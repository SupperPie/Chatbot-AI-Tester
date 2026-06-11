# Job 可靠性与断点续跑（Job Resilience & Continue）

## 1. 需求概述

当前测试执行 Job 在以下场景会出现"显示永远 running 但实际已死"的问题：
- 单 case 网络瞬时抖动直接判失败（无重试）
- 进程崩溃 / 服务重启 / 线程 OOM → daemon 线程被强杀，DB status 永远停在 `running`（僵尸 Job）
- UI 死循环轮询无超时，僵尸 Job 让页面无限转圈

本次目标：让 Job 在异常下能被准确识别、UI 能正确展示、用户能从断点续跑而不丢失已有结果。

## 2. 核心设计原则

| 原则 | 含义 |
|---|---|
| **结果先于状态** | 已写入 `TestResult` 的行永远不动，无论 Job 状态怎么变化 |
| **续跑写回原 report** | Continue 复用原 `history_id`，不新建 `TestHistory` |
| **状态显式化** | 引入 `interrupted` 状态明确区分"用户取消 / 程序崩溃 / 业务异常" |
| **重试分层** | API 调用级重试（瞬时网络）≠ Job 级续跑（进程死亡） |

## 3. 三大场景与处理逻辑

### 3.1 场景 A：单 case API 网络瞬时抖动

- 在 `run_case` 调用 `get_chat_response` 处包裹**3 次指数退避重试**（1s / 2s / 4s）
- 仅对网络异常重试（`ConnectionError`/`Timeout`/5xx），业务 4xx 不重试
- 3 次都失败 → 这条 case 标记 `passed=False`，`actual_output="Error after 3 retries: <last_error>"`
- **不阻塞 Job 整体**，下一条继续跑
- 多轮对话里：某一 turn 重试 3 次仍失败 → 该多轮对话 break（沿用现有逻辑）

### 3.2 场景 B：Job 中断检测与回收

僵尸 Job 检测：**服务启动时**或**进入 Report/TestCases 页时**，检查 DB 里 `status='running'` 但本进程 `active_jobs` 中找不到的 Job，直接标记为 `interrupted`。

| 时机 | 触发 | 检测条件 | 处理 |
|---|---|---|---|
| 服务启动时 | `JobManager.__init__` | DB 里 status='running' 但本进程 `active_jobs` 不存在 | 标记为 `interrupted` |
| Report/TestCases 页渲染时 | UI 调 `JobManager.detect_stale_jobs()` | 同上 | 标记为 `interrupted` |

逻辑简单且充分：本平台单进程部署，进程重启后 `active_jobs` 为空字典，之前 `running` 的 Job 必然是僵尸。

### 3.3 场景 C：用户点击 Continue 续跑

```
continue_job(report_id):
  1. 取 TestHistory.case_ids（首次创建 Job 时持久化的原始用例 ID 列表）
  2. 取 DB 中已存在的 TestResult.case_id 集合
  3. remaining = case_ids - completed
  4. 若 remaining 为空：直接 _finalize_job(status="completed")，不启线程
  5. 否则：
     - status = "running"
     - 重新加载 remaining 对应的完整 case 数据（从 load_data() 或 service）
     - 启动新线程，调 engine.run_batch(remaining_cases)
     - on_step_complete 仍以原 history_id 写 TestResult
  6. 完成后 _finalize_job 重新 COUNT(*) 统计 total/passed/failed
```

**关键不变性**：
- `case_ids` 字段始终保持为**首次创建时的原始全量列表**，续跑不修改它
- `total` 字段在续跑路径中**不被覆盖**（仍为原始 100，不是续跑的 70）
- 进度条统一以 `COUNT(TestResult) / case_ids 长度` 计算

## 4. Job 状态机（新增 interrupted）

```
        ┌─────────┐
        │ running │
        └────┬────┘
             │
   ┌─────────┼──────────┬─────────────┐
   │         │          │             │
正常完成  用户取消   进程崩溃     run_batch 抛异常
   ↓         ↓          ↓             ↓
completed  cancelled  interrupted   failed
   │         │          │             │
   │         │          ▼             │
   │         │    [Continue Job]      │
   │         │          │             │
   │         └──────────┼─────────────┘
   │                    ↓
   │               running (续跑)
   │                    │
   │              ┌─────┴─────┐
   │              ↓           ↓
   │          completed   interrupted (再次中断)
   │              │           │
   └──────────────┴───────────┘
```

| 状态 | 含义 | Continue 是否可用 |
|---|---|---|
| running | 正在执行中 | ❌ 只能 Stop |
| completed | 全部完成 | ❌（可用 Rerun） |
| cancelled | 用户主动停 | ✅ |
| interrupted | 进程崩溃/僵尸 Job 被回收 | ✅ |
| failed | run_batch 抛 Python 异常 | ✅ |

## 5. UI 显示设计

### 5.1 Report 页每个 entry 的状态展示

| Status | 显示 | 操作按钮 |
|---|---|---|
| running | 🟡 进行中 X/Y + 进度条 | Stop Job |
| **interrupted** | 🔴 已中断 X/Y（剩余 Z 条未跑） | **Continue Job** / Stop |
| cancelled | ⏸ 已取消 X/Y | **Continue Job** / Rerun All |
| completed | ✅ 完成 | Rerun All / Rerun Failed |
| failed | ❌ 失败：<error_message> | **Continue Job** / Rerun All |

**所有非 running 状态都展示已有结果表**（即使只完成 30/100，那 30 条也完整可见）。

### 5.2 进度条计算口径

无论首次执行还是续跑：
```
progress = COUNT(TestResult WHERE history_id=X) / TestHistory.total
```
（不再使用 `started_count`，因为续跑场景下需要包含老结果）

### 5.3 TestCases 页轮询循环改造

当前死循环 `while True` 改为：
- 增加最大 30 分钟 timeout，超时跳出并提示"Job 仍在后台执行，请到 Report 页查看进度"
- 每次循环检查 status，遇到 `interrupted` 立即跳出并提示"Job 已中断，可在 Report 页 Continue"
- 进入页面时调一次 `detect_stale_jobs()` 回收僵尸 Job

## 6. 数据库变更

### TestHistory 新增字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `case_ids` | JSON | 首次创建时持久化的原始用例 ID 列表，结构：`[{"id": "TC0001", "turn_index": 1}, ...]` |

| `error_message` | Text | 失败/中断的错误信息（修复当前 `_finalize_job(error=...)` 不落库的 bug） |

不需要新表。`TestResult` 表无变更。

## 7. 受影响文件

| 类型 | 路径 | 改动 |
|---|---|---|
| 修改 | `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/models/test_history.py` | 新增 3 个字段 |
| 修改 | `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/test_engine.py` | `run_case` 内 API 调用加 3 次指数退避重试 |
| 修改 | `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/job_manager.py` | (1) 创建 Job 时持久化 case_ids (2) 启动时扫描僵尸 Job (3) 新增 `detect_stale_jobs()` (4) 新增 `continue_job(report_id)` (5) `_finalize_job` 写入 error_message |
| 修改 | `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/services/history_service.py` | 新增 `get_remaining_cases(report_id)`：返回未完成的 case_id 列表 |
| 修改 | `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/report.py` | (1) 进入页面时调 `detect_stale_jobs()` (2) 状态展示扩充 (3) 新增 Continue 按钮 (4) 进度条改用 COUNT 计算 (5) interrupted/failed 也展示结果表 |
| 修改 | `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/testcases.py` | 轮询循环加 timeout + interrupted 检测 |

## 8. 关键实现细节

### 8.1 API 重试（`test_engine.py`）

```python
def _call_with_retry(fn, *args, max_retries=3, **kwargs):
    last_exc = None
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except (ConnectionError, TimeoutError, requests.exceptions.RequestException) as e:
            last_exc = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s
            continue
    raise RuntimeError(f"Failed after {max_retries} retries: {last_exc}")
```

### 8.2 case_ids 持久化（`job_manager.py`）

```python
def run_background_job(self, cases, api_name, execution_mode="full"):
    report_id = datetime.now().strftime("%Y%m%d%H%M%S")
    case_ids_snapshot = [
        {"id": c.get("id"), "turn_index": c.get("turn_index", 1)}
        for c in cases
    ]
    # 创建 TestHistory 时写入 case_ids
    ...
```

### 8.3 僵尸 Job 检测（`job_manager.py`）

```python
def detect_stale_jobs(self):
    """扫描 status='running' 但本进程 active_jobs 中不存在的 Job，标记为 interrupted。"""
    with self._db_lock:
        running_jobs = db.query(TestHistory).filter(TestHistory.status == 'running').all()
        for job in running_jobs:
            if job.id not in self.active_jobs:
                self._finalize_job(job.id, status="interrupted",
                                   error="Job interrupted (process died or restarted)")

# 在 __init__ 中：服务启动时清扫一次
def __init__(self):
    ...
    self.detect_stale_jobs()
```

### 8.4 Continue Job 核心流程（`job_manager.py`）

```python
def continue_job(self, report_id: str) -> bool:
    with self._db_lock:
        entry = db.query(TestHistory).filter(TestHistory.id == report_id).first()
        if not entry or entry.status not in ('cancelled', 'interrupted', 'failed'):
            return False
        case_ids = entry.case_ids or []
        completed = {(r.case_id, r.turn_index or 1)
                     for r in db.query(TestResult).filter_by(history_id=report_id).all()}
        remaining_keys = [c for c in case_ids
                          if (c["id"], c.get("turn_index", 1)) not in completed]
        if not remaining_keys:
            self._finalize_job(report_id, status="completed")
            return True
        # 重新从数据源加载 remaining 对应的完整 case 数据
        remaining_cases = self._reload_cases(remaining_keys)
        entry.status = 'running'
        entry.error_message = None
        db.commit()
    # 启动续跑线程（与 run_background_job 共享 _worker，但传入既有 report_id）
    thread = threading.Thread(target=self._worker, args=(report_id, remaining_cases, ...), daemon=True)
    self.active_jobs[report_id] = {"thread": thread, "cancelled": False}
    thread.start()
    return True
```

### 8.5 多轮对话中断语义

- 当前实现：多轮对话所有 turn 跑完后写**一条** type=multi_turn 的 TestResult
- 中断在多轮对话进行中（turn 2/3 时）→ 该会话**没有任何 TestResult**
- Continue 时识别为"未完成"，整段会话从 turn 1 重新跑
- **设计选择**：保持现状，不做 turn 级断点（因为被测系统的 session 状态我们不可控，从中间 turn 续跑结果不可信）
- 在 doc 中明确告知用户

## 9. 边界条件与异常处理

| 场景 | 处理 |
|---|---|
| Continue 时原始 case 已被删除/修改 | 从 `load_data()` 重新加载，找不到的 case 跳过并记日志；其余正常跑 |
| 用户对同一 Job 连续点 Continue | 每次 Continue 都重新 diff（completed 集合是动态查询），自动避免重复 |
| Continue 期间再次崩溃 | 新一轮的 stale 检测会再次标记 interrupted，可继续 Continue |
| `case_ids` 为空（老数据迁移前的 Job） | Continue 按钮不可用；在 UI 上提示"该 Job 早于功能上线，仅支持 Rerun" |
| API 重试期间用户点 Stop | `should_stop` 在 case 之间检查；当前重试在 case 内部，会先把这一条跑完再退出（可接受） |
| 多个进程同时跑同一个 Continue | DB 层面通过 status 检查（已是 running 则拒绝），但本平台单进程部署，暂不深入 |

## 10. 预期结果

- 单 case 网络抖动可自愈（3 次重试）
- 进程崩溃后下次启动自动回收僵尸 Job → status 变 `interrupted`
- Report 页对 cancelled/interrupted/failed 状态都展示已完成结果，并提供 Continue 按钮
- Continue 后续跑结果写回原 report，total/passed/failed 自动重新统计
- TestCases 页轮询不再无限阻塞
- 进入 Report 页时自动检测僵尸 Job 并回收

## 11. 不在本次范围

- 多轮对话 turn 级别的断点续跑
- 分布式 Job 管理（Celery / RQ）
- Job 优先级队列、并发上限控制
- 失败用例自动 Rerun（仅人工触发 Continue）
- WebSocket 实时推送（仍用轮询）
