# 多轮对话评分机制升级 - 使用 DeepEval ConversationalTestCase

## 需求背景

当前系统在多轮对话评分时，对每一轮单独使用 `LLMTestCase` + `GEval` 进行评分，导致多轮对话评分都是 0 分。原因是单轮评分缺少对话上下文，无法理解多轮对话的连贯性。

## 技术方案

采用 deepeval 官方推荐的多轮对话评分机制：
- 使用 `ConversationalTestCase` 封装整个对话
- 使用 `Turn` 对象表示每轮对话
- 使用 `ConversationalGEval` 进行整体评分

## 影响文件

| 文件路径 | 修改类型 | 影响范围 |
|---------|---------|---------|
| `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/test_engine.py` | 修改 | 导入新类、修改 `run_multi_turn_case` 方法 |

## 实现细节

### 1. 新增导入

```python
from deepeval.test_case import ConversationalTestCase, Turn
from deepeval.metrics import ConversationalGEval
```

### 2. 初始化 ConversationalGEval 指标

在 `TestEngine.__init__` 中新增：
```python
self.conversational_metric = ConversationalGEval(
    name="Correctness",
    criteria="Determine if the assistant's responses throughout the conversation are correct, helpful, and contextually appropriate based on the user's queries.",
    threshold=0.5,
    model=self.custom_model
)
```

### 3. 修改 run_multi_turn_case 方法

核心改动：
1. 先执行所有轮次的 API 调用，收集实际回复
2. 构建 `Turn` 列表（包含 user 和 assistant 的交替对话）
3. 创建 `ConversationalTestCase`
4. 使用 `ConversationalGEval` 进行整体评分
5. 保留单轮结果用于详细展示

```python
def run_multi_turn_case(self, case_data: Dict[str, Any], api_name: str = "Skills") -> Dict[str, Any]:
    # 1. 执行所有轮次的 API 调用
    turns_data = []
    has_error = False
    error_msg = ""
    
    for turn in conversation:
        actual_output = get_chat_response(...)
        
        # 检查是否为错误响应
        if actual_output.startswith("Error") or "Error calling API:" in actual_output:
            has_error = True
            error_msg = actual_output
            break  # 遇到错误直接停止
            
        turns_data.append({
            "user": user_message,
            "assistant": actual_output,
            ...
        })
    
    # 2. 如果有错误，直接返回错误结果，跳过评分
    if has_error:
        return {
            "case_id": case_data.get("id"),
            "error": error_msg,
            "passed": False,
            "score": 0,
            "reason": "API 调用失败，跳过评分",
            ...
        }
    
    # 3. 构建 ConversationalTestCase
    turns = []
    for t in turns_data:
        turns.append(Turn(role="user", content=t["user"]))
        turns.append(Turn(role="assistant", content=t["assistant"]))
    
    convo_test_case = ConversationalTestCase(
        scenario=case_data.get("description", "Multi-turn conversation test"),
        expected_outcome=...,  # 基于每轮 expected 构建
        turns=turns
    )
    
    # 4. 使用 ConversationalGEval 整体评分（只需 1 次 LLM 调用）
    await self.conversational_metric.a_measure(convo_test_case)
    overall_score = self.conversational_metric.score
    overall_reason = self.conversational_metric.reason
```

### 4. 保持向后兼容

- 保留 `turn_results` 数组用于前端展示每轮对话内容
- 单轮不再有独立评分（`score`/`reason` 为空），只记录 `user`/`actual`/`expected` 等基础信息
- `overall_score` 使用 ConversationalGEval 的结果（整体评分）
- 返回结构保持不变，确保前端报告页面兼容

## 数据流

```
用户触发多轮测试
    ↓
run_multi_turn_case 被调用
    ↓
循环执行每轮 API 调用 (保持 session_id 一致)
    ↓
收集所有轮次的 actual_output
    ↓
构建 ConversationalTestCase (Turn 列表)
    ↓
ConversationalGEval.a_measure() 整体评分
    ↓
返回结果 (整体分数 + 各轮详情)
```

## 边界条件

1. **deepeval 版本兼容**: 需要 deepeval >= 3.9.0 支持 ConversationalTestCase
2. **空对话**: 如果 conversation 为空，返回错误
3. **API 调用失败**: 任意一轮 API 调用失败时，直接返回错误结果，跳过评分（不浪费 LLM 调用）
4. **指标初始化失败**: 如果 ConversationalGEval 初始化失败，降级到单轮评分逻辑

## 性能优化

**原方案**: 每轮都调用 GEval 评分 → N 轮对话需要 N 次 LLM 评分调用

**新方案**: 仅做整体评分 → N 轮对话只需 1 次 LLM 评分调用

这意味着：
- 3 轮对话: 评分速度提升约 3 倍
- 5 轮对话: 评分速度提升约 5 倍
- 单轮的 `score`/`reason` 字段将为空，仅保留 `actual`/`expected` 等基础信息供查看

## 预期结果

- 多轮对话能获得合理的整体评分（不再是 0 分）
- 评分考虑对话上下文的连贯性
- 评分速度显著提升（只需 1 次 LLM 调用而非 N 次）
- 前端报告仍能展示每轮的详细对话内容（但单轮无独立评分）
