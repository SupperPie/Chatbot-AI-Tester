# Test Report 交互修复 - 总结

## 改动一览

### 1. `app/ui/report.py`
- **Q1**：`select_all_state` 由 `st.session_state.get(...)` 改为 `pop(...)`，勾选状态消费一次即清，避免每轮 rerun 覆盖用户勾选导致 data_editor 无法收敛。
- **Q2**：`⟳ Rerun` 按钮点击不再原地处理，改为设置 `pending_rerun_{entry_id}` flag；实际重跑逻辑下移到 `edited_df = st.data_editor(...)` 之后消费，按 `Select == True` 过滤 `edited_df`。空选择时提示"请先勾选"。

### 2. `app/test_engine.py`
- **Q3**：`run_multi_turn_case` 新增 `should_stop=None` 参数；phase 1 turn 循环起点判断 `if should_stop and should_stop(): break`。
- `run_batch` 调用多轮时透传 `should_stop=should_stop`。

## 静态验证

- `python3 -m py_compile app/ui/report.py app/test_engine.py app/job_manager.py` 通过。

## 待用户端到端验证

- Q1：连续勾选 checkbox 不再持续 loading，全选/取消按钮功能保持。
- Q2：勾选部分用例后 Rerun 只跑勾选；未勾选点 Rerun 显示 warning。
- Q3：多轮 case 中途 Stop，剩余 turn 不再调用；批处理外层已有 stop 检查，配合后作业能真正终止。

## 已知未覆盖

- `run_case` 内部单次 HTTP 请求进行中的强制中断：需要在 chat_client 各 `iter_lines` 循环里插入 stop 检查，代价更大，本次未纳入。
