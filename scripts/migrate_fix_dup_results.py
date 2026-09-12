"""
迁移脚本（修复"同一用例被执行多次"问题）：
  1. test_history 添加 heartbeat 字段（Job 心跳，跨进程判断 Job 存活）
  2. 清理 test_results 中的重复行（同 history_id + case_id 只保留最新一条，删除前备份到 data/）
  3. 重算受影响报告的 total/passed/failed/started_count
  4. 为 (history_id, case_id) 建唯一索引，从 DB 层面杜绝重复结果行

幂等，可重复执行。
用法：python scripts/migrate_fix_dup_results.py
"""
import os
import sys
import json
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.database import engine, SCHEMA


def _column_exists(conn, table, column):
    result = conn.execute(text(f"""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = '{SCHEMA}'
          AND table_name = '{table}'
          AND column_name = '{column}'
    """))
    return result.fetchone() is not None


def migrate():
    backup_path = None
    with engine.begin() as conn:
        # 1. test_history.heartbeat（Job 心跳）
        if not _column_exists(conn, 'test_history', 'heartbeat'):
            conn.execute(text(f"ALTER TABLE {SCHEMA}.test_history ADD COLUMN heartbeat TIMESTAMP"))
            print("Added column: test_history.heartbeat (TIMESTAMP, nullable)")
        else:
            print("Column test_history.heartbeat already exists, skipping.")

        # 2. 找出重复行（同 history_id + case_id 多行，保留 id 最大的一条）
        dup_rows = conn.execute(text(f"""
            SELECT r.id, r.history_id, r.case_id, r.passed, r.created_at
            FROM {SCHEMA}.test_results r
            JOIN (
                SELECT history_id, case_id, MAX(id) AS keep_id
                FROM {SCHEMA}.test_results
                GROUP BY history_id, case_id
                HAVING COUNT(*) > 1
            ) keep
              ON r.history_id = keep.history_id AND r.case_id = keep.case_id AND r.id < keep.keep_id
            ORDER BY r.history_id, r.case_id, r.id
        """)).fetchall()

        if dup_rows:
            # 删除前备份
            backup_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", f"backup_dup_results_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            backup = [dict(zip(['id', 'history_id', 'case_id', 'passed', 'created_at'], [r[0], r[1], r[2], r[3], str(r[4])])) for r in dup_rows]
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(backup, f, ensure_ascii=False, indent=2)

            # 找出受影响的报告，稍后重算统计
            affected = sorted({r[1] for r in dup_rows})

            # 删除旧行（保留每组最新）
            conn.execute(text(f"""
                DELETE FROM {SCHEMA}.test_results r
                USING (
                    SELECT history_id, case_id, MAX(id) AS keep_id
                    FROM {SCHEMA}.test_results
                    GROUP BY history_id, case_id
                    HAVING COUNT(*) > 1
                ) keep
                WHERE r.history_id = keep.history_id
                  AND r.case_id = keep.case_id
                  AND r.id < keep.keep_id
            """))
            print(f"Removed {len(dup_rows)} duplicate result rows (kept latest per history_id+case_id).")
            print(f"Backup saved to: {backup_path}")

            # 3. 重算受影响报告的统计
            for hid in affected:
                stats = conn.execute(text(f"""
                    SELECT COUNT(*), COUNT(*) FILTER (WHERE passed)
                    FROM {SCHEMA}.test_results WHERE history_id = :h
                """), {"h": hid}).fetchone()
                total, passed = stats[0], stats[1] or 0
                conn.execute(text(f"""
                    UPDATE {SCHEMA}.test_history
                    SET total = :t, passed = :p, failed = :t - :p, started_count = :t
                    WHERE id = :h
                """), {"t": total, "p": passed, "h": hid})
                print(f"  Recalculated report {hid}: total={total} passed={passed} failed={total - passed}")
        else:
            print("No duplicate result rows found.")

        # 4. 唯一索引（DB 层兜底：同一报告同一用例只能有一行结果）
        idx_exists = conn.execute(text(f"""
            SELECT 1 FROM pg_indexes
            WHERE schemaname = '{SCHEMA}'
              AND indexname = 'uq_test_results_history_case'
        """)).fetchone()
        if not idx_exists:
            # 索引创建前再保险检查一次（并发情况下上面可能已清掉）
            conn.execute(text(f"""
                CREATE UNIQUE INDEX uq_test_results_history_case
                ON {SCHEMA}.test_results (history_id, case_id)
            """))
            print("Created unique index: uq_test_results_history_case (history_id, case_id)")
        else:
            print("Unique index uq_test_results_history_case already exists, skipping.")

    print("Migration complete.")


if __name__ == "__main__":
    migrate()
