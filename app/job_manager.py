import threading
import json
import os
import datetime
import time
from typing import List, Dict, Any, Callable
from app.test_engine import TestEngine

# Path to history file (absolute to avoid CWD issues on servers)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class JobManager:
    _instance = None
    _lock = threading.Lock()
    _db_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(JobManager, cls).__new__(cls)
                    cls._instance.active_jobs = {} # report_id -> thread
        return cls._instance

    def run_background_job(self, cases: List[Dict], api_name: str) -> str:
        """
        Starts a background job.
        Returns the report_id (job_id).
        """
        report_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        
        # 1. Create initial entry in DB with status=running
        self._create_history_entry(report_id, api_name, len(cases))
        
        # 2. Start Thread
        thread = threading.Thread(target=self._worker, args=(report_id, cases, api_name))
        thread.daemon = True
        self.active_jobs[report_id] = {
            "thread": thread,
            "cancelled": False
        }
        thread.start()
        
        return report_id

    def cancel_job(self, report_id: str):
        """Signal a job to stop."""
        if report_id in self.active_jobs:
            self.active_jobs[report_id]["cancelled"] = True
            print(f"Job {report_id} cancelled by user.")

    def _worker(self, report_id: str, cases: List[Dict], api_name: str):
        # Callback for incremental updates
        def on_step_complete(case_result: Dict, current_count: int, total_count: int):
            self._update_job_progress(report_id, case_result, current_count, total_count)
        
        # Check cancellation
        def should_stop():
            if report_id in self.active_jobs:
                return self.active_jobs[report_id].get("cancelled", False)
            return False

        try:
            engine = TestEngine()
            engine.run_batch(cases, api_name=api_name, on_step_complete=on_step_complete, should_stop=should_stop)
            
            if should_stop():
                 self._finalize_job(report_id, status="cancelled")
            else:
                 self._finalize_job(report_id, status="completed")
            
        except Exception as e:
            print(f"Job {report_id} failed: {e}")
            self._finalize_job(report_id, status="failed", error=str(e))
        finally:
            if report_id in self.active_jobs:
                del self.active_jobs[report_id]

    def _create_history_entry(self, report_id: str, api_name: str, total: int):
        """Create initial history entry in DB with status=running"""
        with self._db_lock:
            try:
                from app.database import SessionLocal
                from app.models.test_history import TestHistory
                db = SessionLocal()
                now = datetime.datetime.utcnow()
                entry = TestHistory(
                    id=report_id,
                    timestamp=now,
                    api_name=api_name,
                    total=total,
                    passed=0,
                    failed=0,
                    status='running',
                    started_count=0,
                    source='local',
                    created_at=now
                )
                db.add(entry)
                db.commit()
                db.close()
            except Exception as e:
                print(f"Error creating history entry {report_id}: {e}")

    def _update_job_progress(self, report_id: str, new_result: Dict, current_count: int, total_count: int):
        """Update job progress: add result row and update stats"""
        with self._db_lock:
            try:
                from app.database import SessionLocal
                from app.models.test_history import TestHistory, TestResult
                db = SessionLocal()

                # Add result row
                tr = TestResult(
                    history_id=report_id,
                    case_id=new_result.get('id') or new_result.get('case_id'),
                    input=new_result.get('input'),
                    actual_output=new_result.get('actual_output'),
                    expected_output=new_result.get('expected_output'),
                    retrieval_context=new_result.get('retrieval_context'),
                    score=new_result.get('score'),
                    reason=new_result.get('reason'),
                    faithfulness_score=new_result.get('faithfulness_score'),
                    faithfulness_reason=new_result.get('faithfulness_reason'),
                    passed=new_result.get('passed', False),
                    thinking=new_result.get('thinking'),
                    inform_base=new_result.get('inform_base'),
                    raw=new_result.get('raw'),
                    latency=new_result.get('latency'),
                    ttft=new_result.get('ttft'),
                    type=new_result.get('type'),
                    total_turns=new_result.get('total_turns'),
                    passed_turns=new_result.get('passed_turns'),
                    success_rate=new_result.get('success_rate'),
                    overall_score=new_result.get('overall_score'),
                    overall_passed=new_result.get('overall_passed'),
                    turns=new_result.get('turns'),
                    user_id=new_result.get('user_id'),
                    session_id=new_result.get('session_id'),
                    created_at=datetime.datetime.utcnow()
                )
                db.add(tr)

                # Update history stats
                entry = db.query(TestHistory).filter(TestHistory.id == report_id).first()
                if entry:
                    entry.total = total_count
                    entry.started_count = current_count
                    # Recalculate passed/failed from DB
                    passed = db.query(TestResult).filter(
                        TestResult.history_id == report_id,
                        TestResult.passed == True
                    ).count() + (1 if new_result.get('passed') else 0)
                    entry.passed = passed
                    entry.failed = current_count - passed

                db.commit()
                db.close()
            except Exception as e:
                print(f"Error updating job {report_id}: {e}")

    def _finalize_job(self, report_id: str, status: str, error: str = None):
        """Mark job as completed/failed in DB"""
        with self._db_lock:
            try:
                from app.database import SessionLocal
                from app.models.test_history import TestHistory, TestResult
                db = SessionLocal()

                entry = db.query(TestHistory).filter(TestHistory.id == report_id).first()
                if entry:
                    entry.status = status
                    # Final stats
                    total_results = db.query(TestResult).filter(TestResult.history_id == report_id).count()
                    passed_count = db.query(TestResult).filter(
                        TestResult.history_id == report_id,
                        TestResult.passed == True
                    ).count()
                    entry.total = total_results
                    entry.passed = passed_count
                    entry.failed = total_results - passed_count

                db.commit()
                db.close()
            except Exception as e:
                print(f"Error finalizing job {report_id}: {e}")


def get_job_manager() -> JobManager:
    return JobManager()
