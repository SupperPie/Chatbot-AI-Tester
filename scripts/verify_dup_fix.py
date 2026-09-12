"""验证修复：心跳、CAS、唯一索引幂等插入。跑完自动清理。"""
import sys, os, datetime, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from app.database import SessionLocal
from app.models.test_history import TestHistory, TestResult

TEST_HID = "TESTDUPFIX" + uuid.uuid4().hex[:6]
mgr = None

def cleanup(db):
    db.query(TestResult).filter(TestResult.history_id == TEST_HID).delete()
    db.query(TestHistory).filter(TestHistory.id == TEST_HID).delete()
    db.commit()
    db.close()

try:
    from app.job_manager import JobManager, JOB_HEARTBEAT_STALE_SEC
    # 独立实例（绕过单例，避免污染真实 active_jobs）
    jm = JobManager.__new__(JobManager)
    jm.active_jobs = {}
    jm._initialized = True

    db = SessionLocal()

    # 取一个库里真实存在的用例 ID 供 _reload_cases 加载
    real_case = db.execute(
        __import__('sqlalchemy').text("SELECT id FROM ai_chatbot_tester.test_cases ORDER BY id LIMIT 1")
    ).fetchone()
    REAL_CID = real_case[0]

    # ============ TEST 1: detect_stale_jobs 心跳保护 ============
    # 新鲜心跳的 running job（不在本进程 active_jobs）→ 不应被标记
    now = datetime.datetime.utcnow()
    db.add(TestHistory(id=TEST_HID, timestamp=now, api_name="t", total=10, status='running',
                       case_ids=[{"id": REAL_CID, "turn_index": 1}], heartbeat=now, created_at=now))
    db.commit()
    jm.detect_stale_jobs()
    e = db.query(TestHistory).filter(TestHistory.id == TEST_HID).first()
    assert e.status == 'running', f"TEST1 FAIL: 新鲜心跳被误标为 {e.status}"
    print("[TEST1] 心跳新鲜 → 未被误标 interrupted ✓")

    # 心跳过期 → 应被标记
    e.heartbeat = now - datetime.timedelta(seconds=JOB_HEARTBEAT_STALE_SEC + 60)
    db.commit()
    jm.detect_stale_jobs()
    db.expire_all()
    e = db.query(TestHistory).filter(TestHistory.id == TEST_HID).first()
    assert e.status == 'interrupted', f"TEST2 FAIL: 过期心跳未被标记, 仍是 {e.status}"
    print("[TEST2] 心跳过期(>15min) → 正确标记 interrupted ✓")

    # ============ TEST 3: continue_job 原子抢占（CAS）============
    # 打桩：禁止真实执行用例（只验证状态机与幂等性）
    jm._worker = lambda *a, **k: None
    r1 = jm.continue_job(TEST_HID, max_workers=1)
    assert r1["ok"], f"TEST3 FAIL: 第一次 Continue 应成功: {r1}"
    r2 = jm.continue_job(TEST_HID, max_workers=1)
    assert not r2["ok"], f"TEST4 FAIL: 第二次 Continue 应被拒绝: {r2}"
    print(f"[TEST3] 第一次 Continue 成功 ✓")
    print(f"[TEST4] 第二次 Continue 被原子拒绝（{r2['message']}）✓")

    # ============ TEST 5: 结果幂等插入（同 case_id 只落一行）============
    fake_result = {"id": REAL_CID, "input": "x", "actual_output": "y", "expected_output": "z",
                   "passed": True, "score": 0.9, "type": "single"}
    jm._update_job_progress(TEST_HID, fake_result, 1, 10)
    jm._update_job_progress(TEST_HID, fake_result, 2, 10)  # 重复写入应被唯一索引吞掉
    db.expire_all()  # _update_job_progress 用独立会话提交，刷新本会话缓存
    cnt = db.query(TestResult).filter(TestResult.history_id == TEST_HID).count()
    assert cnt == 1, f"TEST5 FAIL: 期望1行实际{cnt}行"
    e = db.query(TestHistory).filter(TestHistory.id == TEST_HID).first()
    assert e.heartbeat is not None and e.heartbeat > now, "TEST5 FAIL: 心跳未更新"
    print("[TEST5] 同 case 重复结果被唯一索引拦截，心跳已更新 ✓")

    # ============ TEST 6: cancel 跨进程误杀保护 ============
    # 状态 running + 新鲜心跳 + 不在本进程 active_jobs → cancel 应被拒绝
    e.status = 'running'
    e.heartbeat = datetime.datetime.utcnow()
    db.commit()
    jm.cancel_job(TEST_HID)
    db.expire_all()
    e = db.query(TestHistory).filter(TestHistory.id == TEST_HID).first()
    assert e.status == 'running', f"TEST6 FAIL: 新鲜心跳的 job 被跨进程 cancel 误杀为 {e.status}"
    print("[TEST6] 跨进程 Stop 误杀被心跳拦截 ✓")

    print("\n=== ALL TESTS PASSED ===")
    cleanup(db)
except Exception as ex:
    print(f"\n!!! TEST FAILED: {ex}")
    try:
        cleanup(SessionLocal())
    except Exception:
        pass
    sys.exit(1)
