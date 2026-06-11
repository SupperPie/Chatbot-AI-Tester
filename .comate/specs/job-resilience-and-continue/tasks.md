# Job 可靠性与断点续跑 - 任务计划

- [x] Task 1: 数据库模型扩展（TestHistory）
    - 1.1: 在 `app/models/test_history.py` 中新增 `case_ids` 字段（JSON，nullable）
    - 1.2: 在 `app/models/test_history.py` 中新增 `error_message` 字段（Text，nullable）
    - 1.3: 创建 Alembic 迁移脚本（或确认现有 schema auto-migrate 机制）添加这两列
    - 1.4: 验证模型变更不影响现有读写

- [x] Task 2: API 调用级 3 次指数退避重试
    - 2.1: 在 `app/test_engine.py` 中实现 `_call_with_retry` 辅助函数（仅对 ConnectionError/Timeout/RequestException 重试）
    - 2.2: 在 `run_case` 内调用 `get_chat_response` 处包装 retry
    - 2.3: 重试 3 次仍失败时，沿用现有错误处理（actual_output="Error after 3 retries: ..."），不阻塞 batch
    - 2.4: 在 `run_multi_turn_case` 的 turn 调用处同样包装 retry
    - 2.5: 验证瞬时异常下能自愈，业务 4xx 不被错误重试

- [x] Task 3: JobManager 持久化 case_ids 与首次 Job 创建改造
    - 3.1: 在 `run_background_job` 中构造 `case_ids_snapshot`（id + turn_index）
    - 3.2: 创建 TestHistory 时写入 `case_ids` 字段
    - 3.3: 验证首次执行流程未受影响

- [x] Task 4: 僵尸 Job 检测与回收
    - 4.1: 在 `JobManager` 中新增 `detect_stale_jobs()` 方法（status='running' 且不在 active_jobs 即标记 interrupted）
    - 4.2: 在 `JobManager.__init__` 中调用一次 `detect_stale_jobs()`，服务启动即时回收
    - 4.3: 修复 `_finalize_job` 把 `error` 参数实际写入 `error_message` 字段

- [x] Task 5: 实现 Continue Job 后端
    - 5.1: 在 `JobManager` 中新增 `continue_job(report_id) -> bool` 方法
    - 5.2: 实现校验逻辑（status 必须 ∈ {cancelled, interrupted, failed}，case_ids 非空）
    - 5.3: 实现 diff 计算 remaining keys（case_ids - 已存在的 TestResult）
    - 5.4: 实现"全部已完成"快捷路径：直接 finalize 为 completed，不启线程
    - 5.5: 实现 `_reload_cases(remaining_keys)` 从 `load_data()` / TestCaseService 重新加载用例
    - 5.6: 复用 `_worker` 启动续跑线程，复用原 report_id 写入 TestResult
    - 5.7: 续跑前更新 status='running'、清空 error_message
    - 5.8: 续跑结束后 `_finalize_job` 自动重新统计 total/passed/failed（保持 total = len(case_ids)）

- [x] Task 6: Report 页 UI 改造
    - 6.1: 进入 Report 页时调一次 `JobManager.detect_stale_jobs()`
    - 6.2: 状态展示扩展：interrupted（🔴 已中断 X/Y）、failed 显示 error_message
    - 6.3: 进度条计算改用 `COUNT(TestResult) / TestHistory.total`，统一首次执行与续跑
    - 6.4: 对 status ∈ {cancelled, interrupted, failed} 的 entry 显示已完成结果表（与 completed 行为一致）
    - 6.5: 新增 Continue Job 按钮（仅当 status ∈ {cancelled, interrupted, failed} 且仍有 remaining 时显示）
    - 6.6: Continue 按钮点击后调 `mgr.continue_job(report_id)` 并 rerun
    - 6.7: case_ids 为空（老数据）时禁用 Continue，提示"早于功能上线，请使用 Rerun"

- [x] Task 7: TestCases 页轮询循环改造
    - 7.1: 给 `while True` 加 30 分钟 timeout，超时跳出并提示去 Report 页查看
    - 7.2: 检测到 status == 'interrupted' 时立即跳出循环并提示可续跑
    - 7.3: 进度条文案改用 `COUNT(TestResult) / total` 口径

- [x] Task 8: 验证与回归
    - 8.1: 语法检查所有改动文件
    - 8.2: 验证首次执行流程仍正常（completed/cancelled）
    - 8.3: 模拟进程崩溃场景：手动 kill 进程后重启，验证僵尸 Job 被标记为 interrupted
    - 8.4: 验证 Continue 续跑后结果合并到原 report，total 保持不变
    - 8.5: 验证多轮对话中断后 Continue 能从整段会话重新跑
    - 8.6: 验证连续多次 Continue（续跑过程中再次中断）能继续 Continue
