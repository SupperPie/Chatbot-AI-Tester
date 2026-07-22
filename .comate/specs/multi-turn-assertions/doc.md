# 多轮对话断言组件执行功能设计文档

## 1. 需求背景

### 问题描述
用户反馈：在多轮对话测试用例中绑定的断言组件不生效，无法校验返回消息体中的关键字。

### 根因分析
通过代码分析发现：

1. **单轮测试** (`run_case` 方法):
   - test_engine.py:432-462 包含完整的断言执行逻辑
   - 调用 `AssertionEngine` 执行用例的 `assertions` 字段
   - 返回 `assertion_detail` 包含断言执行结果

2. **多轮测试** (`run_multi_turn_case` 方法):
   - test_engine.py:662-860 **完全缺失断言执行逻辑**
   - 只有 ConversationalGEval 的语义评分
   - 返回结果中没有 `assertion_detail` 字段

3. **数据传递问题**:
   - test_engine.py:636-644 在组装多轮对话时
   - 每一轮只传递了 `user`, `expected`, `validation`, `retrieval_context`
   - **没有传递 `assertions` 字段**

## 2. 技术方案

### 2.1 架构设计

#### 执行时机
- 在每一轮 API 调用完成后，立即执行该轮的断言组件
- 与单轮测试保持一致的断言执行逻辑
- 每轮独立执行断言，互不影响

#### 数据流
```
TestCase (multi_turn, assertions=[...])
  ↓
run_batch: 组装 conversation_turns (传递 assertions)
  ↓
run_multi_turn_case: 遍历每一轮
  ↓
每轮: API call → _extract_assertion_response → AssertionEngine.run
  ↓
汇总: turn_results (每轮包含 assertion_detail)
  ↓
返回结果: 整体断言统计 + 每轮详情
```

### 2.2 实现细节

#### 2.2.1 修改 `run_batch` 方法
**文件**: app/test_engine.py (636-644行)

**当前代码**:
```python
conversation_turns.append({
    "turn": row.get("turn_index", i + 1),
    "user": row.get("input", ""),
    "expected": row.get("expected_output", ""),
    "validation": row.get("validation", {"type": "semantic", "threshold": 0.5}),
    "retrieval_context": row.get("retrieval_context", []),
    "case_id": case_id
})
```

**修改为**:
```python
conversation_turns.append({
    "turn": row.get("turn_index", i + 1),
    "user": row.get("input", ""),
    "expected": row.get("expected_output", ""),
    "validation": row.get("validation", {"type": "semantic", "threshold": 0.5}),
    "retrieval_context": row.get("retrieval_context", []),
    "assertions": row.get("assertions"),  # 新增：传递断言配置
    "case_id": case_id
})
```

#### 2.2.2 修改 `run_multi_turn_case` 方法
**文件**: app/test_engine.py (662-860行)

**修改点 1**: 在每轮 API 调用后执行断言（插入到 771行后）

```python
# 当前 771 行后是直接 append turn_results
# 需要在此之前执行断言

# 执行该轮的断言组件（如果有）
turn_assertion_detail = None
assertion_refs = turn.get("assertions")

# 兼容字符串格式（与 run_case 保持一致）
if isinstance(assertion_refs, str):
    try:
        import json as _json_parse
        assertion_refs = _json_parse.loads(assertion_refs)
    except Exception:
        assertion_refs = None

if assertion_refs and not is_error:
    try:
        from app.validators.engine import AssertionEngine
        
        # 构建断言响应对象（使用与 run_case 相同的方法）
        _response_for_assert = self._extract_assertion_response(
            turn_raw_data, 
            actual_output,  # raw_response
            actual_output   # actual_output
        )
        
        # 执行断言引擎
        engine = AssertionEngine()
        engine_result = engine.run(_response_for_assert, assertion_refs)
        
        turn_assertion_detail = {
            "mode": "assertion",
            "passed": engine_result.passed,
            "score": engine_result.score,
            "total": engine_result.total,
            "passed_count": engine_result.passed_count,
            "results": [
                {
                    "id": r.component_id, 
                    "name": r.component_name,
                    "passed": r.passed, 
                    "message": r.message
                }
                for r in engine_result.results
            ]
        }
    except Exception as e:
        turn_assertion_detail = {
            "passed": False, 
            "score": 0, 
            "total": 0, 
            "passed_count": 0,
            "results": [{
                "id": "?", 
                "name": "error", 
                "passed": False, 
                "message": f"Assertion execution error: {str(e)}"
            }]
        }

# 添加到 turn_results
turn_results.append({
    "turn": turn_num,
    "user": user_message,
    "expected": expected,
    "actual": actual_output,
    "retrieval_context": ", ".join(context) if isinstance(context, list) else str(context or ""),
    "thinking": turn_thinking,
    "inform_base": turn_inform_base,
    "raw": turn_raw_data,
    "latency": turn_latency,
    "ttft": ttft,
    "assertion_detail": turn_assertion_detail  # 新增：断言执行结果
})
```

**修改点 2**: 在错误处理时也添加 assertion_detail 字段（757行）

```python
turn_results.append({
    "turn": turn_num,
    "user": user_message,
    "expected": expected,
    "actual": actual_output,
    "error": actual_output,
    "retrieval_context": ", ".join(context) if isinstance(context, list) else str(context or ""),
    "thinking": turn_thinking,
    "inform_base": turn_inform_base,
    "raw": turn_raw_data,
    "latency": turn_latency,
    "ttft": ttft,
    "assertion_detail": None  # 新增：错误时断言为空
})
```

**修改点 3**: 修改 `run_batch` 调用 `run_multi_turn_case` 时传递 execution_mode（653行）

```python
# 当前代码
res = self.run_multi_turn_case(base_case, api_name=api_name)

# 修改为
res = self.run_multi_turn_case(base_case, api_name=api_name, execution_mode=execution_mode)
```

**修改点 4**: 修改 `run_multi_turn_case` 方法签名（662行）

```python
# 当前签名
def run_multi_turn_case(self, case_data: Dict[str, Any], api_name: str = "Skills") -> Dict[str, Any]:

# 修改为
def run_multi_turn_case(self, case_data: Dict[str, Any], api_name: str = "Skills", execution_mode: str = "full") -> Dict[str, Any]:
```

**修改点 5**: 在返回结果时综合判定 passed（844-860行）

根据 execution_mode 和是否有断言，判定整体是否通过（与单轮测试保持一致的逻辑）：

```python
# Phase 3 语义评分后，计算整体 passed
# 先判断是否有任何一轮执行了断言
has_any_assertion = any(t.get("assertion_detail") is not None for t in turn_results)
all_assertions_passed = True

if has_any_assertion:
    # 检查所有有断言的轮次是否都通过
    for t in turn_results:
        if t.get("assertion_detail"):
            if not t["assertion_detail"].get("passed", False):
                all_assertions_passed = False
                break

# ─── 综合 passed 判定（与单轮测试逻辑一致）───
final_passed = False
if execution_mode == "assertion":
    # 只看断言：所有有断言的轮次都要通过
    final_passed = all_assertions_passed if has_any_assertion else True
elif execution_mode == "full":
    # 语义 + 断言：两者都要通过
    if has_any_assertion:
        final_passed = overall_passed and all_assertions_passed
    else:
        # 没有断言，只看语义
        final_passed = overall_passed
elif execution_mode == "semantic":
    # 只看语义
    final_passed = overall_passed

return {
    "case_id": case_data.get("id"),
    "input": input_text,
    "type": "multi_turn",
    "total_turns": num_turns,
    "passed_turns": num_turns if final_passed else 0,
    "success_rate": 1.0 if final_passed else 0.0,
    "score": overall_score,
    "reason": overall_reason,
    "overall_score": overall_score,
    "passed": final_passed,  # 使用综合判定结果
    "latency": sum(t.get("latency", 0) for t in turn_results),
    "ttft": sum(t.get("ttft", 0) for t in turn_results),
    "turns": turn_results,
    "user_id": user_id,
    "session_id": session_id
}
```

### 2.3 边界条件处理

1. **部分轮次有断言，部分没有**：
   - 只执行有断言配置的轮次
   - 没有断言的轮次 `assertion_detail` 为 None

2. **断言执行出错**：
   - 捕获异常，返回错误信息
   - 不中断后续轮次的执行

3. **API 调用失败**：
   - 不执行断言
   - `assertion_detail` 为 None

4. **与语义评分的关系**：
   - 断言和语义评分独立执行
   - 最终 `passed` 判定：两者都要通过（如果都存在）

### 2.4 Passed 判定逻辑

**与单轮测试保持一致**（参考 test_engine.py:558-563）：

| execution_mode | 断言配置 | Passed 判定逻辑 |
|---|---|---|
| "assertion" | 有断言 | 所有有断言的轮次都要通过 |
| "assertion" | 无断言 | True（默认通过）|
| "full" | 有断言 | 语义评分通过 **AND** 所有断言轮次通过 |
| "full" | 无断言 | 只看语义评分 |
| "semantic" | - | 只看语义评分 |

**代码示例**:
```python
# 判断是否有任何一轮执行了断言
has_any_assertion = any(t.get("assertion_detail") is not None for t in turn_results)
all_assertions_passed = all(
    t.get("assertion_detail", {}).get("passed", False) 
    for t in turn_results 
    if t.get("assertion_detail")
) if has_any_assertion else True

# 综合判定
if execution_mode == "assertion":
    final_passed = all_assertions_passed if has_any_assertion else True
elif execution_mode == "full":
    final_passed = overall_passed and all_assertions_passed if has_any_assertion else overall_passed
else:  # semantic
    final_passed = overall_passed
```

### 2.5 数据结构示例

**输入** (TestCase 数据库记录):
```json
{
  "id": "TC001",
  "type": "multi_turn",
  "assertions": [
    {"ref": "ASSERT_001", "params": {"keyword": "支付"}}
  ]
}
```

**输出** (turn_results 中的单个 turn):
```json
{
  "turn": 1,
  "user": "我想买这个产品",
  "expected": "询问支付方式",
  "actual": "好的，请问您想用什么方式支付？",
  "assertion_detail": {
    "mode": "assertion",
    "passed": true,
    "score": 1.0,
    "total": 1,
    "passed_count": 1,
    "results": [
      {
        "id": "ASSERT_001",
        "name": "关键字检查",
        "passed": true,
        "message": "包含关键字: 支付"
      }
    ]
  },
  "latency": 1.2,
  "ttft": 0.3
}
```

**输出** (整体结果):
```json
{
  "case_id": "TC001",
  "type": "multi_turn",
  "total_turns": 3,
  "passed": true,
  "overall_score": 0.85,
  "turns": [
    {
      "turn": 1,
      "assertion_detail": {"passed": true, ...}
    },
    {
      "turn": 2,
      "assertion_detail": {"passed": true, ...}
    },
    {
      "turn": 3,
      "assertion_detail": null
    }
  ]
}
```

**说明**: 不需要 `assertion_total`、`assertion_passed_count` 等汇总字段，每轮的断言结果在 `turns[].assertion_detail` 中，整体 `passed` 综合判定语义和断言。

## 3. 受影响的文件

### 主要文件
- **app/test_engine.py** (核心修改)
  - `run_batch` 方法：传递 assertions
  - `run_multi_turn_case` 方法：执行断言逻辑

### 可能需要调整的文件
- **app/ui/report.py**: 如果需要在报告页面展示多轮对话的断言详情
- **app/ui/testcases.py**: 如果需要调整测试结果的展示

## 4. 测试策略

### 4.1 单元测试场景
1. 多轮对话每一轮都有断言 → 全部执行
2. 多轮对话部分轮次有断言 → 只执行对应轮次
3. 多轮对话无断言 → assertion_detail 为 None
4. 断言执行出错 → 返回错误信息
5. API 调用失败 → 不执行断言

### 4.2 集成测试场景
1. 创建多轮对话用例，绑定断言组件
2. 执行测试，查看每一轮的断言结果
3. 验证整体 passed 判定逻辑：
   - execution_mode="full" + 有断言：语义和断言都要通过
   - execution_mode="full" + 无断言：只看语义
   - execution_mode="assertion"：只看断言
   - execution_mode="semantic"：只看语义

## 5. 预期效果

修复后：
- ✅ 多轮对话的每一轮都可以独立执行断言组件
- ✅ 返回结果包含每轮的断言详情（`turns[].assertion_detail`）
- ✅ 整体 `passed` 判定综合考虑语义和断言（与单轮测试逻辑一致）
- ✅ 支持三种 execution_mode：assertion / semantic / full
- ✅ 不需要额外的汇总统计字段，每轮独立展示

## 6. 风险评估

### 低风险
- 修改仅在 test_engine.py 内部
- 不影响单轮测试的现有逻辑
- 向后兼容：没有断言时行为不变

### 注意事项
- 断言执行可能增加测试耗时（每轮增加少量计算）
- 需要确保 AssertionEngine 的线程安全性
