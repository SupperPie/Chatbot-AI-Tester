"""
迁移脚本：为 test_history 表添加 case_ids 和 error_message 字段。
用法：python scripts/migrate_job_resilience.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.database import engine, SCHEMA


def migrate():
    """Add case_ids (JSONB) and error_message (TEXT) columns to test_history if not exist."""
    from sqlalchemy import text

    with engine.connect() as conn:
        # Check and add case_ids
        result = conn.execute(text(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = '{SCHEMA}' AND table_name = 'test_history' AND column_name = 'case_ids'
        """))
        if result.fetchone() is None:
            conn.execute(text(f'ALTER TABLE {SCHEMA}.test_history ADD COLUMN case_ids JSONB'))
            print("Added column: case_ids (JSONB)")
        else:
            print("Column case_ids already exists, skipping.")

        # Check and add error_message
        result = conn.execute(text(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = '{SCHEMA}' AND table_name = 'test_history' AND column_name = 'error_message'
        """))
        if result.fetchone() is None:
            conn.execute(text(f'ALTER TABLE {SCHEMA}.test_history ADD COLUMN error_message TEXT'))
            print("Added column: error_message (TEXT)")
        else:
            print("Column error_message already exists, skipping.")

        conn.commit()
    print("Migration complete.")


if __name__ == "__main__":
    migrate()
