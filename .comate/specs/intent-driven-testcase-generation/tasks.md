# 意图驱动测试用例生成 - 任务计划

- [x] Task 1: 创建 `app/ui/prompts/intent_prompts.py` 模块
    - 1.1: 创建 `app/ui/prompts/__init__.py` 空文件
    - 1.2: 定义意图常量（INTENT_DEFAULT / INTENT_CONSULT / INTENT_PURCHASE / INTENT_OPTIONS）
    - 1.3: 定义 REQUIREMENT_TEMPLATES 字典（三种意图对应的自动填充文案）
    - 1.4: 定义 TAG_MAPPING 字典（三种意图对应的 tag 列表）
    - 1.5: 定义 BASE_PROMPT_TEMPLATE（从 tester.py 抽取现有 schema 约束部分，增加 `{intent_fragment}` 插槽）
    - 1.6: 定义 CONSULT_PROMPT_FRAGMENT（咨询子 prompt：覆盖多维度、多轮比例约束）
    - 1.7: 定义 PURCHASE_PROMPT_FRAGMENT（购买子 prompt：AIDA 分层、信号词清单、商品特性命中、Few-shot 占位）
    - 1.8: 实现 `build_prompt()` 函数（根据意图组装完整 prompt）
    - 1.9: 实现 `get_requirement_template()` 和 `get_tags_for_intent()` 辅助函数

- [x] Task 2: 改造 `app/ui/tester.py` — UI 层（下拉组件 + 自动填充）
    - 2.1: 新增 import 语句引入 intent_prompts 模块
    - 2.2: 初始化 `st.session_state.selected_intent` 
    - 2.3: 定义 `on_intent_change()` 回调（切换时填充 saved_req）
    - 2.4: 在标题下方、两列输入区之上插入 `st.selectbox("🎯 测试用例模板", ...)`
    - 2.5: 验证"默认"选项时不覆盖用户已有输入

- [x] Task 3: 改造 `app/ui/tester.py` — 生成逻辑（Prompt 替换 + Tag 注入）
    - 3.1: 将原内联 prompt 替换为 `build_prompt(intent, requirements, knowledge_base)` 调用
    - 3.2: 在 flat_cases 组装逻辑中，将 `"tags": []` 替换为 `"tags": get_tags_for_intent(selected_intent)`
    - 3.3: 确认多轮用例每条 turn 均注入相同 tags
    - 3.4: 确认"默认"意图时行为与改造前完全一致（tags=[]，原始 prompt 逻辑）

- [x] Task 4: 功能验证
    - 4.1: 检查文件语法（python -c import）
    - 4.2: 验证三种意图下 build_prompt 输出内容正确性
    - 4.3: 确认多轮 ID 共享逻辑未被影响
