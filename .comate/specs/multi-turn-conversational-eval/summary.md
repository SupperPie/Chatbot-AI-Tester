# 多轮对话评分机制升级 - 完成总结

## 修改内容

### 文件: `app/test_engine.py`

**1. 新增导入 (行 15-35)**
- `ConversationalGEval` - 多轮对话整体评分指标
- `ConversationalTestCase` - 多轮对话测试用例
- `Turn` - 对话轮次对象
- 添加导入失败时的兼容处理

**2. 初始化指标 (行 203-213)**
- 在 `TestEngine.__init__` 中新增 `self.conversational_metric`
- 使用自定义 LLM 模型进行评分
- 添加初始化失败的异常处理

**3. 重构 `run_multi_turn_case` 方法 (行 483-681)**
- 分两阶段执行：先收集所有 API 响应，再统一评分
- 遇到 API 错误时直接返回，跳过评分
- 使用 `ConversationalTestCase` + `ConversationalGEval` 进行整体评分
- 移除单轮评分逻辑，保留基础数据供前端展示

## 关键改进

| 方面 | 原方案 | 新方案 |
|-----|-------|-------|
| 评分方式 | 每轮单独评分 (GEval) | 整体评分 (ConversationalGEval) |
| LLM 调用次数 | N 次 (N = 轮次数) | 1 次 |
| 上下文感知 | 无 | 完整对话上下文 |
| 错误处理 | 继续评分 | 直接返回，跳过评分 |

## 未修改

- `run_case` 方法保持不变，单轮对话功能不受影响
- 返回结构兼容现有报告页面

## 测试建议

1. 运行一个多轮对话测试用例，验证评分不再为 0
2. 确认单轮对话测试功能正常
3. 测试 API 调用失败时的错误处理
