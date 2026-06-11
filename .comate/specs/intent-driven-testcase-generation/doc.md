# 意图驱动的测试用例生成（Intent-Driven Test Case Generation）

## 1. 需求概述

在 Tester 页面引入测试用例模板维度，让用户在生成测试用例之前先选择目标意图/测试用例模板类型（默认 / 咨询意图 / 购买意图）。不同意图触发不同的 Prompt 策略与测试需求模板自动填充，并将选择结果作为 Tag 写入生成的用例，便于后续分类、检索与质量评估。

实现遵循"轻量化"原则：
- 不引入新的数据库表或服务层抽象
- Knowledge Base 仍为纯文本输入，不做结构化
- 仅在 `app/ui/tester.py` 内进行扩展，并新增一个独立模块集中管理 prompt 模板

## 2. 核心场景与处理逻辑

### 2.1 场景 A：选择"默认"
- 行为与现状完全一致
- 使用现有内嵌 prompt
- `Test Requirements` 文本框保持用户已输入的内容（不强制覆盖）
- 生成用例的 `tags` 字段为 `[]`（保持现状）

### 2.2 场景 B：选择"咨询意图"
- Prompt = 现有内嵌 prompt（schema/语言/输出格式约束）+ 咨询子 Prompt
- 自动填充 `Test Requirements` 字段为：
  > 基于产品信息知识的输入生成40条知识问答，尽量全面覆盖产品的信息和10条多轮对话场景性的（每轮对话2-3轮和商品信息相关）
- 生成的所有用例 `tags` 强制写入 `["咨询意图"]`
- 子 Prompt 强调：
  - 基于 Knowledge Base 中的产品信息
  - 全面覆盖产品信息（功能、规格、价格、流程、售后等多个维度）
  - 默认 ~80% 单轮 + ~20% 多轮（每场景 2-3 轮），用户在 requirements 中明确指定时遵从用户

### 2.3 场景 C：选择"购买意图"
- Prompt = 现有内嵌 prompt + 购买子 Prompt（包含购买意图分层 + 信号词清单 + Few-shot 占位）
- 自动填充 `Test Requirements` 字段为：
  > 基于产品信息知识的输入生成40条购买意图的测试用例和10条多轮对话场景性的（每轮对话2-3轮和商品信息相关）
- 生成的所有用例 `tags` 强制写入 `["购买意图"]`
- 子 Prompt 关键设计要素：
  - **意图分层（AIDA+）**：Awareness / Interest / Desire / Intent / Action / Post-purchase；要求 ≥60% 落在 Desire/Intent/Action
  - **购买信号词清单**：决策动词（要、买、订、下单、续费、升级）/ 紧迫词（现在、今天、马上）/ 价格敏感（划算、优惠、值不值）/ 比较句式（A 和 B 哪个好）/ 个人化锚点（我家 3 口人）/ 风险担忧（能退吗、靠谱吗）
  - **基于 Knowledge Base 商品特性**：要求每条用例命中商品至少一个卖点/特性维度
  - **Few-shot 区域**：保留占位符（默认空），后续可由用户提供示例注入

## 3. 架构与技术方案

### 3.1 文件组织
新增一个独立模块集中管理意图相关 prompt 模板：

```
app/ui/
├── tester.py                       # 修改：增加下拉、模板填充回调、调用 prompt builder
└── prompts/
    └── intent_prompts.py           # 新增：集中存放 prompt 片段、需求模板、tag 映射
```

### 3.2 模块职责

**`app/ui/prompts/intent_prompts.py`（新增）**
- 定义意图枚举（字符串常量即可，避免引入 enum 复杂度）
  - `INTENT_DEFAULT = "默认"`
  - `INTENT_CONSULT = "咨询意图"`
  - `INTENT_PURCHASE = "购买意图"`
- 定义 `REQUIREMENT_TEMPLATES: dict[str, str]`：意图 → 自动填充文案
- 定义 `TAG_MAPPING: dict[str, list[str]]`：意图 → 写入的 tag 列表
- 定义 `BASE_PROMPT_TEMPLATE`（schema 部分，从 tester.py 抽出）
- 定义 `CONSULT_PROMPT_FRAGMENT`（咨询子 prompt）
- 定义 `PURCHASE_PROMPT_FRAGMENT`（购买子 prompt，含意图分层、信号词、Few-shot 占位）
- 提供函数：
  - `build_prompt(intent: str, requirements: str, knowledge_base: str, few_shot: str = "") -> str`
  - `get_requirement_template(intent: str) -> str`
  - `get_tags_for_intent(intent: str) -> list[str]`

**`app/ui/tester.py`（修改）**
- 在标题与两列输入区之间增加 `st.selectbox("🎯 意图选择", ...)` 下拉
- 维护 `st.session_state.selected_intent` 与 `st.session_state.last_intent`
- 当下拉值变更时（on_change 回调）：将 `REQUIREMENT_TEMPLATES[intent]` 写入 `st.session_state.saved_req`，触发 rerun 让 Test Requirements 框刷新
- 生成按钮逻辑：调用 `build_prompt(selected_intent, requirements, knowledge_base)` 替换原内联 prompt
- 解析返回的 cases 时：将 `get_tags_for_intent(selected_intent)` 写入每条 case 的 `tags`（默认意图保持空数组）

### 3.3 数据流

```
用户选择意图
    │
    ├─→ on_change 回调
    │   └─→ session_state.saved_req = REQUIREMENT_TEMPLATES[intent]
    │       └─→ rerun → Test Requirements 文本框显示模板
    │
用户点击 Generate
    │
    └─→ build_prompt(intent, req, kb)
        ├─ 默认: BASE_PROMPT_TEMPLATE
        ├─ 咨询: BASE + CONSULT_PROMPT_FRAGMENT
        └─ 购买: BASE + PURCHASE_PROMPT_FRAGMENT
            │
            └─→ LLM 调用
                │
                └─→ 解析 JSON 后注入 tags = get_tags_for_intent(intent)
```

## 4. 受影响文件

| 类型 | 路径 | 主要改动 |
|---|---|---|
| 修改 | `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/tester.py` | 新增意图下拉、自动填充回调；改用 `build_prompt`；生成后注入 tags |
| 新增 | `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/prompts/__init__.py` | 包初始化（空文件） |
| 新增 | `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/prompts/intent_prompts.py` | Prompt 模板与构造函数 |

## 5. 关键实现细节（代码骨架）

### 5.1 `intent_prompts.py` 核心结构

```python
# 意图常量
INTENT_DEFAULT = "默认"
INTENT_CONSULT = "咨询意图"
INTENT_PURCHASE = "购买意图"
INTENT_OPTIONS = [INTENT_DEFAULT, INTENT_CONSULT, INTENT_PURCHASE]

# 自动填充模板
REQUIREMENT_TEMPLATES = {
    INTENT_DEFAULT: "",  # 默认不覆盖用户已有输入
    INTENT_CONSULT: "基于产品信息知识的输入生成40条知识问答，尽量全面覆盖产品的信息和10条多轮对话场景性的（每轮对话2-3轮和商品信息相关）",
    INTENT_PURCHASE: "基于产品信息知识的输入生成40条购买意图的测试用例和10条多轮对话场景性的（每轮对话2-3轮和商品信息相关）",
}

TAG_MAPPING = {
    INTENT_DEFAULT: [],
    INTENT_CONSULT: ["咨询意图"],
    INTENT_PURCHASE: ["购买意图"],
}

BASE_PROMPT_TEMPLATE = """You are a testcase generator. Generate test cases based on the requirements and knowledge.
CRITICAL: You MUST output ONLY a valid JSON array of test case objects. Unless requested otherwise, all "input", "expected_output", and messages MUST be generated in Chinese (中文).

Requirements:
{requirements}

Knowledge Base:
{knowledge_base}

{intent_fragment}

The JSON format MUST strictly follow this flat schema. ...（保留原 schema 描述）...

ONLY return the highly-structured JSON array. Do not include markdown blocks like ```json or trailing text."""

CONSULT_PROMPT_FRAGMENT = """
【意图导向：咨询意图】
本批用例聚焦"产品信息咨询"。请遵循：
1. 基于 Knowledge Base 中的产品信息生成知识问答
2. 全面覆盖：基础介绍、规格参数、价格档位、使用流程、售后政策、常见疑问等多维度
3. 多轮对话占比 ~20%（每段 2-3 轮，围绕同一商品信息话题展开）；如 Requirements 已显式指定比例则遵从用户
4. 用户口吻自然，可以是初次了解、对比了解、深入咨询等场景
"""

PURCHASE_PROMPT_FRAGMENT = """
【意图导向：购买意图】
本批用例聚焦"购买决策与转化"。生成时遵循：

1. 购买意图分层（每条用例需隐式属于以下某一层），≥60% 落在 Desire/Intent/Action：
   - Awareness 认知：知道产品存在
   - Interest 兴趣：主动了解细节
   - Desire 渴望：比较、纠结、个人化考量
   - Intent 意向：询问购买条件、优惠、保障
   - Action 行动：准备下单、询问支付/数量
   - Post-purchase 售后：已购后疑问

2. 必须高频出现以下购买信号语言特征（至少命中一类）：
   - 决策动词：要、买、订、下单、续费、升级、抢
   - 紧迫词：现在、今天、马上、赶时间
   - 价格敏感：划算、优惠、值不值、有券吗
   - 比较句式：A 和 B 哪个好、推荐哪个、对比
   - 个人化锚点：我家/我下周/我有 X
   - 风险担忧：能退吗、靠谱吗、不满意怎么办

3. 紧扣 Knowledge Base 中的商品特性：每条用例须命中至少一个商品卖点 / 行程亮点 / 目标人群 / 常见疑虑，避免泛泛而谈。

4. 多轮对话 ~20%（每段 2-3 轮），呈现"了解 → 比较 → 决策 → 下单"的渐进购买链路。

{few_shot_section}
"""

FEW_SHOT_PLACEHOLDER = ""  # 预留：未来注入用户提供的 few-shot 示例

def build_prompt(intent: str, requirements: str, knowledge_base: str, few_shot: str = "") -> str:
    kb = knowledge_base if knowledge_base.strip() else "No additional knowledge provided."
    if intent == INTENT_CONSULT:
        fragment = CONSULT_PROMPT_FRAGMENT
    elif intent == INTENT_PURCHASE:
        few_shot_section = f"【Few-shot 参考示例】\n{few_shot}" if few_shot.strip() else ""
        fragment = PURCHASE_PROMPT_FRAGMENT.format(few_shot_section=few_shot_section)
    else:
        fragment = ""
    return BASE_PROMPT_TEMPLATE.format(
        requirements=requirements,
        knowledge_base=kb,
        intent_fragment=fragment,
    )

def get_requirement_template(intent: str) -> str:
    return REQUIREMENT_TEMPLATES.get(intent, "")

def get_tags_for_intent(intent: str) -> list:
    return list(TAG_MAPPING.get(intent, []))
```

### 5.2 `tester.py` 关键改动点

```python
from app.ui.prompts.intent_prompts import (
    INTENT_OPTIONS, INTENT_DEFAULT,
    build_prompt, get_requirement_template, get_tags_for_intent,
)

# session 初始化新增
if "selected_intent" not in st.session_state:
    st.session_state.selected_intent = INTENT_DEFAULT

def on_intent_change():
    intent = st.session_state.tester_intent
    st.session_state.selected_intent = intent
    template = get_requirement_template(intent)
    if template:  # 默认时为空字符串，不覆盖
        st.session_state.saved_req = template

# UI: 在两列输入之上加一行
st.selectbox(
    "🎯 意图选择",
    options=INTENT_OPTIONS,
    index=INTENT_OPTIONS.index(st.session_state.selected_intent),
    key="tester_intent",
    on_change=on_intent_change,
    help="选择不同意图会切换 Prompt 策略并自动填充测试需求模板"
)

# 生成时
prompt = build_prompt(
    intent=st.session_state.selected_intent,
    requirements=requirements,
    knowledge_base=knowledge_base,
)

# 解析后注入 tags
intent_tags = get_tags_for_intent(st.session_state.selected_intent)
flat_cases.append({
    ...,
    "tags": intent_tags,  # 替换原来的 []
    ...
})
```

## 6. 边界条件与异常处理

| 场景 | 处理 |
|---|---|
| 用户切换意图后又手动修改了 Requirements | 不再覆盖（仅在 on_change 时填充一次） |
| 用户从"咨询/购买"切回"默认" | 不清空 Requirements（避免误删用户输入） |
| 用户选了"购买意图"但 Knowledge Base 为空 | 仍正常生成；prompt 会提示 "No additional knowledge provided."，但用例可能弱化商品特性命中（属预期，UI 不强制阻断） |
| LLM 返回的用例已自带非空 tags | 用本意图 tag 覆盖（保证一致性，便于后续分类） |
| 多轮用例的多条 turn | 共享同一 tag 列表（每条 turn 都注入相同 tags） |
| 模板填充时如果用户已经输入过自定义内容 | 当前设计为直接覆盖（只在 on_change 时触发一次，符合"模板填充"语义） |

## 7. 预期结果

- Tester 页面顶部新增"意图选择"下拉，三个选项可正常切换
- 选择"咨询/购买"后 Test Requirements 文本框自动填入约定模板文案
- 选择"默认"时，行为与改造前完全一致
- 不同意图触发的 LLM 调用使用不同 prompt（默认 / +咨询 / +购买）
- 生成的用例（包括多轮中的每一条 turn）的 `tags` 字段按意图正确写入
- Few-shot 区域已留出注入入口，后续可低成本扩展
- 现有"多轮对话 ID 共享"逻辑不受影响

## 8. 不在本次范围

- Knowledge Base 结构化（产品画像表单）
- Persona / Scenario 维度组合采样
- 用例质量评分器（LLM Judge / embedding 相似度）
- Few-shot 示例的具体内容编辑 UI（仅留接口）
- Prompt 模板的 DB 持久化与可视化编辑
