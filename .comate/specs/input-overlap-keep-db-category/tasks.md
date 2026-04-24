# 按 input 覆盖并保留数据库分类的实施任务
- [x] Task 1: 调整迁移脚本判重优先级为 input 优先
    - 1.1: 在 `migrate_test_cases` 中新增按 `input` 查询 existing 逻辑
    - 1.2: 仅在 `input` 未命中时回退到 `id + turn_index` 兼容查询
    - 1.3: 保持空 `input` 跳过与 dry-run 行为不变

- [x] Task 2: 实现覆盖更新时保留 category_id
    - 2.1: 在更新分支覆盖业务字段（type/input/expected_output/tags/validation 等）
    - 2.2: 明确不更新 `category_id`，保留数据库原值
    - 2.3: 保持新增分支 `category_id='root'` 现有行为

- [x] Task 3: 同步发布手册冲突策略描述
    - 3.1: 更新 `DEPLOYMENT_RELEASE_2.1.md` 冲突规则文字
    - 3.2: 明确“input 相同覆盖业务字段，category 保留数据库值”

- [x] Task 4: 执行结果校验与收尾
    - 4.1: 运行迁移脚本 dry-run 做行为校验
    - 4.2: 检查 tasks 勾选与变更文件一致
    - 4.3: 生成本轮 spec 总结 `summary.md`
