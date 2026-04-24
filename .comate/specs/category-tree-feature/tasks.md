# Test Cases 目录树功能实现任务

- [x] Task 1: 创建 Category 数据库模型
    - 1.1: 在 app/models/ 下创建 category.py 定义 Category 模型
    - 1.2: 在 app/models/test_case.py 中添加 category_id 外键字段
    - 1.3: 确保模型间的关系定义正确（CASCADE 删除）

- [x] Task 2: 创建 CategoryService 服务层
    - 2.1: 在 app/services/ 下创建 category_service.py
    - 2.2: 实现 get_tree() 获取目录树结构
    - 2.3: 实现 create() 创建目录（含层级校验）
    - 2.4: 实现 update() 重命名目录（含路径更新）
    - 2.5: 实现 delete() 删除目录（返回受影响用例数）
    - 2.6: 实现 get_case_count() 统计目录下用例数量

- [x] Task 3: 创建数据迁移脚本
    - 3.1: 创建 scripts/migrate_categories.py
    - 3.2: 实现根目录初始化逻辑
    - 3.3: 实现现有测试用例归属到根目录的迁移逻辑

- [x] Task 4: 创建目录树 UI 组件
    - 4.1: 创建 app/ui/components/category_tree.py
    - 4.2: 实现树形结构渲染（缩进 + 图标 + 用例数量）
    - 4.3: 实现目录选择状态管理
    - 4.4: 实现操作菜单（重命名/添加子目录/删除）

- [x] Task 5: 创建目录操作对话框组件
    - 5.1: 创建 app/ui/components/category_dialogs.py
    - 5.2: 实现新建目录对话框
    - 5.3: 实现重命名目录对话框
    - 5.4: 实现删除确认对话框（显示受影响用例数）

- [x] Task 6: 改造 testcases.py 页面布局
    - 6.1: 调整页面为左右两栏布局（目录树 25% + 内容 75%）
    - 6.2: 集成目录树组件到左侧栏
    - 6.3: 处理对话框状态触发逻辑

- [x] Task 7: 实现按目录筛选测试用例
    - 7.1: 创建 app/ui/components/category_selector.py 目录选择组件
    - 7.2: 在 testcases.py 集成目录选择下拉框
    - 7.3: 筛选功能基础框架完成（完整筛选需等数据迁移到数据库）

- [x] Task 8: 测试与验收
    - 8.1: 验证目录 CRUD 操作正常
    - 8.2: 验证层级限制（不超过3级）
    - 8.3: 验证删除目录时级联删除测试用例
    - 8.4: 验证迁移脚本执行后现有数据归属正确
