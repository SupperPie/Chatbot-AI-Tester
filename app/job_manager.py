import threading
import json
import os
import datetime
import time
from typing import List, Dict, Any, Callable
from app.test_engine import TestEngine
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Path to history file (absolute to avoid CWD issues on servers)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Job 心跳超时阈值：本地与服务器共用同一数据库时，各自进程只认自己内存里的 active_jobs。
# 只有心跳超过该阈值的 running Job 才允许被其他进程判为僵尸（interrupted），
# 否则会出现"服务器把本地正在跑的 Job 误标中断 → 用户点 Continue → 同一用例被执行两次"的问题。
# 单条用例最长执行约 1~2 分钟，15 分钟阈值有约 10 倍安全余量。
JOB_HEARTBEAT_STALE_SEC = 15 * 60


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
                    cls._instance._initialized = False
        return cls._instance

    def _ensure_initialized(self):
        """Detect stale (zombie) jobs on first access after process start."""
        if not self._initialized:
            self._initialized = True
            self.detect_stale_jobs()

    def detect_stale_jobs(self):
        """扫描 DB 中 status='running' 但本进程 active_jobs 不存在的 Job，标记为 interrupted。

        心跳保护：heartbeat 在阈值内说明该 Job 正在另一个进程（如服务器容器）中
        正常运行，本进程不能动它，否则会诱导用户 Continue 导致用例被执行两次。
        仅当心跳为 NULL（旧数据/功能上线前的 Job）或已超时才标记为 interrupted。
        """
        with self._db_lock:
            try:
                from app.database import SessionLocal
                from app.models.test_history import TestHistory, TestResult
                db = SessionLocal()
                stale_before = datetime.datetime.utcnow() - datetime.timedelta(seconds=JOB_HEARTBEAT_STALE_SEC)
                running_jobs = db.query(TestHistory).filter(TestHistory.status == 'running').all()
                for job in running_jobs:
                    if job.id not in self.active_jobs:
                        if job.heartbeat is not None and job.heartbeat > stale_before:
                            print(f"[stale-detect] Job {job.id} heartbeat fresh (running in another process), skipped")
                            continue
                        job.status = 'interrupted'
                        job.error_message = "Job interrupted (process died or restarted)"
                        # Recalculate stats from already-completed results
                        total_results = db.query(TestResult).filter(TestResult.history_id == job.id).count()
                        passed_count = db.query(TestResult).filter(
                            TestResult.history_id == job.id,
                            TestResult.passed == True
                        ).count()
                        job.passed = passed_count
                        job.failed = total_results - passed_count
                        job.total = total_results
                        job.started_count = total_results
                        print(f"[stale-detect] Job {job.id} marked as interrupted ({total_results} results preserved)")
                db.commit()
                db.close()
            except Exception as e:
                print(f"Error detecting stale jobs: {e}")

    def run_background_job(self, cases: List[Dict], api_name: str, execution_mode: str = "full", max_workers: int = 5, report_name: str = None) -> str:
        """
        Starts a background job.
        Returns the report_id (job_id).
        """
        report_id_base = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        report_id = report_id_base

        # 构造 case_ids 快照，用于后续 Continue Job 时差集计算
        case_ids_snapshot = [
            {"id": c.get("id"), "turn_index": c.get("turn_index", 1)}
            for c in cases
        ]

        # 实际要执行的任务数 = 单轮数 + 多轮组数（同一 id 的多 turn 合并为 1 个任务）
        unique_case_ids = set()
        for c in cases:
            cid = c.get("id")
            if cid is not None:
                unique_case_ids.add(cid)
        total_tasks = len(unique_case_ids)

        # 1. Create initial entry in DB with status=running
        # 同一秒内启动两次会生成相同 report_id（主键冲突），重试加后缀保证唯一
        for attempt in range(5):
            if self._create_history_entry(report_id, api_name, total_tasks, case_ids=case_ids_snapshot, report_name=report_name):
                break
            report_id = f"{report_id_base}-{attempt + 1}"
        else:
            raise RuntimeError(f"Failed to create history entry (tried {report_id_base}*)")
        
        # 2. Start Thread
        thread = threading.Thread(target=self._worker, args=(report_id, cases, api_name, execution_mode, max_workers))
        thread.daemon = True
        self.active_jobs[report_id] = {
            "thread": thread,
            "cancelled": False,
            "max_workers": max_workers,
        }
        thread.start()
        
        return report_id

    def cancel_job(self, report_id: str):
        """Signal a job to stop. If the job thread is no longer active (zombie), directly mark as cancelled in DB."""
        if report_id in self.active_jobs:
            self.active_jobs[report_id]["cancelled"] = True
            print(f"Job {report_id} cancelled by user.")
        else:
            # 线程不在本进程：先查心跳，心跳新鲜说明 Job 正在另一个进程运行，拒绝误杀
            # （否则会把别的进程正在跑的 Job 标成 cancelled，诱导 Continue 造成重复执行）
            try:
                from app.database import SessionLocal
                from app.models.test_history import TestHistory
                db = SessionLocal()
                entry = db.query(TestHistory).filter(TestHistory.id == report_id).first()
                if entry and entry.status == 'running' and entry.heartbeat is not None:
                    stale_before = datetime.datetime.utcnow() - datetime.timedelta(seconds=JOB_HEARTBEAT_STALE_SEC)
                    if entry.heartbeat > stale_before:
                        db.close()
                        print(f"Job {report_id} appears alive in another process (fresh heartbeat); cancel refused.")
                        return
                db.close()
            except Exception as e:
                print(f"Error checking heartbeat for cancel {report_id}: {e}")
            # 心跳超时/为空（僵尸 Job），直接更新 DB 状态
            self._finalize_job(report_id, status="cancelled", error="Cancelled by user (job was stale)")
            print(f"Job {report_id} cancelled (stale job, no active thread).")

    def continue_job(self, report_id: str, max_workers: int = 5) -> Dict[str, Any]:
        """续跑一个 cancelled / interrupted / failed 的 Job。

        返回: {"ok": bool, "message": str, "remaining": int}
        """
        with self._db_lock:
            try:
                from app.database import SessionLocal
                from app.models.test_history import TestHistory, TestResult
                from sqlalchemy import text
                db = SessionLocal()
                entry = db.query(TestHistory).filter(TestHistory.id == report_id).first()
                if not entry:
                    db.close()
                    return {"ok": False, "message": "Report not found", "remaining": 0}
                if entry.status == 'running':
                    db.close()
                    return {"ok": False, "message": "Job is currently running", "remaining": 0}
                if entry.status == 'completed':
                    db.close()
                    return {"ok": False, "message": "Job already completed", "remaining": 0}
                if not entry.case_ids:
                    db.close()
                    return {"ok": False, "message": "Old job without case_ids snapshot, please use Rerun instead", "remaining": 0}

                # 计算 remaining：原始 case_ids - 已存在的 TestResult
                completed_keys = set()
                for r in db.query(TestResult).filter(TestResult.history_id == report_id).all():
                    completed_keys.add(r.case_id)  # 用 case_id 标识；多轮以 id 为整体单位

                remaining_ids = []
                for c in entry.case_ids:
                    if c["id"] not in completed_keys:
                        remaining_ids.append(c)

                # 去重（多轮的多 turn 共享 id，避免重复加载）
                seen = set()
                remaining_unique_ids = []
                for c in remaining_ids:
                    if c["id"] not in seen:
                        seen.add(c["id"])
                        remaining_unique_ids.append(c["id"])

                if not remaining_unique_ids:
                    # 全部完成，直接 finalize
                    db.close()
                    self._finalize_job(report_id, status="completed")
                    return {"ok": True, "message": "All cases already completed, finalized", "remaining": 0}

                # 原子抢占（CAS）：仅当状态仍是可续跑状态时才置为 running。
                # 防止双击 Continue 或本地/服务器两个进程同时续跑同一份报告，
                # 造成同一用例被两条执行流各跑一次（结果重复）。
                cas = db.execute(text(
                    "UPDATE ai_chatbot_tester.test_history "
                    "SET status = 'running', error_message = NULL, heartbeat = now() "
                    "WHERE id = :rid AND status IN ('cancelled', 'interrupted', 'failed')"
                ), {"rid": report_id})
                db.commit()
                if cas.rowcount == 0:
                    db.close()
                    return {"ok": False, "message": "Job was just picked up elsewhere (or state changed), please refresh", "remaining": 0}

                api_name = entry.api_name
                db.close()
            except Exception as e:
                print(f"Error preparing continue_job {report_id}: {e}")
                return {"ok": False, "message": f"Error: {e}", "remaining": 0}

        # 重新加载 remaining 对应的完整 case 数据（在 _db_lock 外，避免长期持锁）
        remaining_cases = self._reload_cases(remaining_unique_ids)
        if not remaining_cases:
            self._finalize_job(report_id, status="failed", error="Failed to reload remaining cases")
            return {"ok": False, "message": "Failed to reload remaining cases (deleted from library?)", "remaining": 0}
        
        thread = threading.Thread(
            target=self._worker,
            args=(report_id, remaining_cases, api_name, "full", max_workers)
        )
        thread.daemon = True
        self.active_jobs[report_id] = {
            "thread": thread,
            "cancelled": False,
            "max_workers": max_workers,
        }
        thread.start()
        
        return {"ok": True, "message": f"Continue started ({len(remaining_unique_ids)} remaining)", "remaining": len(remaining_unique_ids)}

    def _reload_cases(self, case_ids: List[str]) -> List[Dict]:
        """根据 case id 列表从主数据源重新加载完整 case 数据（含多轮的所有 turn）。"""
        try:
            from app.utils import load_data
            df = load_data()
            if df is None or df.empty:
                return []
            cases = []
            for cid in case_ids:
                mask = df['id'] == cid
                if mask.any():
                    rows = df[mask]
                    for _, row in rows.iterrows():
                        cases.append(row.to_dict())
            return cases
        except Exception as e:
            print(f"Error reloading cases: {e}")
            return []

    def _worker(self, report_id: str, cases: List[Dict], api_name: str, execution_mode: str = "full", max_workers: int = 1):
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
            engine.run_batch(cases, api_name=api_name, on_step_complete=on_step_complete, should_stop=should_stop, execution_mode=execution_mode, max_workers=max_workers)
            
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

    def _create_history_entry(self, report_id: str, api_name: str, total: int, case_ids=None, report_name: str = None) -> bool:
        """Create initial history entry in DB with status=running. Returns False on PK collision."""
        with self._db_lock:
            db = None
            try:
                from app.database import SessionLocal
                from app.models.test_history import TestHistory
                db = SessionLocal()
                now = datetime.datetime.utcnow()
                entry = TestHistory(
                    id=report_id,
                    timestamp=now,
                    api_name=api_name,
                    report_name=report_name,
                    total=total,
                    passed=0,
                    failed=0,
                    status='running',
                    started_count=0,
                    source='local',
                    case_ids=case_ids,
                    heartbeat=now,
                    created_at=now
                )
                db.add(entry)
                db.commit()
                db.close()
                return True
            except Exception as e:
                print(f"Error creating history entry {report_id}: {e}")
                try:
                    if db:
                        db.close()
                except Exception:
                    pass
                return False

    def _update_job_progress(self, report_id: str, new_result: Dict, current_count: int, total_count: int):
        """Update job progress: add result row and update stats"""
        with self._db_lock:
            try:
                from app.database import SessionLocal
                from app.models.test_history import TestHistory, TestResult
                db = SessionLocal()

                # Add result row —— (history_id, case_id) 唯一索引兜底：
                # 即使出现两条执行流（跨进程 Continue 等异常场景），同一条用例的结果也只会落一行
                values = dict(
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
                    assertion_detail=new_result.get('assertion_detail'),
                    category=new_result.get('category'),
                    priority=new_result.get('priority'),
                    module=new_result.get('module'),
                    created_at=datetime.datetime.utcnow()
                )
                stmt = pg_insert(TestResult).values(**values)\
                    .on_conflict_do_nothing(index_elements=['history_id', 'case_id'])
                db.execute(stmt)

                # Update history stats
                entry = db.query(TestHistory).filter(TestHistory.id == report_id).first()
                if entry:
                    # total_tasks 以 run_batch 传的 total_count 为准（已经是单轮 + 多轮组数量，不含多轮子turn）
                    entry.total = total_count
                    entry.started_count = current_count
                    # 心跳：报告每完成一条用例更新一次，跨进程判定 Job 存活
                    entry.heartbeat = datetime.datetime.utcnow()
                    # Recalculate passed from DB（刚插入的行会被 count 到）
                    passed = db.query(TestResult).filter(
                        TestResult.history_id == report_id,
                        TestResult.passed == True
                    ).count()
                    entry.passed = passed
                    entry.failed = current_count - passed

                db.commit()
                db.close()
            except Exception as e:
                print(f"Error updating job {report_id}: {e}")

    def _finalize_job(self, report_id: str, status: str, error: str = None):
        """Mark job as completed/failed/cancelled/interrupted in DB"""
        with self._db_lock:
            try:
                from app.database import SessionLocal
                from app.models.test_history import TestHistory, TestResult
                db = SessionLocal()

                entry = db.query(TestHistory).filter(TestHistory.id == report_id).first()
                if entry:
                    entry.status = status
                    entry.heartbeat = datetime.datetime.utcnow()
                    if error:
                        entry.error_message = error
                    else:
                        entry.error_message = None
                    # Final stats from DB rows（TestResult 行数 = 单轮数 + 多轮组数，与 run_batch 的 total_tasks 一致）
                    total_results = db.query(TestResult).filter(TestResult.history_id == report_id).count()
                    passed_count = db.query(TestResult).filter(
                        TestResult.history_id == report_id,
                        TestResult.passed == True
                    ).count()
                    entry.total = total_results
                    entry.passed = passed_count
                    entry.failed = total_results - passed_count
                    entry.started_count = total_results

                db.commit()
                db.close()
            except Exception as e:
                print(f"Error finalizing job {report_id}: {e}")


def get_job_manager() -> JobManager:
    mgr = JobManager()
    mgr._ensure_initialized()
    return mgr
