# Stop Job 打分阶段中断任务计划

- [x] Task 1: `run_case` / `_run_semantic` / `_run_semantic_async` 加 `should_stop`
    - 1.1: `run_case` 签名增加 `should_stop=None`
    - 1.2: `_run_semantic_async` 接收 `should_stop`，在 correctness 与 faithfulness 之间检查
    - 1.3: `_run_semantic` 内 `asyncio.run` 时把 should_stop 传给 `_run_semantic_async`

- [x] Task 2: `run_batch` 透传 should_stop 到 run_case
    - 2.1: `_run_single_case_safe(case)` 通过闭包引用外层 should_stop，或增加参数
    - 2.2: 调用 `self.run_case(...)` 时传 `should_stop=should_stop`

- [x] Task 3: future.result 之后再判 stop
    - 3.1: `future.result(timeout=300)` 拿到结果后立刻 `if should_stop and should_stop(): break/return`
    - 3.2: 对取消场景返回时标记 `passed=False`，reason 简短说明

- [x] Task 4: 静态验证
    - 4.1: `python3 -m py_compile app/test_engine.py`
    - 4.2: 端到端待用户 UI 验证：Stop 后作业能较快收敛，无进度僵死
