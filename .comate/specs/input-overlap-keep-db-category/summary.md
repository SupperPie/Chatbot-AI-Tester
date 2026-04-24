# input-overlap-keep-db-category 执行总结

## 完成结果
- 已实现迁移时“按 `input` 判断重叠，服务器覆盖数据库业务字段，但保留数据库 `category_id`”。
- 已同步更新发版手册冲突策略描述，文档与代码行为一致。

## 代码变更
1. `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/scripts/migrate_json_to_db.py`
   - 在 `migrate_test_cases` 中调整判重顺序：
     - 先按 `TestCase.input == input_text` 查重
     - 未命中再回退 `id + turn_index` 兼容逻辑
   - 更新分支中覆盖业务字段并显式保留 `category_id`（不更新该字段）
   - 新增分支维持 `category_id='root'` 不变

2. `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/DEPLOYMENT_RELEASE_2.1.md`
   - 冲突策略改为：
     - `input` 相同：覆盖业务字段
     - `category_id`：保留数据库原值

## 验证结果
- 已执行 dry-run：
  - 命令：`python3 scripts/migrate_json_to_db.py --dry-run --file data/test_cases.json`
  - 结果：`更新 705 条，新增 0 条，错误 0 条`
  - 说明：脚本在预演模式下按预期运行，无异常。

## 结论
本轮需求已完成，当前迁移行为满足：
- 重叠判断标准：`input`
- 覆盖策略：服务器覆盖数据库业务字段
- 分类策略：数据库 `category_id` 保留不变