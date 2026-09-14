# 统一 testcase 口径、字段对齐与运行弹窗修复 - 完成总结

## 完成情况

已完成 `tasks.md` 中全部 5 个顶层任务并勾选完成。

## 主要改动结果

### 1) 统计口径统一为 testcase id

- TestCases 页统计统一改为按 `id` 去重：
  - 总数、筛选数、已选数全部使用 unique testcase id。
  - 勾选行为改为按 case 生效：任意 turn 勾选/取消会同步同 case 的全部 turn；`Select page` 也按 case 批量勾选。
  - 相关文件：`app/ui/testcases.py`
- 目录树计数统一改为按 `id` 去重：
  - `func.count(distinct(TestCase.id))`
  - 相关文件：`app/ui/components/category_widget.py`
- 目录服务计数（删除检查、总数统计）改为按 `id` 去重：
  - 相关文件：`app/services/category_service.py`
- 报告与任务状态统计在后端统一按 `case_id` 去重：
  - `JobManager` 的 stale/progress/finalize 统计改为 `count(distinct case_id)`
  - `HistoryService` 的 save/update 汇总改为 case 维度
  - 相关文件：`app/job_manager.py`, `app/services/history_service.py`

## 2) TestCase/导入/Report 字段对齐

- 导入说明文案更新为完整字段矩阵口径：
  - 必填：`input`, `expected_output`
  - 可选：`id`, `description`, `priority`, `module`, `tags`, `type`, `turn_index`, `validation`, `overall_criteria`, `retrieval_context`, `assertions`
  - 相关文件：`app/ui/testcases.py`
- 导入时新增 `assertions` 归一化解析（字符串/空值→list）：
  - 相关文件：`app/ui/testcases.py`
- `docs/import_template.csv` 已对齐列头并补示例：
  - 新列包含 `assertions`

## 3) 新增 Actual_Output_CN（翻译落库链路）

- 数据模型新增字段：
  - `TestResult.actual_output_cn`
  - 相关文件：`app/models/test_history.py`
- 执行链路新增翻译：
  - 单轮：若 `actual_output` 非中文则尝试翻译到 `actual_output_cn`
  - 多轮：每个 turn 生成 `actual_cn`
  - 翻译失败不阻断主流程
  - 可通过 `ENABLE_ACTUAL_OUTPUT_CN` 环境变量控制开关（默认开启）
  - 相关文件：`app/test_engine.py`
- 写库/读库/展示链路打通：
  - JobManager 落库新增 `actual_output_cn`
  - HistoryService save/_entry_to_dict 增加字段透传
  - Report 表格新增 `Actual Output CN` 列
  - 相关文件：`app/job_manager.py`, `app/services/history_service.py`, `app/ui/report.py`
- 建表与迁移脚本更新：
  - `scripts/create_tables.sql` 增加 `test_results.actual_output_cn`
  - `scripts/migrate_module_report_name.py` 增加该列的幂等迁移

## 4) Run 弹窗确认后不自动关闭修复

- TestCases 页 Run 流程改为“待确认态”单次消费：
  - 点击 Run 按钮仅设置 `pending_run_dialog` 并 rerun
  - dialog confirm/cancel 后清理 `pending_run_dialog` 与 `run_report_name_input`
  - 避免 rerun 后反复命中 dialog 条件
  - 相关文件：`app/ui/testcases.py`

## 5) 回归与自检

已完成以下验证：

- 语法编译检查：
  - `python3 -m compileall` 覆盖核心改动文件并通过
- 导入模板检查：
  - `docs/import_template.csv` 列头包含 `assertions`
- 变更摘要确认：
  - 共修改 12 个文件（257 insertions, 60 deletions）

## 变更文件清单

- `app/ui/testcases.py`
- `app/ui/report.py`
- `app/ui/tester.py`
- `app/ui/components/category_widget.py`
- `app/services/category_service.py`
- `app/services/history_service.py`
- `app/job_manager.py`
- `app/test_engine.py`
- `app/models/test_history.py`
- `docs/import_template.csv`
- `scripts/create_tables.sql`
- `scripts/migrate_module_report_name.py`

## 注意事项

- 新增字段 `actual_output_cn` 需要先执行迁移脚本后再在生产环境稳定使用：
  - `python3 scripts/migrate_module_report_name.py`
- 历史旧报告如果是旧口径产生，新的统计逻辑会在新执行任务中统一为 testcase id 口径。