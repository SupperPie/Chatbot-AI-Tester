# 断言组件化测试框架 - 实现总结

## 完成状态

全部 12 个任务已完成，数据库迁移已执行成功。

## 新增文件

| 文件 | 用途 |
|------|------|
| `app/models/assertion_component.py` | AssertionComponent ORM 模型 |
| `app/services/assertion_service.py` | 组件 CRUD + 去重匹配 + 引用统计 |
| `app/validators/__init__.py` | 验证器包入口 |
| `app/validators/base.py` | BaseValidator 基类 + extract_field 路径解析 |
| `app/validators/field_validators.py` | 9 种字段类验证器 (equals/contains/matches/in/not_empty/type/compare/length) |
| `app/validators/structure_validators.py` | 5 种结构类验证器 (path_exists/required_fields/field_count/array_not_empty/nested_structure) |
| `app/validators/status_validators.py` | 3 种状态码验证器 (equals/in_range/not_equals) |
| `app/validators/engine.py` | AssertionEngine 断言引擎 (组件加载/参数渲染/composite 执行/评分) |
| `app/ui/assertions.py` | Streamlit 断言组件管理页面 (列表Tab + 生成Tab) |
| `scripts/migrate_assertion_components.py` | 数据库迁移脚本 |

## 修改文件

| 文件 | 改动 |
|------|------|
| `app/models/test_case.py` | 新增 `assertions` JSONB 列 |
| `app/services/test_case_service.py` | `_sanitize_record` 增加 assertions 字段清洗 |
| `app/test_engine.py` | 集成断言引擎 (execution_mode / assertion_detail) |
| `app/job_manager.py` | 传递 execution_mode 参数 |
| `app/utils.py` | load_data 增加 assertions 字段加载 |
| `app/ui/testcases.py` | 新增断言绑定按钮+面板、执行模式选择器 |
| `app/ui/sidebar.py` | 新增 Assertions 导航按钮 |
| `streamlit_app.py` | 新增 Assertions 页面路由 |

## 架构概览

```
TestCase (assertions JSONB)
    │
    │ [{"ref": "AC001", "params": {"expected": "dc"}}]
    │
    ▼
AssertionEngine.run(response, assertion_refs)
    │
    ├─ 加载组件定义 (from DB)
    ├─ 渲染参数 (preset + deferred override)
    ├─ 选择 Validator (VALIDATOR_MAP[category.condition])
    ├─ 执行验证 (atomic 或 composite)
    └─ 汇总结果 (EngineResult: passed/score/details)
```

## 执行模式

- **semantic**: 仅 DeepEval 语义评分（现有逻辑不变）
- **assertion**: 仅执行断言组件
- **full**: 两者都执行，都通过才算 passed

## 使用流程

1. 执行 `python3 scripts/migrate_assertion_components.py` 完成数据库迁移
2. 启动应用，侧栏出现 "🧩 Assertions" 入口
3. 在 Assertions 页面通过 AI 生成或手动创建组件
4. 在 Testcases 页面选中用例 → 点击 "🧩 Assertions" → 绑定组件
5. 执行测试时选择执行模式（full/semantic/assertion）

## 未改动的现有逻辑

- `validation` 字段含义和用法不变（语义评分标准定义）
- 当 `assertions` 为空时，断言引擎直接跳过，行为与改动前完全一致
- DeepEval 语义评分逻辑未修改
- 多轮对话 (multi_turn) 流程未受影响
