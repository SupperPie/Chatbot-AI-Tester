# Stop Job 打分阶段中断 - 总结

## 改动

`app/test_engine.py`：
1. `run_case(..., should_stop=None)` 新增参数。
2. `_run_semantic_async` 在 correctness `a_measure` 与 faithfulness `a_measure` 之间检查 `should_stop`；若已取消则跳过 faithfulness，直接以 correctness 得分返回。
3. `_run_semantic` 通过闭包引用外层 `should_stop`（run_case 参数），透传给 async 函数。
4. `run_batch`：
   - `_run_single_case_safe` 调用 `run_case` 时透传 `should_stop`。
   - 串行分支的 `self.run_case(...)` 也透传。
5. 打分 `future.result(timeout=300)` 拿到结果后立即判 `should_stop`，短路后续 futures。

## 静态验证

- `python3 -m py_compile app/test_engine.py` 通过。

## 效果预期

Stop 后：
- 新 case 不启动、新 turn 不启动（之前已实现）。
- 当前 case 正在跑的语义评分：Correctness 结束后立即跳过 Faithfulness，避免继续等 LLM 打分。
- 若 assertion 与 semantic future 尚未取回，取消后短路 break，job 可较快进入 finalize。

## 已知限制

- 单个 `.a_measure` 调用进行中无法真正打断（DeepEval 内部 asyncio 任务不接受外部 cancel）。若卡在 correctness 单次调用中，仍需等该次 LLM 返回。
- 未来改造方向：改用 `asyncio.wait([task], timeout=...)` + `task.cancel()`，或对 LLM 调用设更短超时。
