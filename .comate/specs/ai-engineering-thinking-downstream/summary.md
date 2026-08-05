# AI Engineering thinking/result 下游渲染排查 - 总结

## 检查结论

从 `chat_client.get_ai_engineering_response` 返回到 UI 展示的整条链路均**未发现**将 thinking 混入 result 的代码：

| 环节 | 位置 | 结论 |
| --- | --- | --- |
| API 路由 | `chat_client.py:1568-1569` | `type=ai_engineering` 正确分发到 `get_ai_engineering_response` |
| 客户端拆分 | `chat_client.py:834-854` | 按 `is_thinking` 分别 append，done 空 content 不覆盖 |
| 单轮字段映射 | `test_engine.py:417-421` | `resp_data["result"] → actual_output`、`thinking` 独立 |
| 多轮字段映射 | `test_engine.py:788-792` | `resp_data["thinking"] → turn_thinking`，与 `actual_output` 分离 |
| UI 拆分 | `app/ui/report.py:428, 439` | `actual_output` 与 `thinking` 各占一列，独立渲染 |

## 推测的用户实测偏差原因

1. Streamlit 未重启，旧代码还在服务进程中。
2. 报告页显示的是**历史 entry**，其数据来自修复前的运行（旧行为把 done 帧整段 content 覆盖到 result）。
3. UI 上下拉/筛选选到了旧数据快照。

## 建议动作

- 重启 Streamlit（或热重载）后重新触发一次运行。
- 在报告页点新运行 entry（而非展开旧 entry）。
- 若仍然出现 result 里包含 thinking 内容，请把该 case 在 UI 上的实际 `actual_output` 值与 `thinking` 值分别贴出来，或提供该 entry 的 raw 字段，进一步定位。

## 无需改动的部分

- `chat_client.py`、`test_engine.py`、`app/ui/report.py` 现有实现均已正确分离两列。
