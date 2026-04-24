# input-overlap-keep-db-category 需求设计

## 需求场景与处理逻辑
在服务器数据迁移到 PostgreSQL 时，若服务器测试用例与数据库记录重叠（按 `input` 判断），需要满足：
- 服务器数据覆盖数据库的业务字段；
- 但 `category_id` 保留数据库原值，不被服务器侧覆盖。

该规则用于保障：
1. 服务器数据内容（输入/预期/标签/校验等）是最新来源；
2. 数据库内已有分类归档不被破坏。

## 技术方案与架构
以 `scripts/migrate_json_to_db.py` 为主改点，调整迁移判重优先级：
1. 优先按 `input` 查找已存在记录；
2. 命中时执行“覆盖更新（排除 category_id）”；
3. 未命中时再按现有 `id + turn_index` 查询兼容旧逻辑；
4. 仍未命中则新增记录（新增保持现有 `category_id='root'` 逻辑）。

这样可在不改变 DB schema 的前提下，精准实现“按 input 覆盖 + 分类保留”。

## 影响文件
1. 修改：`/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/scripts/migrate_json_to_db.py`
   - 修改类型：迁移判重与更新逻辑
   - 影响函数：`migrate_test_cases`
   - 关键区域：当前 `id + turn_index` 去重段（约第 97-114 行）

2. 修改：`/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/DEPLOYMENT_RELEASE_2.1.md`
   - 修改类型：发布手册冲突策略文字精确化
   - 影响章节：冲突策略说明段

## 实现细节（含代码片段）
### 1) 按 input 优先匹配
在每条迁移记录处理中新增：
```python
existing_by_input = db.query(TestCase).filter(TestCase.input == input_text).first()
```

### 2) 覆盖更新但保留分类
若 `existing_by_input` 命中：
```python
existing = existing_by_input
existing.type = case_type
existing.input = input_text
existing.expected_output = expected_output
existing.retrieval_context = retrieval_context
existing.description = description
existing.turn_index = turn_index
existing.validation = validation
existing.overall_criteria = overall_criteria
existing.tags = tags
existing.updated_at = datetime.utcnow()
# 不更新 existing.category_id
```

### 3) 兼容旧判重
仅当 `existing_by_input` 未命中时，执行现有 `id + turn_index` 查询，避免破坏历史行为。

### 4) 新增逻辑保持不变
仍按当前规则创建记录并设置：
```python
category_id='root'
```

## 边界条件与异常处理
- `input` 为空：按现有逻辑跳过，不参与覆盖。
- 同一 `input` 在 DB 存在多条：使用 `.first()` 的当前行为；后续可加审计告警（本次不扩大范围）。
- `dry-run`：仅统计不提交，行为与正式模式一致。
- `category_id`：仅在“更新命中场景”保留 DB 原值；新增场景仍用默认分类。

## 数据流路径
1. 读取服务器 JSON (`data/test_cases.json`)。
2. 清洗字段并提取 `input`。
3. 优先按 `input` 查 DB。
4. 命中则更新业务字段（不改 `category_id`）。
5. 未命中再按旧规则查找/新增。
6. 批量提交并输出统计。

## 预期结果
- 数据重叠按 `input` 判断时，以服务器数据覆盖数据库。
- 数据库原有分类 `category_id` 在覆盖更新时保持不变。
- 发布手册与真实行为一致，便于上线执行。