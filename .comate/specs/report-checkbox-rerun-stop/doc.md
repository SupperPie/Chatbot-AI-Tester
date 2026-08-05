# Test Report 交互修复

## 需求

修复 Test Report 页面三个问题：
1. 勾选 `Select` checkbox 时整个 report widget 陷入持续 loading。
2. Rerun 按钮应该只重跑勾选用例，但实际重跑全部。
3. Stop Job 提示"开始停止"，但任务未真正停止。

## 根因分析

### Q1：Select 勾选后一直 loading（`app/ui/report.py:527-579`）

```python
select_all_state = st.session_state.get(f"select_all_{entry_id}")
if select_all_state is True:
    display_res_df["Select"] = True
elif select_all_state is False:
    display_res_df["Select"] = False
...
edited_df = st.data_editor(display_res_df, ..., key=f"hist_tbl_{entry_id}_v{tbl_key_suffix}")
```

`select_all_state` 未清除，每次 rerun 都把整列 Select 强制刷回原值，与用户 edited_rows 冲突，Streamlit 一直无法收敛 → 持续 loading。此外每次 rerun 触发 `service.get_by_id(entry_id)` 完整 DB 查询加重体验。

### Q2：Rerun 跑全部而非勾选（`app/ui/report.py:299-364`）

```python
if rerun_clicked:
    res_df_curr = pd.DataFrame(entry.get('results', []))   # ← 从 DB 全量取
    for _, row in res_df_curr.iterrows():                  # ← 遍历全部
        cases_to_rerun.append(...)
```

- Rerun 按钮位于 `mgmt_col3`（第 267 行前后），渲染顺序在 `edited_df` 之前，无法读取 data_editor 编辑态。
- 未按 `Select == True` 过滤。
- 同文件 668 行的 "Update Expect Result" 使用了正确写法：`selected_rows = edited_df[edited_df["Select"] == True]`。

### Q3：Stop Job 未真正停止

信号链路：
- UI `report.py:271` → `mgr.cancel_job(entry_id)`
- `job_manager.py:88` 设置 `active_jobs[report_id]["cancelled"] = True`
- `job_manager.py:213` 生成 `should_stop` 闭包传给 `engine.run_batch`
- `test_engine.py` 检查点：`613`（单条前）、`646-650`（`as_completed`）、`670`（串行）、`680`（多轮前）

缺失：
- `run_case` 内部 API 调用不检查 stop，长调用无法中断。
- `run_multi_turn_case`（`test_engine.py:721-800+`）的 `for turn in conversation:`（约 747）不检查 stop；`should_stop` 也未作为参数传入 `run_multi_turn_case`。
- `as_completed` 无法真正 `future.cancel()`，已启动线程会跑到结束。
- 结果：点 Stop 后，多轮 case 剩余 turn 仍继续；串行分支中单条跑到结束；`run_batch` 才返回并 `_finalize_job`，UI 状态一直 running。

## 修改方案

### 影响文件

- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/report.py`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/test_engine.py`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/job_manager.py`（若需暴露 should_stop 更多层）

### Q1 修复

将 `select_all_state` 读取改为 pop 消费一次即清，仅在点击"全选/取消"后的下一轮 rerun 起作用：
```python
select_all_state = st.session_state.pop(f"select_all_{entry_id}", None)
if select_all_state is True:
    display_res_df["Select"] = True
elif select_all_state is False:
    display_res_df["Select"] = False
```

### Q2 修复

选择方案 A：把 Rerun 按钮的执行分支从 `mgmt_col3` 处**推迟处理**到 data_editor 之后。按钮点击时先把标志写入 `st.session_state[f"pending_rerun_{entry_id}"] = True`，`edited_df` 生成之后再消费：

```python
# mgmt_col3
if st.button("⟳ Rerun", key=f"btn_rerun_{entry_id}", ...):
    st.session_state[f"pending_rerun_{entry_id}"] = True

# data_editor 之后
if st.session_state.pop(f"pending_rerun_{entry_id}", False):
    if edited_df is None or edited_df.empty:
        st.warning("No results to rerun.")
    else:
        selected = edited_df[edited_df["Select"] == True]
        if selected.empty:
            st.warning("Please select at least one case to rerun.")
        else:
            res_df_curr = selected
            # 原来的 case 收集与 mgr.run_background_job 逻辑保持
```

### Q3 修复

1. `TestEngine.run_multi_turn_case` 签名增加 `should_stop=None`，在多轮循环内每轮开头判断：
```python
def run_multi_turn_case(self, case_data, api_name="Skills", should_stop=None):
    ...
    for turn in conversation:
        if should_stop and should_stop():
            break
        ...
```
2. `run_batch` 调用多轮时把 `should_stop` 传入：
```python
res = self.run_multi_turn_case(base_case, api_name=api_name, should_stop=should_stop)
```
3. `as_completed` 分支中，取消后短路取消未完成 futures 并 break：
```python
if should_stop and should_stop():
    for f in futures:
        f.cancel()
    break
```
4. 说明：`requests.post` 已在进行中的 HTTP 长调用不可被强中断（除非改 `stream=True` 并在流循环内检查 stop），本次先覆盖多轮与批处理层的中止，长单调用截断留作后续。

## 边界与验证

- Q1：连续点勾选不再 loading；点"全选"后再手动取消某行仍生效。
- Q2：勾选 1 条 rerun 只跑该条；未勾选点 rerun 提示"请先勾选"。
- Q3：多轮 case 停止后不再继续下一轮；作业状态 `finalize` 为 `cancelled`。

## 不改动

- `chat_client.py` 单请求内部逻辑。
- 现有 Update Expect Result 分支（已正确）。
