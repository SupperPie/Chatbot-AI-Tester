"""
迁移脚本：
  1. 为 test_cases 表添加 module 字段（允许为空）
  2. 为 test_results 表添加 module 字段（允许为空，执行时快照）
  3. 为 test_history 表添加 report_name 字段（允许为空，Run 弹窗输入的报告名）
  4. 为 test_results 表添加 actual_output_cn 字段（允许为空，结果中文翻译）
用法：python scripts/migrate_module_report_name.py
"""
import os
import sys
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
    with engine.connect() as conn:
        # 1. test_cases.module
        if not _column_exists(conn, 'test_cases', 'module'):
            conn.execute(text(f"ALTER TABLE {SCHEMA}.test_cases ADD COLUMN module VARCHAR(100)"))
            print("Added column: test_cases.module (VARCHAR(100), nullable)")
        else:
            print("Column test_cases.module already exists, skipping.")

        # 2. test_results.module（执行时快照）
        if not _column_exists(conn, 'test_results', 'module'):
            conn.execute(text(f"ALTER TABLE {SCHEMA}.test_results ADD COLUMN module VARCHAR(100)"))
            print("Added column: test_results.module (VARCHAR(100), nullable)")
        else:
            print("Column test_results.module already exists, skipping.")

        # 3. test_history.report_name（Run 弹窗输入的报告名）
        if not _column_exists(conn, 'test_history', 'report_name'):
            conn.execute(text(f"ALTER TABLE {SCHEMA}.test_history ADD COLUMN report_name VARCHAR(200)"))
            print("Added column: test_history.report_name (VARCHAR(200), nullable)")
        else:
            print("Column test_history.report_name already exists, skipping.")

        # 4. test_results.actual_output_cn（中文翻译结果）
        if not _column_exists(conn, 'test_results', 'actual_output_cn'):
            conn.execute(text(f"ALTER TABLE {SCHEMA}.test_results ADD COLUMN actual_output_cn TEXT"))
            print("Added column: test_results.actual_output_cn (TEXT, nullable)")
        else:
            print("Column test_results.actual_output_cn already exists, skipping.")

        conn.commit()

    print("Migration complete.")


if __name__ == "__main__":
    migrate()
