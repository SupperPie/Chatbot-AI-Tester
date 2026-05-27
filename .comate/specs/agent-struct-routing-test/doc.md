# Agent 结构体验证与路由逻辑测试框架设计

## 1. 需求概述

在现有语义检测基础上，设计一套**断言组件化**的测试框架，实现：

1. **断言组件库** — 可复用的最小断言单元，参数化定义，保存后可被任意测试用例引用
2. **API 结构体测试** — 通过组合断言组件，验证 Agent 返回 JSON 的字段存在性、类型、值
3. **Supervisor Agent 路由逻辑测试** — 验证路由分配正确性 + 对下游结果级联断言
4. **断言组件管理页面** — 专门的 UI 页面用于创建、编辑、预览断言组件

核心设计原则：**断言组件化、参数化引用、自由组合、渐进丰富**。

## 2. 现状分析

### 2.1 当前架构

```
TestEngine.run_case()
  → get_chat_response(input, api_name) → 返回 raw JSON string
  → 解析为 {result, thinking, inform_base, raw, ttft}
  → DeepEval GEval 语义评分
  → 返回 pass/fail
```

### 2.2 已有扩展点

- `TestCase.validation` 字段（Text 类型，存 JSON 字符串）已存在但未被 TestEngine 使用
- `chat_client.py` 返回完整 JSON 字符串，包含所有原始字段
- API 响应示例：`{"type": "token", "lob": "dc", "content": ".", "session_id": "151", "user_id": "123", "data": {}, "meta": {}}`

### 2.3 Supervisor Agent 特征

- API 类型: `ai_engineering`
- Supervisor 将用户请求路由到下游 Agent（Flight、Hotel、Limo、Entitlements 等）
- 路由结果体现在返回结构体的特定字段中

## 3. 断言组件化设计

### 3.1 核心概念

```
┌─────────────────────────────────────────────────────┐
│  断言组件 (Assertion Component)                      │
│  - 最小可复用的断言单元                               │
│  - 参数化：定义时用占位符，引用时填具体值               │
│  - 独立存储，有唯一 ID 和名称                         │
└─────────────────────────────────────────────────────┘
          ↓ 被引用
┌─────────────────────────────────────────────────────┐
│  测试用例 validation 字段                            │
│  - 引用 0~N 个断言组件                               │
│  - 每个引用可覆盖组件的参数值                         │
│  - 轻量 JSON 数组，不内联完整逻辑                     │
└─────────────────────────────────────────────────────┘
```

### 3.2 断言组件数据模型

```python
# app/models/assertion_component.py
class AssertionComponent(Base):
    __tablename__ = 'assertion_components'

    id = Column(String(50), primary_key=True)        # e.g., "AC001"
    name = Column(String(100), nullable=False)        # e.g., "检查 lob 字段值"
    description = Column(Text)                        # 说明用途
    category = Column(String(30), nullable=False)     # 大类: "field" / "structure" / "status_code" / "composite"
    condition = Column(String(30), nullable=False)    # 判断条件: "equals" / "contains" / "all_pass" 等
    config = Column(JSONB, nullable=False)            # 断言参数配置（原子组件为单条件，组合组件为 checks 数组）
    tags = Column(JSONB, default=list)                # 标签，便于筛选
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 3.2.1 组件粒度：原子组件 vs 组合组件

| 粒度 | category | 说明 | 适用场景 |
|------|----------|------|----------|
| **原子组件** | field / structure / status_code | 单个检查条件，高复用 | 手动创建的基础组件 |
| **组合组件** | composite | 内含多个检查条件，作为一个整体执行 | AI 生成的多条件断言、业务级校验 |

**原子组件 config 示例：**
```json
{
  "field": {"value": "lob", "mode": "preset"},
  "expected": {"value": "", "mode": "deferred"}
}
```

**组合组件 config 示例：**
```json
{
  "checks": [
    {"category": "structure", "condition": "required_fields", "params": {"path": ".", "fields": ["type","lob","content","data"]}},
    {"category": "field", "condition": "equals", "params": {"field": "lob", "expected": "dc"}},
    {"category": "field", "condition": "not_empty", "params": {"field": "content"}},
    {"category": "field", "condition": "length", "params": {"field": "data.flights", "operator": ">=", "value": 1}},
    {"ref": "AC004"}
  ]
}
```

**组合组件特性：**
- `checks` 数组中每项可以是：
  - **内联条件**：直接定义 category + condition + params
  - **引用已有组件**：`{"ref": "AC004"}` — 复用已有原子组件
- 执行时所有 checks AND 逻辑，全部通过才算通过
- 关联到测试用例时作为一个整体，只需引用一次

### 3.3 断言组件类型体系

断言类型分为三大类，每类下有不同的判断条件：

#### 大类一：field（字段值检查）

对 JSON 返回中指定字段的**值**进行断言。

| 判断条件 | 说明 | 示例 |
|----------|------|------|
| `equals` | 值等于指定值 | `lob == "DC"` |
| `not_equals` | 值不等于 | `status != "error"` |
| `contains` | 值包含子串 | `result` 包含 "航班" |
| `matches` | 值匹配正则 | 手机号格式 `^1[3-9]\d{9}$` |
| `in` | 值在枚举列表中 | `lob` in ["DC", "MC", "VI"] |
| `not_empty` | 值非空 | `content` 不为空字符串/null |
| `type` | 值的类型 | `data` is object，`flights` is array |
| `gt` / `gte` / `lt` / `lte` | 数值比较 | `price > 0`，`count >= 1` |
| `length` | 数组/字符串长度 | `flights.length >= 1` |

创建组件时选择：大类 = `field`，然后选判断条件。

#### 大类二：structure（结构检查）

验证 JSON 返回体的**整体结构**是否符合预期。

| 判断条件 | 说明 | 示例 |
|----------|------|------|
| `path_exists` | 指定路径是否存在 | `data.summary_state.details` 路径存在 |
| `required_fields` | 某层级是否包含所有必需字段 | 顶层必须有 `type`, `lob`, `content`, `data` |
| `field_count` | 某层级字段数量 | `data` 下至少有 2 个字段 |
| `array_not_empty` | 指定数组路径非空 | `data.flights` 数组有至少 1 个元素 |
| `nested_structure` | 嵌套对象的结构校验 | `data.flights[*]` 每个元素都必须有 `price` 和 `airline` |

#### 大类三：status_code（状态码检查）

验证 HTTP 响应的状态码。

| 判断条件 | 说明 | 示例 |
|----------|------|------|
| `equals` | 状态码等于 | `status_code == 200` |
| `in_range` | 状态码在范围内 | `status_code` in [200, 201, 202] |
| `not_equals` | 状态码不等于 | `status_code != 500` |

> **注意**：status_code 需要 `chat_client.py` 在返回中包含 HTTP 状态码信息（当前返回仅有 body，需扩展）。

#### 数据模型中的类型字段

```python
class AssertionComponent(Base):
    ...
    category = Column(String(30))   # 大类: "field" / "structure" / "status_code"
    condition = Column(String(30))  # 判断条件: "equals" / "contains" / "path_exists" 等
    config = Column(JSONB)          # 参数配置
```

#### UI 编辑时的选择流程

```
第一步: 选择大类
  [field ▼]  [structure]  [status_code]

第二步: 选择判断条件（根据大类动态切换选项）
  大类=field 时:    [equals ▼] [contains] [matches] [in] [not_empty] [type] [gt/gte/lt/lte] [length]
  大类=structure:  [path_exists ▼] [required_fields] [array_not_empty] [nested_structure]
  大类=status_code: [equals ▼] [in_range] [not_equals]

第三步: 配置参数（根据大类+条件动态渲染表单）
```

### 3.4 断言组件参数模型

组件的每个参数有两种模式：

| 模式 | 说明 | 场景 |
|------|------|------|
| **预设值 (preset)** | 定义组件时就写死值 | 通用固定逻辑，如"result 字段必须存在" |
| **延迟绑定 (deferred)** | 定义时留空，关联测试用例时再填 | 灵活参数，如"lob 等于什么值由用例决定" |

#### 组件 config 结构

```json
{
  "field": {"value": "lob", "mode": "preset"},
  "expected": {"value": "", "mode": "deferred"}
}
```

- `mode: "preset"` + `value` 已填写 → 直接使用，关联时不需要再填
- `mode: "deferred"` + `value` 为空 → 关联测试用例时必须提供值

#### 示例：同一类型两种用法

**组件 A：固定检查 result 字段存在**（无需填参数）
```json
{
  "name": "result 字段必须存在",
  "type": "field_exists",
  "config": {
    "field": {"value": "result", "mode": "preset"}
  }
}
```
关联时：直接选中即可，无需填写任何参数。

**组件 B：检查指定字段等于指定值**（关联时填参数）
```json
{
  "name": "字段值等于",
  "type": "field_equals",
  "config": {
    "field": {"value": "", "mode": "deferred"},
    "expected": {"value": "", "mode": "deferred"}
  }
}
```
关联时：需要填写 `field = "lob"`, `expected = "DC"`。

**组件 C：混合模式 — 字段固定，值灵活**
```json
{
  "name": "lob 值检查",
  "type": "field_equals",
  "config": {
    "field": {"value": "lob", "mode": "preset"},
    "expected": {"value": "", "mode": "deferred"}
  }
}
```
关联时：只需填写 `expected = "DC"`。

### 3.5 测试用例 validation 字段格式

测试用例的 `validation` 字段变为**断言引用数组**：

```json
[
  {"ref": "AC001", "params": {}},
  {"ref": "AC003", "params": {"field": "lob", "expected": "DC"}},
  {"ref": "AC003", "params": {"field": "content", "expected": "hello"}}
]
```

- `params` 中只需提供 `mode: "deferred"` 的参数值
- `mode: "preset"` 的参数不需要出现在 params 中
- 数组为空或 null → 无断言组件，仅走语义检测

### 3.6 评分逻辑与执行模式

#### 执行模式选择

在执行测试时，用户可选择执行模式：

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| **语义检测** | 仅做 DeepEval 语义评分（现有默认） | 关注回答内容质量 |
| **仅断言** | 仅执行断言组件，跳过语义检测 | 关注结构/路由正确性，速度快 |
| **完整检测** | 断言 + 语义同时执行 | 需要全面验证的场景 |

在 UI 上体现为：执行测试时的一个下拉/Radio 选择项。

#### 评分规则

```
模式: 语义检测 (无断言组件 或 用户选择仅语义)
    passed = semantic_score >= 0.5
    score = semantic_score

模式: 仅断言
    passed = 所有断言组件全部通过 (AND 逻辑)
    score = 通过数 / 总数
    # 不调用 DeepEval，执行速度快

模式: 完整检测 (有断言组件 + 用户未选仅断言)
    struct_passed = 所有断言组件全部通过 (AND 逻辑)
    semantic_passed = semantic_score >= 0.5
    passed = struct_passed AND semantic_passed
    score = struct_score * 0.4 + semantic_score * 0.6
```

#### 模式自动推断

如果用户未主动选择模式，系统按以下规则自动推断：
- 测试用例无断言组件 → 语义检测模式
- 测试用例有断言组件 → 完整检测模式
- 用户手动选择 → 以用户选择为准（可覆盖自动推断）

## 4. 断言组件管理页面设计

### 4.1 设计原则

- 组件以**卡片形式**展示，而非表格/列表，因为每个组件有结构化的配置需要可视化
- 编辑采用**表单驱动**，根据选择的断言类型动态渲染对应的参数输入项
- 每个参数都有 preset/deferred 切换，直观展示哪些值已固定、哪些需要关联时填写

### 4.2 页面整体布局

新增 Streamlit 页面 `app/ui/assertions.py`：

```
┌─────────────────────────────────────────────────────────────────────┐
│  断言组件库                                           [+ 创建组件]    │
├─────────────────────────────────────────────────────────────────────┤
│  筛选: [全部类型 ▼]  [全部标签 ▼]   搜索: [___________]             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌────────────┐ │
│  │ AC001               │  │ AC002               │  │ AC003      │ │
│  │ ━━━━━━━━━━━━━━━━━━  │  │ ━━━━━━━━━━━━━━━━━━  │  │ ━━━━━━━━━ │ │
│  │ result 字段必须存在  │  │ lob 值检查          │  │ 路由目标   │ │
│  │                     │  │                     │  │ 检查       │ │
│  │ 类型: field_exists  │  │ 类型: field_equals  │  │            │ │
│  │ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  │  │ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  │  │ 类型:     │ │
│  │ field: "result" [固] │  │ field: "lob"  [固]  │  │route_equal│ │
│  │                     │  │ expected: ___  [活]  │  │ ┄┄┄┄┄┄┄┄ │ │
│  │ 引用: 12 个用例     │  │                     │  │ route_fiel│ │
│  │ [编辑] [测试] [删除] │  │ 引用: 5 个用例      │  │ d: ___ [活│ │
│  └─────────────────────┘  │ [编辑] [测试] [删除] │  │ expected_r│ │
│                           └─────────────────────┘  │ oute: _[活]│ │
│                                                    │            │ │
│                                                    │ 引用: 3个  │ │
│                                                    │[编辑][测试]│ │
│                                                    └────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.3 组件卡片展示

每张卡片展示：
- **标题行**：组件 ID + 名称
- **类型徽章**：`field_exists` / `field_equals` / `route_equals` 等，不同颜色区分
- **参数预览**：
  - `[固]` 标记 = preset，已有值，灰色底色，显示具体值
  - `[活]` 标记 = deferred，需关联时填写，虚线边框，显示参数名
- **引用统计**：被多少测试用例引用
- **操作按钮**：编辑、测试预览、删除

### 4.4 组件创建/编辑表单

点击「创建组件」或卡片上的「编辑」按钮，展开编辑区域（使用 `st.expander` 或 modal）：

```
┌─────────────────────────────────────────────────────────┐
│  创建断言组件                                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  组件名称: [检查 lob 字段值_______________]              │
│                                                         │
│  断言类型: [field_equals ▼]                             │
│            ┌──────────────────┐                         │
│            │ field_exists     │                         │
│            │ field_equals     │  ← 选中后动态渲染       │
│            │ field_type       │     下方参数表单         │
│            │ field_contains   │                         │
│            │ field_in         │                         │
│            │ field_not_empty  │                         │
│            │ field_matches    │                         │
│            │ route_equals     │                         │
│            └──────────────────┘                         │
│                                                         │
│  ─── 参数配置 ──────────────────────────────────────     │
│                                                         │
│  参数: field                                            │
│  ┌──────────────────────────────────────────┐           │
│  │  模式: (●) 预设值  ( ) 关联时填写         │           │
│  │  值:   [lob________________________]     │           │
│  └──────────────────────────────────────────┘           │
│                                                         │
│  参数: expected                                         │
│  ┌──────────────────────────────────────────┐           │
│  │  模式: ( ) 预设值  (●) 关联时填写         │           │
│  │  提示文字: [请输入期望的字段值_____]       │           │
│  └──────────────────────────────────────────┘           │
│                                                         │
│  标签: [结构检查] [字段验证] [+]                         │
│  描述: [验证返回体中 lob 字段是否等于指定值___]          │
│                                                         │
│  [保存]  [取消]                                         │
└─────────────────────────────────────────────────────────┘
```

**关键交互：**
1. 选择「断言类型」后，表单根据类型定义动态渲染该类型需要的参数列表
2. 每个参数有 Radio 切换：「预设值」vs「关联时填写」
   - 选「预设值」→ 显示 text_input 填写固定值
   - 选「关联时填写」→ 显示 text_input 填写提示文字（帮助关联时理解要填什么）
3. 保存时验证必填项

### 4.5 各断言类型的参数定义

每种类型需要哪些参数（决定编辑表单渲染什么）：

| 类型 | 参数 | 说明 |
|------|------|------|
| `field_exists` | `field` | 要检查的字段路径 |
| `field_equals` | `field`, `expected` | 字段路径 + 期望值 |
| `field_type` | `field`, `expected_type` | 字段路径 + 期望类型(string/number/object/array/boolean) |
| `field_contains` | `field`, `substring` | 字段路径 + 包含子串 |
| `field_matches` | `field`, `pattern` | 字段路径 + 正则表达式 |
| `field_in` | `field`, `options` | 字段路径 + 可选值列表 |
| `field_not_empty` | `field` | 要检查的字段路径 |
| `route_equals` | `route_field`, `expected_route` | 路由字段路径 + 期望路由目标 |
| `nested_check` | `path`, `check_type`, 动态子参数 | 嵌套路径 + 子断言类型及参数 |

### 4.6 自然语言一键生成断言

在组件管理页面顶部提供「AI 生成」区域：

```
┌─────────────────────────────────────────────────────────────────┐
│  AI 生成断言                                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  API 响应示例 (粘贴实际返回的 JSON):                              │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ {"type":"token","lob":"dc","content":"您好，已为您查询", │    │
│  │  "session_id":"151","user_id":"123","data":{"flights":  │    │
│  │  [{"price":1200,"airline":"CA"}]},"meta":{}}            │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  断言需求描述 (自然语言):                                         │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 我要检查 lob 字段等于 dc，content 不为空，                │    │
│  │ data.flights 是数组且至少有一个元素                        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  [一键生成]                                                      │
│                                                                 │
│  ─── 生成结果 ──────────────────────────────────────────────     │
│                                                                 │
│  生成了 3 个断言组件:                                             │
│                                                                 │
│  ┌───────────────────────────────────────┐                      │
│  │ 1. lob 值等于 dc                      │                      │
│  │    类型: field_equals                  │                      │
│  │    field: "lob" [固]                   │                      │
│  │    expected: "dc" [固]                 │                      │
│  │    [保存为组件] [修改为活参数]          │                      │
│  └───────────────────────────────────────┘                      │
│  ┌───────────────────────────────────────┐                      │
│  │ 2. content 不为空                     │                      │
│  │    类型: field_not_empty               │                      │
│  │    field: "content" [固]               │                      │
│  │    [保存为组件] [修改为活参数]          │                      │
│  └───────────────────────────────────────┘                      │
│  ┌───────────────────────────────────────┐                      │
│  │ 3. data.flights 是非空数组            │                      │
│  │    类型: field_type                    │                      │
│  │    field: "data.flights" [固]          │                      │
│  │    expected_type: "array" [固]         │                      │
│  │    + field_not_empty 检查              │                      │
│  │    [保存为组件] [修改为活参数]          │                      │
│  └───────────────────────────────────────┘                      │
│                                                                 │
│  [全部保存]  [验证运行]                                          │
│                                                                 │
│  ─── 验证运行结果 ──────────────────────────────────────────     │
│  对输入的 API 响应执行生成的断言:                                  │
│  1. lob 值等于 dc          → PASS                               │
│  2. content 不为空         → PASS                               │
│  3. data.flights 是非空数组 → PASS                               │
│  全部通过 (3/3)                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**关键设计：**

1. **输入**：API 响应 JSON + 自然语言描述
2. **生成**：调用项目已有的评估 LLM（Qwen3-max，复用 `SynchronousEvalModel`），无需额外 skill 或外部服务
3. **去重匹配**：生成后自动与组件库现有组件对比，标注哪些已存在可复用、哪些是新条件
4. **本地验证**：用输入的 JSON 样本在本地执行断言逻辑，不调用真实 API
5. **可调整**：生成后可修改参数模式（preset → deferred），或手动编辑
6. **保存选项**：
   - 「保存为组合组件」— 整体打包为一个 composite 组件（内部引用已有 + 新建）
   - 「仅保存新条件」— 已有组件跳过，只保存库里没有的原子组件
   - 「全部保存为独立组件」— 忽略去重，全部另存

### 4.6.1 AI 生成去重匹配逻辑

AI 生成断言条件后，执行去重检查流程：

```
AI 生成 N 个断言条件
    ↓
逐条与组件库匹配:
  匹配规则: category + condition + 关键参数(preset值) 完全一致
    ↓
展示标注结果:
  ✅ 已有组件 (可复用): 显示匹配到的组件 ID 和名称
  ⭐ 新条件 (库中无): 标记为待保存
```

**匹配算法：**
```python
def find_matching_component(check, existing_components):
    """查找是否已有匹配的组件"""
    for comp in existing_components:
        if comp.category != check["category"]:
            continue
        if comp.condition != check["condition"]:
            continue
        # 对比关键参数 (只比较 preset 值)
        if _params_match(comp.config, check["params"]):
            return comp
    return None

def _params_match(comp_config, check_params):
    """比较组件的 preset 参数与生成的参数是否一致"""
    for key, value in check_params.items():
        comp_param = comp_config.get(key, {})
        if comp_param.get("mode") == "preset":
            if comp_param.get("value") != value:
                return False
    return True
```

**UI 展示效果：**

```
生成了 5 个断言条件:

1. 顶层必需字段 [structure / required_fields]
   ✅ 已有: AC003 "顶层必需字段检查" → [复用]

2. lob 等于 dc [field / equals]
   ✅ 已有: AC002 "lob值检查" (活参数 expected) → [复用, expected=dc]

3. content 不为空 [field / not_empty]
   ✅ 已有: AC004 "content不为空" → [复用]

4. data.flights 长度 >= 1 [field / length]
   ⭐ 新条件 → [保存为新组件]

5. data.flights[0].price 路径存在 [structure / path_exists]
   ⭐ 新条件 → [保存为新组件]

─────────────────────────────
保存选项:
  [保存为组合组件] — 创建 1 个 composite，引用 AC003+AC002+AC004 + 新建 2 个原子组件
  [仅保存新条件] — 只新建条件 4、5 为独立原子组件
  [全部保存为独立组件] — 新建 5 个独立原子组件（允许重复）
```

**实现方式**：和 `app/ui/tester.py` 中 AI 生成测试用例同一模式 — 给 LLM 输入结构化 prompt，输出 JSON 格式的断言组件定义。

**LLM Prompt 模板：**

```python
ASSERTION_GEN_PROMPT = """
你是一个断言组件生成器。根据用户提供的 API 响应示例和断言需求，
生成一组可独立运行的断言组件定义。

API 响应示例:
{api_response}

用户需求:
{user_description}

断言类型体系:
- 大类 "field": 字段值检查。条件: equals/not_equals/contains/matches/in/not_empty/type/gt/gte/lt/lte/length
- 大类 "structure": 结构检查。条件: path_exists/required_fields/field_count/array_not_empty/nested_structure
- 大类 "status_code": 状态码检查。条件: equals/in_range/not_equals


请生成断言组件列表，每个组件格式如下:
{{
  "name": "简短描述",
  "category": "field|structure|status_code",
  "condition": "具体判断条件",
  "config": {{
    // 根据 category + condition 填写参数
    // 每个参数: {{"value": "具体值", "mode": "preset"}}
  }}
}}

要求:
1. 每个断言必须能独立运行
2. 多个断言串行执行时不能互相冲突
3. 字段路径支持点分隔嵌套 (如 data.flights[0].price)
4. 返回 JSON 数组格式
"""
```

### 4.7 组件测试预览

每张组件卡片都有「测试」按钮，点击后展开预览区：

```
┌─────────────────────────────────────────────────────────┐
│  测试预览: AC002 "lob 值检查"                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  模拟 API 返回 (JSON):                                   │
│  ┌─────────────────────────────────────────────────┐    │
│  │ {"type":"token","lob":"dc","content":".","data":{}} │  │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  填写活参数:                                             │
│    expected: [DC_____________]                           │
│                                                         │
│  [执行测试]                                              │
│                                                         │
│  结果: PASS                                             │
│  详情: 'lob' = 'dc', expected 'DC'                      │
│        (注: 当前为大小写敏感比较)                         │
└─────────────────────────────────────────────────────────┘
```

### 4.7 测试用例页面的关联交互

在测试用例管理页面（`app/ui/testcases.py`），validation 列的交互：

1. 点击 validation 单元格 → 弹出「断言组件选择器」
2. 选择器展示所有可用组件（卡片缩略图形式）
3. 点击组件添加到当前用例，如果有 deferred 参数则展开参数填写表单
4. 已关联的组件以 tag/chip 形式展示在单元格中
5. 支持拖拽排序、移除

```
validation 列显示:
┌─────────────────────────────────────────────┐
│ [result存在 ×] [lob=DC ×] [路由=flight ×]   │
│                              [+ 添加断言]    │
└─────────────────────────────────────────────┘
```

## 5. 核心模块设计

### 5.1 文件结构

```
app/
├── models/
│   └── assertion_component.py    # [新建] 断言组件 ORM 模型
├── services/
│   └── assertion_service.py      # [新建] 断言组件 CRUD 服务
├── validators/
│   ├── __init__.py               # [新建] 验证器包
│   ├── base.py                   # [新建] BaseValidator + ValidationResult
│   ├── field_validators.py       # [新建] field_exists/equals/type/contains/matches/in/not_empty
│   ├── routing_validator.py      # [新建] route_equals 验证器
│   └── engine.py                 # [新建] 断言引擎：解析 validation 数组，加载组件，执行断言
├── ui/
│   └── assertions.py             # [新建] 断言组件管理页面
├── test_engine.py                # [修改] 集成断言引擎
└── ...
```

### 5.2 断言引擎 (Validation Engine)

```python
# app/validators/engine.py
import json
from typing import List, Dict, Any, Optional
from app.validators.base import ValidationResult
from app.services.assertion_service import AssertionService

class AssertionEngine:
    """断言执行引擎：解析 validation 引用列表，加载组件，执行断言"""

    VALIDATOR_MAP = {
        "field_exists": FieldExistsValidator,
        "field_equals": FieldEqualsValidator,
        "field_type": FieldTypeValidator,
        "field_contains": FieldContainsValidator,
        "field_matches": FieldMatchesValidator,
        "field_in": FieldInValidator,
        "field_not_empty": FieldNotEmptyValidator,
        "route_equals": RouteEqualsValidator,
        "nested_check": NestedCheckValidator,
    }

    def __init__(self):
        self.assertion_service = AssertionService()

    def run(self, response_data: Dict[str, Any], validation_refs: List[Dict]) -> ValidationResult:
        """
        执行断言列表
        Args:
            response_data: API 返回解析后的完整 dict
            validation_refs: [{"ref": "AC001", "params": {"value": "DC"}}, ...]
        Returns:
            综合 ValidationResult
        """
        if not validation_refs:
            return None  # 无断言，交给原有语义检测

        results = []
        needs_semantic = False

        for ref_item in validation_refs:
            component_id = ref_item.get("ref")
            params = ref_item.get("params", {})

            # 从 DB 加载组件定义
            component = self.assertion_service.get_by_id(component_id)
            if not component:
                results.append(ValidationResult(
                    passed=False, score=0.0,
                    reason=f"Assertion component '{component_id}' not found"
                ))
                continue

            if component.type == "semantic":
                needs_semantic = True
                continue  # 语义断言由 TestEngine 处理

            # 渲染参数：将 {{param}} 替换为实际值
            rendered_config = self._render_params(component.config, params)

            # 执行断言
            validator_cls = self.VALIDATOR_MAP.get(component.type)
            if validator_cls:
                result = validator_cls().validate(response_data, rendered_config)
                result.details["component_id"] = component_id
                result.details["component_name"] = component.name
                results.append(result)

        # 综合结果
        if not results:
            return None

        all_passed = all(r.passed for r in results)
        score = sum(r.score for r in results) / len(results)
        reasons = [f"[{r.details.get('component_name', '?')}] {r.reason}" for r in results]

        return ValidationResult(
            passed=all_passed,
            score=score,
            reason=" | ".join(reasons),
            details={
                "results": [{"component": r.details.get("component_id"),
                             "passed": r.passed, "reason": r.reason} for r in results],
                "needs_semantic": needs_semantic
            }
        )

    def _render_params(self, config: dict, params: dict) -> dict:
        """递归替换 config 中的 {{param}} 占位符"""
        rendered = {}
        for key, value in config.items():
            if isinstance(value, str):
                for param_name, param_value in params.items():
                    value = value.replace(f"{{{{{param_name}}}}}", str(param_value))
                rendered[key] = value
            elif isinstance(value, dict):
                rendered[key] = self._render_params(value, params)
            else:
                rendered[key] = value
        return rendered
```

### 5.3 字段验证器实现

```python
# app/validators/field_validators.py
from app.validators.base import BaseValidator, ValidationResult

class FieldExistsValidator(BaseValidator):
    """检查字段是否存在"""
    def validate(self, response_data: dict, config: dict) -> ValidationResult:
        field = config.get("field", "")
        value = self._extract_field(response_data, field)
        passed = value is not None
        return ValidationResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=f"Field '{field}' exists" if passed else f"Field '{field}' not found"
        )

class FieldEqualsValidator(BaseValidator):
    """检查字段值等于预期值"""
    def validate(self, response_data: dict, config: dict) -> ValidationResult:
        field = config.get("field", "")
        expected = config.get("expected")
        actual = self._extract_field(response_data, field)
        passed = str(actual) == str(expected)
        return ValidationResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=f"'{field}' = '{actual}'" if passed else f"'{field}': expected '{expected}', got '{actual}'"
        )

class FieldTypeValidator(BaseValidator):
    """检查字段类型"""
    TYPE_MAP = {"string": str, "number": (int, float), "object": dict, "array": list, "boolean": bool}

    def validate(self, response_data: dict, config: dict) -> ValidationResult:
        field = config.get("field", "")
        expected_type = config.get("expected_type", "string")
        value = self._extract_field(response_data, field)
        python_type = self.TYPE_MAP.get(expected_type, str)
        passed = isinstance(value, python_type) if value is not None else False
        return ValidationResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=f"'{field}' is {expected_type}" if passed else f"'{field}' is not {expected_type} (got {type(value).__name__})"
        )

class FieldContainsValidator(BaseValidator):
    """检查字段值包含子串"""
    def validate(self, response_data: dict, config: dict) -> ValidationResult:
        field = config.get("field", "")
        substring = config.get("substring", "")
        value = self._extract_field(response_data, field)
        passed = substring in str(value) if value is not None else False
        return ValidationResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=f"'{field}' contains '{substring}'" if passed else f"'{field}' does not contain '{substring}'"
        )

class FieldInValidator(BaseValidator):
    """检查字段值在枚举列表中"""
    def validate(self, response_data: dict, config: dict) -> ValidationResult:
        field = config.get("field", "")
        options = config.get("options", [])
        value = self._extract_field(response_data, field)
        passed = str(value) in [str(o) for o in options]
        return ValidationResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=f"'{field}' = '{value}' in {options}" if passed else f"'{field}' = '{value}' not in {options}"
        )

class FieldNotEmptyValidator(BaseValidator):
    """检查字段非空"""
    def validate(self, response_data: dict, config: dict) -> ValidationResult:
        field = config.get("field", "")
        value = self._extract_field(response_data, field)
        passed = value is not None and str(value).strip() != ""
        return ValidationResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=f"'{field}' is not empty" if passed else f"'{field}' is empty or missing"
        )

class FieldMatchesValidator(BaseValidator):
    """检查字段值匹配正则"""
    def validate(self, response_data: dict, config: dict) -> ValidationResult:
        import re
        field = config.get("field", "")
        pattern = config.get("pattern", "")
        value = self._extract_field(response_data, field)
        passed = bool(re.search(pattern, str(value))) if value is not None else False
        return ValidationResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=f"'{field}' matches pattern" if passed else f"'{field}' does not match '{pattern}'"
        )
```

所有 Validator 继承的 `_extract_field` 定义在 BaseValidator 中：

```python
# app/validators/base.py (补充)
class BaseValidator(ABC):
    def _extract_field(self, data: dict, field_path: str):
        """支持点分隔的嵌套字段提取: 'raw.agent_name' or 'data.flights[0].price'"""
        import re
        parts = re.split(r'\.(?![^\[]*\])', field_path)
        current = data
        for part in parts:
            # 处理数组索引 field[0]
            match = re.match(r'(\w+)\[(\d+)\]', part)
            if match:
                key, index = match.group(1), int(match.group(2))
                if isinstance(current, dict) and key in current:
                    current = current[key]
                    if isinstance(current, list) and index < len(current):
                        current = current[index]
                    else:
                        return None
                else:
                    return None
            else:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
        return current
```

### 5.4 路由验证器

```python
# app/validators/routing_validator.py
from app.validators.base import BaseValidator, ValidationResult

class RouteEqualsValidator(BaseValidator):
    """验证 Supervisor Agent 的路由分配是否正确"""
    def validate(self, response_data: dict, config: dict) -> ValidationResult:
        route_field = config.get("route_field", "raw.agent_name")
        expected_route = config.get("expected_route", "")
        actual_route = self._extract_field(response_data, route_field)

        passed = str(actual_route) == str(expected_route) if actual_route is not None else False
        return ValidationResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=f"Route: '{actual_route}'" if passed else f"Expected route '{expected_route}', got '{actual_route}'",
            details={"actual_route": actual_route, "expected_route": expected_route}
        )
```

### 5.5 TestEngine 集成

在 `app/test_engine.py` 的 `run_case()` 中：

```python
# 在解析 resp_data 之后、DeepEval 之前插入：

from app.validators.engine import AssertionEngine

# 解析 validation 字段
validation_raw = case_data.get("validation")
validation_refs = self._parse_validation(validation_raw)

if validation_refs is not None:
    # 新格式：断言组件引用列表
    assertion_engine = AssertionEngine()
    struct_result = assertion_engine.run(resp_data, validation_refs)

    needs_semantic = struct_result and struct_result.details.get("needs_semantic", False)

    if not needs_semantic:
        # 纯结构断言，不需要 DeepEval，直接返回
        return {
            "case_id": case_data.get("id"),
            "input": input_text,
            "actual_output": actual_output,
            "expected_output": expected_output,
            "score": struct_result.score if struct_result else 1.0,
            "reason": struct_result.reason if struct_result else "No assertions",
            "passed": struct_result.passed if struct_result else True,
            "validation_type": "structural",
            "validation_details": struct_result.details if struct_result else {},
            "latency": latency, "ttft": ttft,
            "thinking": thinking_process, "inform_base": inform_base, "raw": raw_data
        }
    else:
        # 混合模式：结构断言已执行，继续执行语义检测，最终合并得分
        struct_score_part = struct_result.score if struct_result else 1.0
        # ... 继续走 DeepEval 逻辑 ...
        # 最终: score = (struct_score_part + semantic_score) / 2

def _parse_validation(self, validation_raw) -> Optional[List[Dict]]:
    """解析 validation 字段，区分新格式(数组)和旧格式(对象)"""
    if validation_raw is None:
        return None
    if isinstance(validation_raw, str):
        try:
            validation_raw = json.loads(validation_raw)
        except:
            return None
    if isinstance(validation_raw, list):
        return validation_raw  # 新格式
    return None  # 旧格式 dict → 走原有逻辑
```

## 6. 数据流

```
断言组件库 (DB: assertion_components)
    │  保存组件定义
    │
    ▼
测试用例 validation 字段: [{"ref": "AC001", "params": {"value": "DC"}}, ...]
    │
    ▼
TestEngine.run_case()
    │
    ├── get_chat_response() → raw JSON string
    │
    ├── json.loads() → resp_data dict
    │
    ├── _parse_validation() → 判断新/旧格式
    │       │
    │       ├── 新格式(数组) → AssertionEngine.run()
    │       │       ├── 加载每个组件定义 (from DB)
    │       │       ├── 渲染参数 ({{value}} → "DC")
    │       │       ├── 执行对应 Validator
    │       │       └── 汇总结果
    │       │
    │       └── 旧格式/空 → 走原有 DeepEval 语义检测
    │
    └── 返回综合结果（含每个断言的 pass/fail 详情）
```

## 7. 使用场景示例

### 场景 A：验证普通 Agent 返回结构

```
组件库中已有:
  AC001: field_exists, config: {"field": "{{field_name}}"}
  AC002: field_equals, config: {"field": "{{field}}", "expected": "{{value}}"}
  AC005: field_not_empty, config: {"field": "{{field_name}}"}

测试用例 validation:
[
  {"ref": "AC001", "params": {"field_name": "result"}},
  {"ref": "AC001", "params": {"field_name": "lob"}},
  {"ref": "AC002", "params": {"field": "lob", "value": "DC"}},
  {"ref": "AC005", "params": {"field_name": "content"}}
]

API 返回: {"type": "token", "lob": "dc", "content": ".", "session_id": "151", ...}

执行结果:
  ✅ AC001: Field 'result' exists → FAIL (result 不存在)
  ✅ AC001: Field 'lob' exists → PASS
  ✅ AC002: 'lob' = 'dc' vs expected 'DC' → FAIL (大小写不匹配)
  ✅ AC005: 'content' is not empty → PASS
  综合: 2/4 passed, score=0.5
```

### 场景 B：Supervisor Agent 路由测试

```
组件库中已有:
  AC010: route_equals, config: {"route_field": "{{route_field}}", "expected_route": "{{agent}}"}
  AC001: field_exists, config: {"field": "{{field_name}}"}

测试用例 (input: "帮我查航班"):
validation:
[
  {"ref": "AC010", "params": {"route_field": "raw.routed_to", "agent": "flight"}},
  {"ref": "AC001", "params": {"field_name": "raw.flight_data"}}
]

API 返回: {"result": "...", "raw": {"routed_to": "flight", "flight_data": {...}}}

执行结果:
  ✅ AC010: Route = 'flight' → PASS
  ✅ AC001: Field 'raw.flight_data' exists → PASS
  综合: 2/2 passed, score=1.0
```

## 8. 受影响文件

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `app/models/assertion_component.py` | **新建** | 断言组件 ORM 模型 |
| `app/services/assertion_service.py` | **新建** | 断言组件 CRUD（增删改查） |
| `app/validators/__init__.py` | **新建** | 验证器包 |
| `app/validators/base.py` | **新建** | BaseValidator + ValidationResult + _extract_field |
| `app/validators/field_validators.py` | **新建** | 7 种字段验证器 |
| `app/validators/routing_validator.py` | **新建** | 路由验证器 |
| `app/validators/engine.py` | **新建** | 断言引擎（加载组件、渲染参数、执行断言） |
| `app/ui/assertions.py` | **新建** | 断言组件管理页面 |
| `app/test_engine.py` | **修改** | 集成 AssertionEngine，新增 `_parse_validation()` |
| `streamlit_app.py` | **修改** | 添加「断言管理」导航入口 |
| `scripts/migrate_*.py` | **新建** | DB migration: 创建 assertion_components 表 |

## 9. 边界条件与异常处理

1. **validation 为 null/空/旧格式 dict** → 回退到纯语义检测（完全向后兼容）
2. **组件 ID 不存在** → 该断言报 fail，reason 说明找不到组件
3. **参数未填写（{{param}} 未被替换）** → 断言报 fail，reason 提示缺少参数
4. **resp_data 非 dict（API 返回错误/纯文本）** → 所有结构断言 fail
5. **字段路径不存在** → `_extract_field` 返回 None，各 validator 处理 None 情况
6. **field_equals 类型敏感性** → 默认 string 比较，可扩展配置 `case_insensitive: true`

## 10. 可扩展性

- **新增断言类型**：实现 BaseValidator 子类，注册到 `AssertionEngine.VALIDATOR_MAP`
- **新增 Agent 类型**：无需改代码，创建对应断言组件即可
- **组件复用**：同一组件可被上百个用例引用，修改组件定义全局生效
- **渐进丰富**：从几个基础组件开始，逐步添加更复杂的断言逻辑
- **未来扩展方向**：自然语言生成断言组件（输入描述 → LLM 生成 config）
