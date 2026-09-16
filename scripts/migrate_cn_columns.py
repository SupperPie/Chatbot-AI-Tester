"""
数据库迁移脚本（幂等，可重复执行）：
对比 ORM 模型与实际表结构，自动补齐所有缺失列。

覆盖表：
  - test_cases   (TestCase)
  - test_history (TestHistory)
  - test_results (TestResult)

用法: python3 scripts/migrate_cn_columns.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from app.database import SessionLocal, SCHEMA
from app.models.test_case import TestCase
from app.models.test_history import TestHistory, TestResult

TABLES = [
    TestCase,
    TestHistory,
    TestResult,
]


def get_existing_columns(db, table_name: str) -> set:
    rows = db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = :schema AND table_name = :table"
    ), {"schema": SCHEMA, "table": table_name}).fetchall()
    return {r[0] for r in rows}


def sync_table(db, model) -> list:
    """把模型中存在、表中缺失的列补上。返回新增列名列表。"""
    table_name = model.__tablename__
    existing = get_existing_columns(db, table_name)
    if not existing:
        print(f"  ⚠️ 表 {SCHEMA}.{table_name} 不存在，跳过（等待建表）")
        return []

    added = []
    dialect = postgresql.dialect()
    for col in model.__table__.columns:
        if col.name in existing:
            continue
        type_sql = col.type.compile(dialect)
        stmt = f'ALTER TABLE {SCHEMA}.{table_name} ADD COLUMN IF NOT EXISTS "{col.name}" {type_sql}'
        db.execute(text(stmt))
        added.append(col.name)
        print(f"  ✓ {table_name}: ADD COLUMN {col.name} {type_sql}")
    return added


def run_migration():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("Running migration: auto-sync model columns to DB")
        print("=" * 60)

        total_added = 0
        for model in TABLES:
            print(f"\n[{model.__tablename__}]")
            added = sync_table(db, model)
            if not added:
                print("  （无缺失列）")
            total_added += len(added)

        db.commit()
        print(f"\n✅ Migration completed! 共新增 {total_added} 列。")

        # 验证：打印三张表的列数对比
        print("\n--- 验证 ---")
        for model in TABLES:
            model_cols = {c.name for c in model.__table__.columns}
            db_cols = get_existing_columns(db, model.__tablename__)
            missing = model_cols - db_cols
            status = "OK" if not missing else f"仍缺: {missing}"
            print(f"  {model.__tablename__}: 模型 {len(model_cols)} 列 / DB {len(db_cols)} 列 -> {status}")
    except Exception as e:
        db.rollback()
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_migration()
