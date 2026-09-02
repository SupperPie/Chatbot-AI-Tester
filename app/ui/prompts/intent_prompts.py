"""意图驱动的测试用例生成 - Prompt 模板与构造函数。

集中管理 Tester 页面三种意图（默认/咨询意图/购买意图）所对应的：
- Test Requirements 自动填充模板
- Prompt 子片段
- 生成用例时注入的 Tag
"""

# ============================================================
# 意图常量
# ============================================================
INTENT_DEFAULT = "默认"
INTENT_CONSULT = "咨询意图"
INTENT_PURCHASE = "购买意图"

INTENT_OPTIONS = [INTENT_DEFAULT, INTENT_CONSULT, INTENT_PURCHASE]


# ============================================================
# Test Requirements 自动填充模板
# ============================================================
REQUIREMENT_TEMPLATES = {
    INTENT_DEFAULT: "",  # 默认不覆盖用户已有输入
    INTENT_CONSULT: (
        "基于产品信息知识的输入生成40条知识问答，尽量全面覆盖产品的信息和"
        "10条多轮对话场景性的（每轮对话2-3轮和商品信息相关）"
    ),
    INTENT_PURCHASE: (
        "基于产品信息知识的输入生成40条购买意图的测试用例和"
        "10条多轮对话场景性的（每轮对话2-3轮和商品信息相关）"
    ),
}


# ============================================================
# 意图 -> Tag 映射
# ============================================================
TAG_MAPPING = {
    INTENT_DEFAULT: [],
    INTENT_CONSULT: ["咨询意图"],
    INTENT_PURCHASE: ["购买意图"],
}


# ============================================================
# 基础 Prompt 模板（schema/语言/输出格式约束）
# 保留原 tester.py 中的所有 schema 约定，仅在 Knowledge Base 之后
# 插入一个 {intent_fragment} 插槽，用于注入子 prompt。
# ============================================================
BASE_PROMPT_TEMPLATE = """You are a testcase generator. Generate test cases based on the requirements and knowledge.
CRITICAL: You MUST output ONLY a valid JSON array of test case objects. Unless requested otherwise, all "input", "expected_output", "description", and messages MUST be generated in Chinese (中文).

Requirements:
{requirements}

Knowledge Base:
{knowledge_base}
{intent_fragment}
The JSON format MUST strictly follow this flat schema. If generating a multi-turn conversation, DO NOT use a nested "conversation" array. Instead, output one distinct object per turn. Each turn object for the same conversation MUST have the exact same "description" and "type", but an incrementing "turn_index" starting at 1.

IMPORTANT - "description" field: This field describes the purpose of the test case, corresponding to the Acceptance Criteria (AC) from the product requirements. For each test case, write a concise sentence in Chinese describing which AC this test case is designed to verify. Example: "验证用户在未登录状态下访问个人中心时跳转到登录页" or "验证模型能基于知识库正确回答退改签政策".

[
  {{
    "type": "multi_turn", // Use "multi_turn" if testing a sequence, else "single"
    "turn_index": 1, // Only use turn_index if multi_turn. 1 for first turn, 2 for second, etc.
    "tags": [], // CRITICAL: This MUST ALWAYS be an empty list []. Do not generate tags.
    "input": "User's first message (in Chinese)",
    "expected_output": "Expected assistant response (in Chinese)",
    "description": "用中文描述本条用例要验证的验收标准(AC)，例如：验证模型能正确回答退款政策"
  }},
  {{
    "type": "multi_turn",
    "turn_index": 2, // Second turn continues the same conversation
    "tags": [],
    "input": "User's follow up message (in Chinese)",
    "expected_output": "Expected follow up response (in Chinese)",
    "description": "同上，描述本条用例要验证的验收标准(AC)"
  }}
]

ONLY return the highly-structured JSON array. Do not include markdown blocks like ```json or trailing text."""


# ============================================================
# 咨询意图子 Prompt
# ============================================================
CONSULT_PROMPT_FRAGMENT = """
【意图导向：咨询意图（产品信息咨询）】
本批用例聚焦"用户对商品信息的咨询与了解"，请严格遵循以下原则：

1. 以 Knowledge Base 中的产品信息为唯一事实来源生成知识问答；不可编造未提及的卖点或参数。
2. 全面覆盖以下信息维度（每个维度至少有若干用例）：
   - 基础介绍：产品是什么、适用人群、核心价值
   - 规格/内容：组成、行程、规格、包含项与不包含项
   - 价格档位：价格、套餐差异、优惠政策
   - 使用流程：如何下单、使用、核销、入场流程
   - 售后政策：退改、保障、客服支持
   - 常见疑问：用户对产品的高频疑虑（基于商品特性合理推断）
3. 多轮对话占比默认 ~20%（即每 10 条用例约 2 段多轮，每段 2-3 轮，围绕同一商品信息话题层层追问）；如 Requirements 已显式指定数量/比例，按用户指定执行。
4. 用户口吻自然、多样：可以是"初次了解"、"对比了解"、"深入咨询"等不同场景，避免句式雷同。
5. expected_output 应基于 Knowledge Base 给出准确、简洁的事实性答复。
"""


# ============================================================
# 购买意图子 Prompt（含 Few-shot 占位）
# ============================================================
PURCHASE_PROMPT_FRAGMENT = """
【意图导向：购买意图（购买决策与转化）】
本批用例聚焦"用户表现出明确购买倾向"。生成时严格遵循：

1. 购买意图分层（每条用例隐式属于以下某一层），**≥60% 的用例必须落在 Desire / Intent / Action 三层**：
   - Awareness 认知：刚知道产品存在
   - Interest 兴趣：主动了解细节
   - Desire 渴望：纠结、比较、个人化考量
   - Intent 意向：询问购买条件、优惠、保障
   - Action 行动：准备下单、询问支付/数量/确认
   - Post-purchase 售后：已购后疑问

2. 用例必须高频出现以下"购买信号"语言特征（每条用例至少命中一类，鼓励多类组合）：
   - 决策动词：要、买、订、下单、续费、升级、抢、入手
   - 紧迫词：现在、今天、马上、赶时间、来不及、最后一天
   - 价格敏感：划算、优惠、值不值、便宜点、有券吗、最低多少
   - 比较句式：A 和 B 哪个好、对比、推荐哪个、区别在哪
   - 个人化锚点：我家 X 口人、我下周出差、我有 X 张券、我是会员
   - 风险担忧：能退吗、靠谱吗、保障、不满意怎么办、出问题谁负责

3. **紧扣 Knowledge Base 中的商品特性**：每条用例必须命中商品至少一个具体卖点 / 行程亮点 / 目标人群 / 常见疑虑，避免"你们产品多少钱"这种与商品无关的泛化问题。优先体现该商品独特的差异化要素。

4. 多轮对话占比默认 ~20%（每段 2-3 轮），呈现"了解 → 比较 → 决策 → 下单"的渐进购买链路；如 Requirements 已显式指定，按用户指定执行。

5. expected_output 应是符合销售/客服话术的高质量回复：澄清疑虑、突出卖点、推动转化，并紧扣 Knowledge Base 事实。
{few_shot_section}"""


# Few-shot 默认占位（未提供时为空字符串，不会污染 prompt）
FEW_SHOT_PLACEHOLDER = ""


# ============================================================
# 公开 API
# ============================================================
def build_prompt(
    intent: str,
    requirements: str,
    knowledge_base: str,
    few_shot: str = "",
) -> str:
    """根据意图组装完整的 LLM prompt。

    Args:
        intent: 意图常量之一（INTENT_DEFAULT/INTENT_CONSULT/INTENT_PURCHASE）
        requirements: 用户输入的 Test Requirements
        knowledge_base: 用户输入的 Knowledge Base（可为空）
        few_shot: 可选的 few-shot 示例文本（仅购买意图使用）

    Returns:
        完整 prompt 字符串
    """
    kb_text = knowledge_base if knowledge_base and knowledge_base.strip() else "No additional knowledge provided."

    if intent == INTENT_CONSULT:
        intent_fragment = CONSULT_PROMPT_FRAGMENT
    elif intent == INTENT_PURCHASE:
        few_shot_section = (
            f"\n【Few-shot 参考示例】\n{few_shot}\n"
            if few_shot and few_shot.strip()
            else ""
        )
        intent_fragment = PURCHASE_PROMPT_FRAGMENT.format(
            few_shot_section=few_shot_section
        )
    else:
        intent_fragment = ""

    return BASE_PROMPT_TEMPLATE.format(
        requirements=requirements,
        knowledge_base=kb_text,
        intent_fragment=intent_fragment,
    )


def get_requirement_template(intent: str) -> str:
    """获取指定意图对应的 Test Requirements 自动填充文案。"""
    return REQUIREMENT_TEMPLATES.get(intent, "")


def get_tags_for_intent(intent: str) -> list:
    """获取指定意图对应的 tag 列表（返回新副本，避免外部修改污染映射）。"""
    return list(TAG_MAPPING.get(intent, []))
