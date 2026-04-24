# release/2.1 部署与迁移方案

## 需求场景与处理逻辑
用户需要两件事：
1. 输出一份可直接执行的部署文档（Markdown）
2. 将当前代码提交到 `release/2.1`

部署文档必须覆盖：
- 服务器数据库连接配置
- 服务器数据迁移到 PostgreSQL 的执行步骤
- 冲突策略：以 `input` 为键，服务器数据覆盖数据库
- 备份、校验、回滚

## 技术方案与架构
采用“文档落地 + Git 发布”双轨方案：
- 在仓库内新增部署文档，作为 release/2.1 运维手册
- 使用现有脚本（`scripts/migrate_json_to_db.py`、`scripts/migrate_all_data.py` 等）组织迁移流程
- 明确冲突覆盖算法为“按 input 更新或插入”
- 发布分支统一切到 `release/2.1` 并提交

## 影响文件
- 新增：`/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/DEPLOYMENT_RELEASE_2.1.md`
  - 类型：新增部署手册
  - 内容：环境变量、建表、迁移、冲突策略、校验、回滚、发布清单

- 更新：`/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/.comate/specs/release-2-1-deployment/tasks.md`
  - 类型：任务编排与进度追踪

- 更新：`/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/.comate/specs/release-2-1-deployment/summary.md`
  - 类型：结果总结

## 实现细节
### 部署文档章节结构
- 发布分支与提交命令
- `.env` 中 `DATABASE_URL`/`DATABASE_SCHEMA` 配置（重点）
- 迁移 dry-run + 正式执行（重点）
- 冲突策略（按 input 覆盖）伪代码
- 校验与回滚命令
- schema 初始化与建表（可选，仅新环境首次部署）

### 冲突处理伪代码
```python
existing = db.query(TestCase).filter(TestCase.input == src_input).first()
if existing:
    # 服务器覆盖数据库
    existing.expected_output = src_expected_output
    existing.tags = src_tags
    existing.validation = src_validation
    ...
else:
    db.add(TestCase(...))
```

## 边界与异常处理
- 数据库不可连通：先执行 `scripts/test_db_connection.py`，失败则阻断迁移
- 迁移脚本执行异常：使用迁移前 SQL dump 回滚
- 分支已存在：切换后 rebase/pull，再提交
- 推送失败（权限或网络）：保留本地 commit，重试 push

## 数据流
1. 服务器 JSON 数据（`data/*.json`）
2. 迁移脚本读取并标准化
3. 根据 `input` 在 PostgreSQL 中 upsert（更新优先）
4. UI 与执行模块继续从 DB 读取（回退 JSON）

## 预期结果
- 仓库中存在完整 `release/2.1` 部署文档
- 迁移策略明确满足“按 input 覆盖”
- 代码提交到 `release/2.1`，具备可发布状态