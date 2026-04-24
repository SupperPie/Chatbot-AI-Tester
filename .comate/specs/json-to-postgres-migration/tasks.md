# JSON 数据存储迁移到 PostgreSQL 任务清单

- [ ] Task 1: 项目基础设施搭建
    - 1.1: 更新 requirements.txt，添加 psycopg2-binary、sqlalchemy、python-dotenv
    - 1.2: 创建 app/config.py 配置管理（DATABASE_URL 环境变量）
    - 1.3: 创建 app/database.py 数据库连接层
    - 1.4: 创建 .env.example 示例配置文件

- [ ] Task 2: 数据库模型定义
    - 2.1: 创建 app/models.py 定义所有 ORM 模型
    - 2.2: 定义 Category 模型（3级树形目录）
    - 2.3: 定义 Tag 模型（扁平化标签）
    - 2.4: 定义 TestCase 模型（含 input_hash、category_id、tags）
    - 2.5: 定义 TestHistory 和 TestResult 模型（含 source 字段）
    - 2.6: 定义 BlindReview 和 BlindReviewItem 模型
    - 2.7: 定义 ApiConfig 模型
    - 2.8: 定义 DraftBatch 和 TestCaseDraft 模型（草稿表）
    - 2.9: 定义 Attachment 和内容关联模型（多媒体支持）

- [ ] Task 3: 数据库表创建脚本
    - 3.1: 创建 scripts/init_db.py 初始化数据库表
    - 3.2: 添加所有索引定义
    - 3.3: 测试表创建和连接

- [ ] Task 4: 数据迁移脚本
    - 4.1: 创建 scripts/migrate_json_to_postgres.py
    - 4.2: 实现 DataMigrator 类（备份、日志、分批提交）
    - 4.3: 实现 migrate_categories() 迁移分类目录
    - 4.4: 实现 migrate_tags() 迁移预定义标签
    - 4.5: 实现 migrate_test_cases() 迁移测试用例（含 input_hash 去重）
    - 4.6: 实现 migrate_history() 迁移测试历史和结果
    - 4.7: 实现 migrate_blind_reviews() 迁移盲测评审
    - 4.8: 实现 migrate_api_configs() 迁移 API 配置
    - 4.9: 实现 verify_migration() 校验迁移完整性

- [ ] Task 5: 数据迁移去重与导入
    - 5.1: 迁移脚本支持 source 参数标记数据来源（local/server）
    - 5.2: 测试用例迁移：基于 input_hash 去重，相同 input 跳过
    - 5.3: 测试报告迁移：全部保留，通过 source 字段区分来源
    - 5.4: 实现 export_to_json() 导出功能（用于备份）

- [ ] Task 6: 重写 app/utils.py 核心数据操作
    - 6.1: 重写 load_data() 从数据库加载测试用例
    - 6.2: 重写 save_data() 保存测试用例到数据库
    - 6.3: 重写 save_history() 保存测试历史（逐条原子写入）
    - 6.4: 重写 delete_reports() 删除测试报告
    - 6.5: 重写 update_history_entry() 更新历史记录
    - 6.6: 新增 get_category_tree() 获取分类目录树
    - 6.7: 新增 add_category() 添加分类目录
    - 6.8: 新增 move_test_case_to_category() 移动用例到分类

- [ ] Task 7: Tester 页面草稿功能
    - 7.1: 实现 start_generation_batch() 开始生成批次
    - 7.2: 实现 save_draft_case() 逐条保存草稿
    - 7.3: 实现 complete_batch() 完成批次
    - 7.4: 实现 confirm_drafts() 确认草稿转正式表
    - 7.5: 实现 discard_drafts() 丢弃草稿
    - 7.6: 修改 app/ui/tester.py 集成草稿功能

- [ ] Task 8: Test Report 原子性写入
    - 8.1: 实现 create_test_history() 创建测试记录
    - 8.2: 实现 save_test_result_atomic() 单条原子写入
    - 8.3: 实现 finalize_test_history() 更新最终状态
    - 8.4: 实现 get_test_report() 支持实时查看进行中报告
    - 8.5: 修改 app/test_engine.py 使用新的写入方式

- [ ] Task 9: 重写 app/ui/blind_review.py
    - 9.1: 重写 load_reviews() 从数据库加载
    - 9.2: 重写 save_reviews() 保存到数据库

- [ ] Task 10: 重写 app/routers/cases.py
    - 10.1: 修改 load_cases() 使用数据库
    - 10.2: 修改 save_cases() 使用数据库

- [ ] Task 11: 多媒体支持基础（预留）
    - 11.1: 创建 app/services/attachment.py 附件服务
    - 11.2: 实现文件上传和存储逻辑
    - 11.3: 实现内容与附件关联

- [ ] Task 12: 测试与验证
    - 12.1: 本地环境迁移测试
    - 12.2: 验证 UI 页面功能正常
    - 12.3: 验证数据完整性
    - 12.4: 编写迁移文档和操作手册
