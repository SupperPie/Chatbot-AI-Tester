# Test Report 交互修复任务计划

- [✓] Task 1: 修复 Select 勾选持续 loading（Q1）
    - 1.1: 在 `app/ui/report.py:543` 把 `st.session_state.get(f"select_all_{entry_id}")` 改为 `st.session_state.pop(f"select_all_{entry_id}", None)`
    - 1.2: 验证：连续勾选/取消不再 loading，全选/取消按钮仍生效

- [✓] Task 2: Rerun 仅重跑勾选用例（Q2）
    - 2.1: 在 `mgmt_col3` 中把 `⟳ Rerun` 按钮点击行为改为设置 `st.session_state[f"pending_rerun_{entry_id}"] = True`，不再原地处理
    - 2.2: 在 `edited_df = st.data_editor(...)` 之后新增消费块：`st.session_state.pop(f"pending_rerun_{entry_id}", False)` 时按 `Select == True` 过滤 `edited_df` 生成 `res_df_curr`
    - 2.3: 迁移原 rerun 分支中的 case 收集 + `mgr.run_background_job(...)` 逻辑到新块内
    - 2.4: 空选择时 `st.warning` 提示"请先勾选至少一条用例"

- [✓] Task 3: Stop Job 真正中止（Q3）
    - 3.1: `app/test_engine.py:run_multi_turn_case` 签名增加 `should_stop=None`，在 turn 循环开头 `if should_stop and should_stop(): break`
    - 3.2: `run_batch` 调用 `run_multi_turn_case` 时透传 `should_stop=should_stop`
    - 3.3: `as_completed` 分支检测到取消时 `future.cancel()` 未完成的 futures 并 break
    - 3.4: 检查 `_run_single_case_safe` / 串行分支的 stop 检查是否完整

- [✓] Task 4: 静态与端到端验证
    - 4.1: `python -m py_compile app/ui/report.py app/test_engine.py app/job_manager.py`
    - 4.2: 手动验证 Q1 交互无 loading
    - 4.3: 手动验证 Q2：勾选 1 条 rerun 只跑该条；未勾选 rerun 报警告
    - 4.4: 手动验证 Q3：多轮 case 中途 stop，剩余 turn 不再执行；作业状态 finalize 为 cancelled
