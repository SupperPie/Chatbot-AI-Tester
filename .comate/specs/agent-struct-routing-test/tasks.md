# 断言组件化测试框架 - 任务计划

> **约束**：不改动现有功能和逻辑。所有对现有文件的修改（test_engine.py、chat_client.py、streamlit_app.py、testcases.py 等）在执行前需先与用户确认具体改动内容。新建文件不受此限制。

- [x] Task 1: 数据库模型与迁移
    - 1.1: 创建 `app/models/assertion_component.py` ORM 模型（id, name, description, category, condition, config, tags, created_at, updated_at）
    - 1.2: 创建 DB migration 脚本，建表 `assertion_components`
    - 1.3: 在 `app/database.py` 或模型 init 中注册新模型

- [x] Task 2: 断言组件 CRUD 服务
    - 2.1: 创建 `app/services/assertion_service.py`
    - 2.2: 实现 get_all / get_by_id / get_by_category / search 查询方法
    - 2.3: 实现 create / update / delete 写入方法
    - 2.4: 实现 get_reference_count（统计组件被多少用例引用）
    - 2.5: 实现 find_matching_component（去重匹配：按 category + condition + preset 参数查找重复）

- [x] Task 3: 验证器基础架构
    - 3.1: 创建 `app/validators/__init__.py`
    - 3.2: 创建 `app/validators/base.py`（BaseValidator 抽象基类 + ValidationResult + `_extract_field` 嵌套路径提取）
    - 3.3: 单元测试 `_extract_field` 对 `data.flights[0].price` 等路径的解析

- [x] Task 4: Field 类验证器实现
    - 4.1: 创建 `app/validators/field_validators.py`
    - 4.2: 实现 FieldEqualsValidator（equals / not_equals）
    - 4.3: 实现 FieldContainsValidator（contains）
    - 4.4: 实现 FieldMatchesValidator（matches，正则）
    - 4.5: 实现 FieldInValidator（in）
    - 4.6: 实现 FieldNotEmptyValidator（not_empty）
    - 4.7: 实现 FieldTypeValidator（type）
    - 4.8: 实现 FieldCompareValidator（gt / gte / lt / lte）
    - 4.9: 实现 FieldLengthValidator（length）

- [x] Task 5: Structure 类验证器实现
    - 5.1: 创建 `app/validators/structure_validators.py`
    - 5.2: 实现 PathExistsValidator（path_exists）
    - 5.3: 实现 RequiredFieldsValidator（required_fields）
    - 5.4: 实现 FieldCountValidator（field_count）
    - 5.5: 实现 ArrayNotEmptyValidator（array_not_empty）
    - 5.6: 实现 NestedStructureValidator（nested_structure）

- [x] Task 6: StatusCode 验证器实现
    - 6.1: **[需确认]** 修改 `chat_client.py`，在返回的 JSON 中增加 `status_code` 字段（需确认改动方案）
    - 6.2: 创建 `app/validators/status_validators.py`
    - 6.3: 实现 StatusCodeEqualsValidator / StatusCodeInRangeValidator / StatusCodeNotEqualsValidator

- [x] Task 7: 断言引擎（AssertionEngine）
    - 7.1: 创建 `app/validators/engine.py`
    - 7.2: 实现组件加载（从 DB 读取组件定义）
    - 7.3: 实现参数渲染（preset 直接取值，deferred 从 params 填充）
    - 7.4: 实现 VALIDATOR_MAP 注册（category+condition → Validator 类映射）
    - 7.5: 实现 run() 方法：遍历断言引用列表，逐个执行，汇总结果
    - 7.6: 实现组合组件(composite)执行逻辑：解析 checks 数组，支持内联条件 + 引用已有组件
    - 7.7: 实现综合评分逻辑（全部通过=pass，score=通过数/总数）

- [x] Task 8: TestEngine 集成 **[已确认]**
    - 8.1: **[需确认]** 在 `app/test_engine.py` 新增 `_parse_validation()` 方法（区分新格式数组 vs 旧格式/空）
    - 8.2: **[需确认]** 在 `run_case()` 中插入断言引擎调用点（确保不影响现有语义检测流程）
    - 8.3: 扩展返回结果 dict，新增 validation_type / validation_details 字段
    - 8.4: 实现三种执行模式逻辑（语义检测 / 仅断言 / 完整检测）

- [x] Task 9: 断言组件管理 UI 页面 - 组件列表 Tab
    - 9.1: 创建 `app/ui/assertions.py`，**[需确认]** 注册到 `streamlit_app.py` 和 `sidebar.py`
    - 9.2: 实现 Tab 切换结构（组件列表 | 组件生成）
    - 9.3: 实现筛选栏（大类下拉 + 标签下拉 + 搜索框）
    - 9.4: 实现组件卡片网格展示（双徽章、参数预览、引用统计）
    - 9.5: 实现卡片「测试」按钮（展开 JSON 输入 + 活参数填写 + 本地验证执行）
    - 9.6: 实现卡片「编辑」和「删除」功能

- [x] Task 10: 断言组件管理 UI 页面 - 组件生成 Tab
    - 10.1: 实现 AI 一键生成区域（JSON 输入 + 自然语言输入 + 调用 LLM 生成）
    - 10.2: 编写 AI 生成 prompt 模板（基于 3 大类 + 条件体系 + composite）
    - 10.3: 实现去重匹配逻辑（生成后自动与组件库对比，标注已有/新条件）
    - 10.4: 实现生成结果展示（标注复用/新建状态 + 改为活参数按钮）
    - 10.5: 实现三种保存选项（保存为组合组件 / 仅保存新条件 / 全部保存为独立组件）
    - 10.6: 实现「本地验证」功能（用输入的 JSON 执行生成的断言）
    - 10.7: 实现手动创建区域（三步表单：选大类 → 选条件 → 配参数）
    - 10.8: 实现参数 preset/deferred 切换 Radio
    - 10.9: 实现手动创建的「本地验证」功能

- [x] Task 11: 测试用例页面集成 **[已确认]**
    - 11.1: **[需确认]** 在 `app/ui/testcases.py` 的 validation 列添加断言组件选择交互
    - 11.2: 实现断言组件选择器（列出可用组件 + 填写活参数 + 添加/移除）
    - 11.3: validation 列以 tag/chip 形式展示已关联组件

- [x] Task 12: 执行模式选择 UI
    - 12.1: 在测试执行入口（run batch 时）添加执行模式选择（语义检测 / 仅断言 / 完整检测）
    - 12.2: 将选择的模式传递给 TestEngine
    - 12.3: 测试报告中显示 validation_type 和断言详情
