# Stop Job 打分阶段中断改进

## 现状问题

`should_stop` 已覆盖 `run_batch` case 循环、`run_multi_turn_case` turn 循环。但 job 常卡在 DeepEval 打分（Faithfulness / Correctness / ConversationalGEval），因为：

- `_run_semantic_async`（`test_engine.py:484-519`）里 `correctness_m.a_measure` → `faithfulness_m.a_measure` 顺序 await，无 stop 检查。
- 打分包裹在 `concurrent.futures.ThreadPoolExecutor` future 中（`test_engine.py:529-540`），`future.result(timeout=300)` 无法真正取消已启动线程；`.a_measure` 内部 LLM 调用不响应 cancel。
- 因此 Stop 后 UI 看不到进度，但实际线程还在等 LLM。

## 改进方案（尽力而为，非硬中断）

### 影响文件

- `app/test_engine.py`

### 改动 1：`run_case` 接受 `should_stop`

签名改为：
```python
def run_case(self, case_data, api_name="Skills", execution_mode="full", should_stop=None):
```

在打分 future.result 之后立即判断 stop：若为真，跳过后续赋值直接返回带标记的结果。

### 改动 2：`_run_semantic_async` 两个 metric 之间检查 stop

```python
async def _run_semantic_async(tc, has_context, correctness_m, faithfulness_m, should_stop=None):
    await correctness_m.a_measure(tc)
    if should_stop and should_stop():
        return
    if has_context:
        await faithfulness_m.a_measure(tc)
```

至少能在 Correctness 打完后跳过 Faithfulness（Faithfulness 通常是耗时大头）。

### 改动 3：`_run_semantic` 把 should_stop 传入 asyncio.run

### 改动 4：run_batch 调用处传 should_stop 到 run_case 与 _run_single_case_safe

- `_run_single_case_safe(case)` 新增闭包 should_stop 参数或直接闭包捕获外层 should_stop。
- `self.run_case(case, api_name=..., execution_mode=..., should_stop=should_stop)` 透传。

### 改动 5：`future.result` 后再检查一次 stop

若 stop 为真，标记 `result["actual_output"] = "Cancelled by user"`，`passed=False`，`reason="cancelled"`。

### 无法覆盖的部分

- 单个 `a_measure` 调用进行中无法真正打断（DeepEval 内部 async task 若不被 cancel，只能等 LLM 返回）。
- 未来可考虑把 `asyncio.run` 改成手动 `loop.run_until_complete` + polling `task.cancel()`，或给 LLM 调用短超时。

## 期望效果

- Stop 后，当前正在跑 Correctness 的 case 结束后跳过 Faithfulness，快速进入下一次 case 循环的 stop 检查并退出；
- 整体停止耗时从"等所有 metric 全跑完"降低到"当前一个 metric 剩余时间"；
- 作业最终 `finalize` 为 `cancelled`，UI 状态回归。

## 不改动

- `chat_client.py`
- UI 层现有 Q1/Q2 修复
- `run_multi_turn_case` 的 ConversationalGEval 单次 `a_measure`（一个 metric，无 checkpoint 可插）
