# 并发测试执行 - 完成总结

## 目标
让测试用例批量执行支持 1-10 并发，UI 上在 API 下拉旁提供 slider，默认 5。多轮对话保持串行；兼容 Stop/Continue/Rerun。

## 主要改动

### 1. `app/test_engine.py`
- `run_batch` 新增参数 `max_workers: int = 1`
- 单轮 cases：当 `max_workers > 1 且 case 数 > 1` 时走 `ThreadPoolExecutor` + `as_completed`
  - `_run_single_case_safe(case)` 包裹 `run_case`：入口检查 stop，异常兜底返回错误 result
  - `threading.Lock` 保护 `completed_tasks` 计数
  - 检测到 `should_stop()` 时对未启动的 future 调 `cancel()` 并 break
- 多轮 `grouped_cases`：保持原串行循环不动（同一 case_id 多轮之间有上下文依赖）
- `max_workers=1` 时走原串行代码路径，保证回归

### 2. `app/job_manager.py`
- `run_background_job(..., max_workers: int = 5)`
- `_worker(..., max_workers: int = 1)` 透传到 `engine.run_batch(..., max_workers=...)`
- `continue_job(report_id, max_workers: int = 5)` 同样支持
- `active_jobs[report_id]["max_workers"]` 便于诊断

### 3. `app/ui/testcases.py`
- Management 行 `top_col1` 内拆分为 `sub_api (2) + sub_workers (1)`
  - API selectbox 保持不变（`key="page_api_select"`）
  - 新增 `st.number_input("并发线程数", min=1, max=10, value=5, key="page_max_workers")`
- 唯一的 `mgr.run_background_job(...)` 调用带上 `max_workers=st.session_state.get("page_max_workers", 5)`

### 4. `app/ui/report.py`
- Continue 按钮 → `mgr.continue_job(entry_id, max_workers=...)`
- Rerun 按钮 → `mgr.run_background_job(..., max_workers=...)`
- Cancelled / Interrupted 提示追加 `st.caption`：说明并发下已完成用例不一定按 ID 顺序

## Stop / Rerun / Continue 行为

- **Stop**：点击后 `should_stop()` 立即返回 True → 未启动 future 全部 cancel → 正在运行的 task 自然跑完（Python 无法安全中断阻塞 I/O 线程，最长等 1 个 case 时长）→ `_finalize_job(status='cancelled')`
- **Continue**：从 DB 计算 remaining（集合差集，天然兼容并发），用当前 UI 上的 `max_workers` 启动新线程
- **Rerun**：创建新 `report_id`，用当前 UI 上的 `max_workers` 并发跑

## 预期加速

单条 case ~20s，100 条：
- 串行：~33 min
- max_workers=5：~7 min
- max_workers=10：~3.5 min

多轮 case 占比高时加速比会打折扣（多轮仍串行）。

## 验证

- 4 个改动文件 `ast.parse` 语法均通过
- 剩余功能验证（并发运行、Stop、Continue、Rerun）请在 Streamlit 中实际操作确认

## 重启命令

```bash
cd "/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester"
pkill -f ".venv/bin/streamlit run streamlit_app.py"
.venv/bin/streamlit run streamlit_app.py
```

## 注意事项 / 后续可选优化

1. **线程总数**：外层 N × 内层 `run_case` 的 2 = 最多 22 线程（N=10），可接受
2. **LLM QPS 限制**：如遇 rate limit，把并发调低到 1-3
3. **DB 连接池**：如出现连接紧张，检查 `app/database.py` 的 `pool_size` / `max_overflow`
4. **不同 case_id 的多轮之间是否可并行**：本次不做，保持串行；后续如需再单独立 spec
