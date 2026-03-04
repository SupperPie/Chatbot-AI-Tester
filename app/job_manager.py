import threading
import json
import os
import datetime
import time
from typing import List, Dict, Any, Callable
from app.test_engine import TestEngine

# Path to history file (circular import if we import from utils, so defining here or passing in)
HISTORY_JSON = "data/history.json"

class JobManager:
    _instance = None
    _lock = threading.Lock()
    _file_lock = threading.Lock()

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
        
        # 1. Create initial empty entry in history
        initial_entry = {
            "id": report_id,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total": len(cases), # This is approximate, depends on multi-turn expansion. Updated periodically.
            "passed": 0,
            "failed": 0,
            "status": "running",
            "results": [],
            "api_name": api_name
        }
        
        self._safe_append_history(initial_entry)
        
        # 2. Start Thread
        thread = threading.Thread(target=self._worker, args=(report_id, cases, api_name))
        thread.daemon = True # Daemon thread so it doesn't block app exit (though st works differently)
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
            # Run the batch
            engine.run_batch(cases, api_name=api_name, on_step_complete=on_step_complete, should_stop=should_stop)
            
            # Finalize status (check if actually cancelled during last step)
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

    def _safe_append_history(self, new_entry: Dict):
        """Prepend new entry to history safely."""
        with self._file_lock:
            history = []
            if os.path.exists(HISTORY_JSON):
                try:
                    with open(HISTORY_JSON, "r", encoding="utf-8") as f:
                        history = json.load(f)
                except:
                    history = []
            
            history.insert(0, new_entry)
            
            with open(HISTORY_JSON, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4, ensure_ascii=False)

    def _update_job_progress(self, report_id: str, new_result: Dict, current_count: int, total_count: int):
        """Update specific job in history with new result."""
        with self._file_lock:
            if not os.path.exists(HISTORY_JSON):
                return

            try:
                with open(HISTORY_JSON, "r", encoding="utf-8") as f:
                    history = json.load(f)
                
                # Find the entry
                for entry in history:
                    if entry.get("id") == report_id:
                        # Append result
                        if "results" not in entry:
                            entry["results"] = []
                        entry["results"].append(new_result)
                        
                        # Update stats
                        entry["total"] = total_count # Real total from engine
                        entry["started_count"] = current_count # Track progress
                        
                        # Recalculate passed
                        passed_count = sum(1 for r in entry["results"] if r.get("passed", False))
                        entry["passed"] = passed_count
                        entry["failed"] = len(entry["results"]) - passed_count
                        
                        break
                
                with open(HISTORY_JSON, "w", encoding="utf-8") as f:
                    json.dump(history, f, indent=4, ensure_ascii=False)
                    
            except Exception as e:
                print(f"Error updating job {report_id}: {e}")

    def _finalize_job(self, report_id: str, status: str, error: str = None):
        """Mark job as completed/failed."""
        with self._file_lock:
            if not os.path.exists(HISTORY_JSON):
                return
                
            try:
                with open(HISTORY_JSON, "r", encoding="utf-8") as f:
                    history = json.load(f)
                
                for entry in history:
                    if entry.get("id") == report_id:
                        entry["status"] = status
                        if error:
                            entry["error"] = error
                        # Final stats check
                        passed_count = sum(1 for r in entry.get("results", []) if r.get("passed", False))
                        entry["passed"] = passed_count
                        entry["total"] = len(entry.get("results", [])) # Final total
                        entry["failed"] = entry["total"] - passed_count
                        break
                        
                with open(HISTORY_JSON, "w", encoding="utf-8") as f:
                    json.dump(history, f, indent=4, ensure_ascii=False)
            except:
                pass

# Global Accessor
def get_job_manager():
    return JobManager()
