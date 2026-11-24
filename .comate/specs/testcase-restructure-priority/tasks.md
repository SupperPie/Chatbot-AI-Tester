# Test Case 重构与 Priority 体系实施计划

- [x] Task 1: 数据模型与数据库迁移（Priority）
    - 1.1: 在 `test_cases` 表新增 `priority` 字段（允许为空）
    - 1.2: 历史数据不回填（`NULL/''` 保持原样）
    - 1.3: 更新 `app/models/test_case.py` 增加 `priority` 列定义

- [x] Task 2: 服务层支持 Priority 与批量更新
    - 2.1: 更新 `app/services/test_case_service.py` 读写逻辑透传 `priority`
    - 2.2: 增加批量更新 Priority 方法（按 `id` 列表）
    - 2.3: 增加“按条件批量更新 Priority”方法（用于历史补齐/筛选结果批改）

- [x] Task 3: 生成流程 Priority 分配（P1:P2=1:3）
    - 3.1: 在 `app/ui/tester.py` 生成结果上增加 `priority` 字段
    - 3.2: 按“单次 PRD 全量结果（跨 AC）”计算 P1 数量并分配
    - 3.3: 保存入库时写入 priority，并显示分配统计

- [x] Task 4: Test Cases 页面 Priority 能力
    - 4.1: 在 `app/ui/testcases.py` 表格新增 `priority` 列（P0/P1/P2 下拉编辑）
    - 4.2: 新增 Priority 筛选（支持多选）
    - 4.3: 新增批量改 Priority 操作（选中行批量设值）
    - 4.4: 空 priority 不做自动修复；保留人工批量设置入口（按选中/筛选范围）

- [x] Task 5: 目录结构重构能力（节点排序 + 换父）
    - 5.1: 在 `app/services/category_service.py` 新增 `reorder_siblings(parent_id, ordered_ids)`
    - 5.2: 在 `app/services/category_service.py` 新增 `move_node(cat_id, new_parent_id)`
    - 5.3: 在 `move_node` 中递归修正子树 `path/level` 并校验防循环/层级上限

- [x] Task 6: Test Cases 批量迁移与目录操作 UI
    - 6.1: 在 `app/ui/testcases.py` 规范化“批量移动到目录”入口（基于选中行）
    - 6.2: 在目录组件（`category_widget.py` / `category_tree.py`）增加同级排序入口
    - 6.3: 增加节点换父入口（选择新父目录）并刷新树与列表
    - 6.4: 校验目录名称大小写敏感（创建/重命名/展示全链路保持输入原样）

- [x] Task 7: 工具层与加载层兼容
    - 7.1: 在 `app/utils.py` 的 DataFrame 列结构中加入 `priority`
    - 7.2: 确认导入、保存、编辑流程不会丢失 priority

- [x] Task 8: 校验与回归
    - 8.1: 语法检查：`python3 -m py_compile` 覆盖受影响文件
    - 8.2: 功能回归：生成→保存→筛选→批量改优先级→批量迁移目录
    - 8.3: 目录回归：同级排序、节点换父、path/level 正确性
    - 8.4: 历史数据回归：空 priority 保持为空且不被自动改写，可被人工批量编辑
    - 8.5: 命名回归：目录名输入 `abc/ABC/aBc` 后展示与存储严格一致，不发生自动格式化
