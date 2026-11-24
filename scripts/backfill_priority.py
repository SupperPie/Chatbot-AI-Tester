"""
Backfill priority and category for test_results from recent history
using data from test_cases table.

Usage:
    python scripts/backfill_priority.py [--days N]

Default: backfill last 2 days.
"""
import sys, os
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.database import SessionLocal, SCHEMA
from sqlalchemy import text
from datetime import datetime, timedelta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=2, help="Number of days to look back (default: 2)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=args.days)
        print(f"Cutoff (UTC): {cutoff}  (looking back {args.days} days)")

        # Check priority distribution in test_cases
        dist = db.execute(text(f"""
            SELECT COALESCE(priority, 'NULL') as p, COUNT(*) 
            FROM {SCHEMA}.test_cases 
            GROUP BY priority ORDER BY p
        """)).fetchall()
        print(f"test_cases priority distribution: {dist}")

        # Backfill priority from test_cases (turn_index=1 as canonical)
        print("\n--- Backfilling priority ---")
        result = db.execute(text(f"""
            UPDATE {SCHEMA}.test_results tr
            SET priority = tc.priority
            FROM {SCHEMA}.test_cases tc
            WHERE tr.case_id = tc.id
              AND tc.turn_index = 1
              AND tr.priority IS NULL
              AND tr.history_id IN (
                  SELECT id FROM {SCHEMA}.test_history
                  WHERE timestamp >= :cutoff
              )
              AND tc.priority IS NOT NULL
              AND tc.priority <> ''
        """), {"cutoff": cutoff})
        print(f"Updated {result.rowcount} rows with priority from test_cases.")

        # Backfill category from categories table
        print("\n--- Backfilling category ---")
        result2 = db.execute(text(f"""
            UPDATE {SCHEMA}.test_results tr
            SET category = c.name
            FROM {SCHEMA}.test_cases tc
            LEFT JOIN {SCHEMA}.categories c ON tc.category_id = c.id
            WHERE tr.case_id = tc.id
              AND tc.turn_index = 1
              AND tr.category IS NULL
              AND tr.history_id IN (
                  SELECT id FROM {SCHEMA}.test_history
                  WHERE timestamp >= :cutoff
              )
        """), {"cutoff": cutoff})
        print(f"Updated {result2.rowcount} rows with category from categories.")

        db.commit()

        # Verify
        print("\n--- Verification ---")
        total = db.execute(text(f"""
            SELECT COUNT(*) FROM {SCHEMA}.test_results tr
            JOIN {SCHEMA}.test_history th ON tr.history_id = th.id
            WHERE th.timestamp >= :cutoff
        """), {"cutoff": cutoff}).scalar()
        filled = db.execute(text(f"""
            SELECT COUNT(*) FROM {SCHEMA}.test_results tr
            JOIN {SCHEMA}.test_history th ON tr.history_id = th.id
            WHERE th.timestamp >= :cutoff
              AND tr.priority IS NOT NULL AND tr.priority <> ''
        """), {"cutoff": cutoff}).scalar()
        remaining = total - filled
        print(f"Total recent results: {total}")
        print(f"Results with priority: {filled}")
        print(f"Results still without priority: {remaining} (test case itself has no priority or was deleted)")

        dist2 = db.execute(text(f"""
            SELECT COALESCE(tr.priority, 'NULL') as p, COUNT(*)
            FROM {SCHEMA}.test_results tr
            JOIN {SCHEMA}.test_history th ON tr.history_id = th.id
            WHERE th.timestamp >= :cutoff
            GROUP BY tr.priority ORDER BY p
        """), {"cutoff": cutoff}).fetchall()
        print(f"Priority distribution in recent results: {dist2}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()

    print("\nBackfill complete!")


if __name__ == "__main__":
    main()
