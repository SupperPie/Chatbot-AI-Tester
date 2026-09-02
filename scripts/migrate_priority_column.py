"""
迁移脚本：为 test_cases 表添加 priority 字段（允许为空）。
用法：python scripts/migrate_priority_column.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.database import engine, SCHEMA


def migrate():
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = '{SCHEMA}'
              AND table_name = 'test_cases'
              AND column_name = 'priority'
        """))
        if result.fetchone() is None:
            conn.execute(text(f"ALTER TABLE {SCHEMA}.test_cases ADD COLUMN priority VARCHAR(2)"))
            print("Added column: priority (VARCHAR(2), nullable)")
        else:
            print("Column priority already exists, skipping.")
        conn.commit()

    print("Migration complete.")


if __name__ == "__main__":
    migrate()
