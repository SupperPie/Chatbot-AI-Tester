# Parallel Test Execution (可配置并发线程数)

## 需求背景与场景

当前 `TestEngine.run_batch` 串行执行测试用例，一个 case 平均 10-30s（chatbot API + LLM 语义评分），
100 条 case 需要几十分钟，非常慢。而 `run_case` 是 I/O bound（HTTP + LLM 调用），
非常适合线程池并发。

## 目标

1. 在 `testcases` 页面 API 下拉框旁边加一个 **并发线程数** 设置，范围 1-10，默认 5
2. 并发只用于 **单轮 cases**；**多轮对话（multi-turn）保持串行**（同一 case_id 的多轮之间存在上下文/顺序依赖，不能并行）
3. Stop 中断机制：一次点击 Stop，所有并发线程都要尽快退出，不再启动新任务
4. Rerun/Continue 使用同样的并发线程数
5. Report 页面对 `cancelled` / `interrupted` 提示继续兼容（因为并发下"已完成数"可能不再是连续前缀，需要按实际完成数展示）

## 技术方案

### 整体思路
- 在 `TestEngine.run_batch` 内部改造：
  - **单轮 cases**：用 `ThreadPoolExecutor(max_workers=N)` 提交 `run_case`，用 `as_completed` 收集
  - **多轮 grouped_cases**：保持原来的 for 循环串行执行（不做任何并发改动）
- `max_workers=N` 从上游传入，默认 5
- 传入链路：UI (`testcases.py`) → `JobManager.run_background_job(...)` → `_worker` → `engine.run_batch(..., max_workers=N)`
- Rerun / Continue 走同样的入参链路（`report.py` 里的两个按钮）

### 关键改动点

#### 1. `app/test_engine.py` - `run_batch`
新增参数 `max_workers: int = 1`（保持向后兼容，1 就是原有串行行为）。
```python
def run_batch(self, cases, api_name="Skills", on_step_complete=None,
              should_stop=None, execution_mode="full", max_workers: int = 1):
    ...
    completed_lock = threading.Lock()
    completed_tasks = 0

    def _wrap(case):
        # 每个线程内部先检查 stop
        if should_stop and should_stop():
            return None
        try:
            return self.run_case(case, api_name=api_name, execution_mode=execution_mode)
        except Exception as e:
            # 保底：失败也返回一个错误 result（避免线程池吞异常）
            return {"case_id": case.get("id"), "error": str(e), "passed": False, ...}

    # ---- 单轮 cases 并发 ----
    if max_workers > 1 and len(single_cases) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers,
                                                   thread_name_prefix="run_case") as pool:
            futures = {pool.submit(_wrap, c): c for c in single_cases}
            for fut in concurrent.futures.as_completed(futures):
                if should_stop and should_stop():
                    # 取消尚未开始的任务；正在执行的等它跑完（无法强制中断线程）
                    for f in futures:
                        f.cancel()
                    break
                res = fut.result()
                if res is None:
                    continue
                results.append(res)
                with completed_lock:
                    completed_tasks += 1
                    idx = completed_tasks
                if on_step_complete:
                    on_step_complete(res, idx, total_tasks)
    else:
        for case in single_cases:
            if should_stop and should_stop():
                break
            res = self.run_case(case, api_name=api_name, execution_mode=execution_mode)
            results.append(res)
            completed_tasks += 1
            if on_step_complete:
                on_step_complete(res, completed_tasks, total_tasks)

    # ---- 多轮 cases 保持串行（不动） ----
    for case_id, group in grouped_cases.items():
        if should_stop and should_stop():
            break
        ...
```

**为什么多轮不并行？**
- 一个 case_id 的多轮之间需要按 `turn_index` 顺序调 chatbot，session_id 累积上下文
- 用户明确要求"多轮对话一定要串行执行"

**要不要不同 case_id 的多轮之间也并行？** 本次不做，保持串行——降低复杂度，避免 DeepEval / API session 冲突；如后续必要再单独拆一个 spec 加进来。

#### 2. `app/job_manager.py`
- `run_background_job(cases, api_name, execution_mode="full", max_workers: int = 5)` 增加参数
- `_worker` 里读出后传给 `engine.run_batch(..., max_workers=max_workers)`
- `continue_job(report_id, max_workers: int = 5)` 也加参数

存储：`active_jobs[report_id]["max_workers"] = N` 便于诊断（可选）。

#### 3. `app/ui/testcases.py` - API 下拉旁加并发 slider

当前 `top_col1, top_col2, top_col3, top_col4 = st.columns([3, 1, 1, 1])`，
把 `top_col1` 内部再拆成两个子列：selectbox + slider。

```python
top_col1, top_col2, top_col3, top_col4 = st.columns([3, 1, 1, 1])
with top_col1:
    sub1, sub2 = st.columns([2, 1])
    with sub1:
        selected_api = st.selectbox(
            "⚙️ API Endpoint", options=available_apis, index=0,
            key="page_api_select", label_visibility="collapsed"
        )
    with sub2:
        max_workers = st.number_input(
            "并发", min_value=1, max_value=10, value=5, step=1,
            key="page_max_workers",
            help="并发线程数（1-10，默认 5）。多轮对话仍串行执行。",
            label_visibility="collapsed"
        )
```

所有 `mgr.run_background_job(...)` 调用（Run Range / Run Tags / Run Selected 处）都加 `max_workers=st.session_state.get("page_max_workers", 5)`。

#### 4. `app/ui/report.py` - Rerun / Continue 沿用并发数

Rerun (`app/ui/report.py:244`) 和 Continue (`app/ui/report.py:230`) 按钮
读取 `st.session_state.get("page_max_workers", 5)` 传入。

#### 5. Report 页 cancelled / interrupted 提示适配

现在的文案：
```
Cancelled {started}/{total_count} (remaining {remaining})
```
`started_count` 在 `_update_job_progress` 里递增，是 case 完成计数。
并发下每个 case 完成时仍会调 `on_step_complete`，`started_count` 仍能正确累计，
因此文案本身可以沿用。**唯一要注意**：
- 并发下"remaining"不再是"顺序前缀之后的部分"，而是"未完成集合"
- Continue 逻辑基于 `test_results` 表已存在的 `case_id` 计算 remaining（`job_manager.py` 内），
  这本身就是集合差集，不依赖顺序 —— 所以 continue 逻辑天然兼容并发

需要新增/调整：
- 在 report 的 cancelled/interrupted 提示里加一行说明：
  `"并发执行时已完成的用例不一定按 ID 顺序排列"`（可选，帮助用户理解）
- Continue 时同样传入 `max_workers`

## 影响文件

| 文件 | 修改类型 | 影响函数 |
| --- | --- | --- |
| `app/test_engine.py` | 修改 | `run_batch` 增加 `max_workers` 参数，单轮 cases 走线程池 |
| `app/job_manager.py` | 修改 | `run_background_job`, `_worker`, `continue_job` 增加 `max_workers` |
| `app/ui/testcases.py` | 修改 | Management row 加并发 slider；所有 `run_background_job` 调用带上 `max_workers` |
| `app/ui/report.py` | 修改 | Rerun / Continue 按钮读 `page_max_workers` 并传入 |

## 边界与异常处理

1. **线程安全**：
   - `results.append` 在 as_completed 循环里做，是主线程串行 append，无需锁
   - `completed_tasks` 用 `threading.Lock()` 保护
   - `on_step_complete` 里 `_update_job_progress` 会写 DB —— SQLAlchemy 通过 `SessionLocal()` 每次新 session，`_update_job_progress` 本来就是线程安全的（每次 with SessionLocal()）；如有 shared session 需要重构，先审代码
   - `run_case` 内部还有一个 `ThreadPoolExecutor(max_workers=2)`：总线程数上限 = 外层 N * 2 + 主 = 22，可接受

2. **Stop 生效延迟**：
   - `Future.cancel()` 只能取消尚未开始的任务，正在执行的 `run_case` 会跑完（因为 HTTP/LLM 是阻塞调用，Python 无法安全中断线程）
   - 用户点 Stop 后，主循环 break，池的 __exit__ 会等所有正在执行的任务返回；最长等待 = 一个 case 的耗时（~30s）
   - Report 页会显示 `cancelled` 状态

3. **异常隔离**：单个 case 抛异常不能拖垮整个池；`_wrap` 内捕获后返回错误 result

4. **DB 死锁 / 连接池打满**：
   - 并发上限 10，每个 `run_case` 内可能开一次 DB 事务；SQLAlchemy 默认 pool_size=5、max_overflow=10 —— 检查 `app/database.py` 的池配置，必要时上调
   - 如发现问题在实施阶段再补一个 task

5. **LLM QPS 限制**：默认 5、上限 10，用户可自主降为 1-3 规避 rate limit

## 数据流

```
Streamlit UI (testcases.py)
   ├─ selectbox: API
   └─ number_input: 并发数 N  (page_max_workers)
              │
              ▼
    mgr.run_background_job(cases, api_name, max_workers=N)
              │
              ▼
   JobManager._worker
              │
              ▼
   engine.run_batch(cases, ..., max_workers=N)
              │
       ┌──────┴───────┐
       ▼              ▼
  single_cases    grouped_cases (多轮)
  ThreadPool(N)   for 串行 (原逻辑)
       │              │
       └──────┬───────┘
              ▼
       on_step_complete(res, idx, total)
              │
              ▼
   _update_job_progress → test_results 表
```

Stop 数据流：
```
UI 点 Stop → mgr.cancel_job(report_id)
   → active_jobs[report_id]["cancelled"] = True
   → engine.run_batch 内 should_stop() == True
     → futures.cancel() 未开始的任务
     → break as_completed 循环
     → ThreadPool __exit__ 等待正在执行的返回
   → _worker 感知 should_stop() → _finalize_job(status="cancelled")
```

## 预期效果

| 场景 | 100 条 case（假设单条 20s） | 备注 |
| --- | --- | --- |
| 现在（串行） | ~2000s ≈ 33 min | |
| max_workers=5 | ~400s ≈ 7 min | 5x 加速 |
| max_workers=10 | ~200s ≈ 3.5 min | 10x 加速，需 API 支持 |

多轮 case 部分仍串行，如果多轮占比高整体加速比会下降。

## 测试要点（不落 spec，仅实施时自测）

- 单轮 100 条，`max_workers=5`：跑完时长约为串行的 1/5
- 混合单轮 + 多轮：多轮部分严格串行
- 点 Stop：所有线程尽快退出，report 显示 cancelled
- Continue：断点续跑，remaining case 用同样并发数继续
- Rerun：所有 case 重跑，用同样并发数
- 并发数改成 1：行为等价于原串行代码路径
