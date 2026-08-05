# Parallel Test Execution 实施任务

- [x] Task 1: 改造 `TestEngine.run_batch` 支持并发（单轮 cases 并行、多轮保持串行）
    - 1.1: 新增参数 `max_workers: int = 1`
    - 1.2: 引入 `concurrent.futures.ThreadPoolExecutor` 与 `as_completed`
    - 1.3: 单轮 cases：`max_workers > 1 and len(single_cases) > 1` 时走线程池；否则走原串行路径
    - 1.4: 用 `_wrap(case)` 包裹 `run_case`，进入时先检查 `should_stop`，异常时兜底返回错误 result
    - 1.5: `completed_tasks` 用 `threading.Lock()` 保护；`on_step_complete` 传主线程递增后的 idx
    - 1.6: 主循环里检测 `should_stop()` 后，对未开始的 future 调 `f.cancel()` 并 break
    - 1.7: 多轮 `grouped_cases` for 循环保持原串行代码不动

- [x] Task 2: 改造 `JobManager`
    - 2.1: `run_background_job(...)` 增加 `max_workers: int = 5` 参数
    - 2.2: `active_jobs[report_id]` 存 `max_workers`（便于诊断）
    - 2.3: `_worker` 从 job 记录读取 `max_workers` 并传给 `engine.run_batch(..., max_workers=...)`
    - 2.4: `continue_job(...)` 同样支持 `max_workers` 参数并透传

- [x] Task 3: 在 `testcases.py` Management 行加并发 slider
    - 3.1: 在 `top_col1` 内拆分为 `sub1, sub2 = st.columns([2, 1])`
    - 3.2: `sub1` 放原 API `selectbox`（key=`page_api_select`）
    - 3.3: `sub2` 放 `st.number_input("并发", min=1, max=10, value=5, key="page_max_workers")`
    - 3.4: 所有 `mgr.run_background_job(...)` 调用（Run Range / Run Tags / Run Selected）加 `max_workers=st.session_state.get("page_max_workers", 5)`

- [x] Task 4: 在 `report.py` 的 Rerun / Continue 传递并发数
    - 4.1: Continue 按钮：`mgr.continue_job(entry_id, api_name=..., max_workers=st.session_state.get("page_max_workers", 5))`
    - 4.2: Rerun 按钮：`mgr.run_background_job(unique_cases_to_rerun, api_name=..., max_workers=st.session_state.get("page_max_workers", 5))`

- [x] Task 5: 兼容 Stop 提示与 Report 状态展示
    - 5.1: 验证 `_finalize_job(status="cancelled")` 在并发退出后能正常触发
    - 5.2: 在 report 页 cancelled/interrupted 说明里附一句"并发执行下已完成用例不一定按 ID 顺序"（用 `st.caption` 追加，避免破坏原有布局）

- [x] Task 6: 冒烟自测
    - 6.1: max_workers=1 → 行为与原串行一致（回归）
    - 6.2: max_workers=5 → 单轮 100 条明显加速，report 数据完整
    - 6.3: 混合单轮 + 多轮 → 多轮部分严格串行
    - 6.4: 执行中点 Stop → 池优雅退出，状态置为 cancelled
    - 6.5: Continue / Rerun → 沿用当前并发数运行
