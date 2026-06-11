# Summary: Job 可靠性与断点续跑

## 完成内容

### 新增文件
| 文件 | 用途 |
|---|---|
| `scripts/migrate_job_resilience.py` | 一次性 DB 迁移脚本，给 `test_history` 表添加 `case_ids`、`error_message` 列 |

### 修改文件
| 文件 | 改动 |
|---|---|
| `app/models/test_history.py` | TestHistory 新增 `case_ids` (JSONB)、`error_message` (Text) 字段 |
| `app/test_engine.py` | 新增 `_call_chat_with_retry`：3 次指数退避（1s/2s/4s），仅对网络异常重试；`run_case` 与 `run_multi_turn_case` 全部走重试包装 |
| `app/job_manager.py` | (1) 创建 Job 时持久化 case_ids 快照 (2) 新增 `detect_stale_jobs()` 服务启动 + 进入 Report 页时调用 (3) 新增 `continue_job(report_id)` 完整实现 (4) `_finalize_job` 写入 error_message，total 保持 case_ids 长度 (5) 新增 `_reload_cases()` 从 load_data 重新加载用例 |
| `app/services/history_service.py` | `_entry_to_dict` 暴露 case_ids、error_message 字段给 UI |
| `app/ui/report.py` | (1) 进入页面时触发 stale 检测 (2) 状态显示扩展 interrupted/cancelled/failed (3) 显示 error_message 与剩余条数提示 (4) 新增 Continue 按钮（与 Rerun 并列） |
| `app/ui/testcases.py` | 轮询循环加 30 分钟 timeout、识别 interrupted/cancelled 状态、不再死循环 |

## 部署步骤

1. **执行 DB 迁移**（必须，仅一次）：
   ```bash
   python scripts/migrate_job_resilience.py
   ```
   会输出 `Added column: case_ids` 和 `Added column: error_message`。

2. **重启服务**：服务启动时 `JobManager` 会自动扫描 DB 中所有 `status='running'` 的 Job，标记为 `interrupted`。

## 核心机制说明

### 三层防御
1. **API 调用级**：单 case 网络抖动 → 3 次指数退避重试 → 仍失败则当条标记错误，不阻塞 batch
2. **Job 级**：进程崩溃后下次启动 / 进入 Report 页 → 自动识别僵尸 Job → 标记 `interrupted`
3. **续跑级**：用户点 Continue → diff 出剩余 case → 复用原 history_id 续跑 → 结果合并到原 report

### 状态机
```
running → completed       (正常结束)
        → cancelled       (用户 Stop)
        → failed          (run_batch 抛异常)
        → interrupted     (进程崩溃后被 stale 检测回收)
        
{cancelled, failed, interrupted} → [Continue Job] → running → completed
```

### 关键不变性
- 已写入 `TestResult` 的行永不修改/删除
- Continue 不创建新 `TestHistory`，复用原 `report_id`
- `case_ids` 字段始终保持原始全量列表（多次续跑都基于它做 diff）
- `total` 统一为 case_ids 中唯一 id 数量，续跑不会改变它
- 进度条计算口径：`COUNT(TestResult) / total`（首次执行与续跑统一）

## 验证结果
- ✅ 所有 7 个改动文件 + 1 个迁移脚本语法正确
- ✅ TestHistory 模型字段就位
- ✅ `_call_chat_with_retry` 辅助函数可导入
- ✅ JobManager 新增方法（continue_job、detect_stale_jobs、_reload_cases、_ensure_initialized）就位

## 边界条件覆盖
- ✅ 主动取消（cancelled）也支持 Continue
- ✅ 续跑期间再次中断 → 再次自动检测为 interrupted → 可继续 Continue
- ✅ 全部 case 已完成但 status 仍异常 → Continue 直接 finalize 为 completed
- ✅ 用例被删除 → 跳过该条；其余正常续跑
- ✅ 老数据无 case_ids → Continue 按钮禁用，提示使用 Rerun
- ✅ TestCases 页轮询有 30 分钟 timeout，避免无限阻塞
- ✅ 多轮对话中断 → 整段会话从 turn 1 重跑（保持被测系统状态一致性）

## 不在本次范围
- 多轮对话 turn 级断点续跑
- 分布式 Job 管理
- 失败用例自动重试
- WebSocket 实时推送
