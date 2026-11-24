# 测试用例重构与 Priority 体系设计

## 目标

围绕 Test Case 管理做两类增强：

1. **结构重构能力**
   - 支持将某节点下测试用例批量迁移到另一个节点
   - 支持目录节点位置调整：
     - 同级排序调整（A）
     - 节点整体换父（B）
   - 本次范围为 **A+B（C）**
   - 目录名称大小写敏感：输入什么就保留什么，不做自动大小写转换

2. **Priority 体系**
   - 测试用例增加 `priority` 字段：`P0 / P1 / P2`
   - 生成测试用例时默认仅生成 `P1/P2`，按 **1:3** 分配
   - 分配范围为 **整个 PRD 的全部生成结果（跨 AC 汇总）**
   - QA 后续可在 Test Cases 页面将部分用例更新为 `P0`

---

## 当前系统现状（基于代码走查）

### 目录与用例关系

- `test_cases` 表通过 `category_id` 关联 `categories.id`
- `CategoryService` 支持目录 CRUD、树结构、数量统计
- `TestCaseService` 已有 `update_category(test_case_ids, category_id)` 支持批量改目录
- Test Cases 页面已有“Move to Category”能力（基于选中行移动）

### 目录结构能力缺口

- 当前缺少“同级排序调整”接口
- 当前缺少“节点整体换父”接口
- `Category.path` 依赖父子关系，节点换父时需递归更新子节点 path/level

### Priority 能力缺口

- `TestCase` 模型当前无 `priority` 字段
- 生成流程未按比例分配优先级
- Test Cases 页面无 priority 展示/编辑/筛选入口

---

## 方案设计

## 一、数据模型改造

### 1) test_cases 增加 priority

- 新增字段：`priority VARCHAR(2)`，枚举值 `P0/P1/P2`
- 默认值：`P2`
- 迁移策略：历史数据保持原状（为空则继续为空，不强制回填）

模型变更：
- `app/models/test_case.py` 增加 `priority = Column(String(2), default='P2')`

服务层：
- `TestCaseService` 的读取/写入/upsert/insert 透传 `priority`

历史数据处理（按你最新要求）：
- 历史 `priority IS NULL/''` 数据保持为空，不做自动回填
- Test Cases 页面增加批量操作：
  - 对选中用例批量设为 `P0/P1/P2`
  - 对筛选结果一键批量设值（可选，带二次确认）
- 该批量编辑能力主要用于 QA 批量把候选用例提升为 `P0` 或统一重标优先级

### 2) categories 增强排序与换父能力

已有字段：`parent_id`, `path`, `level`, `sort_order`

新增服务方法（`CategoryService`）：
- `reorder_siblings(parent_id, ordered_ids)`：按传入顺序重写同级 `sort_order`
- `move_node(cat_id, new_parent_id)`：节点换父，并递归修正：
  - 当前节点 `parent_id/level/path/sort_order`
  - 所有后代 `path` 前缀替换 + `level` 重算

约束：
- 禁止移动 root
- 禁止移动到自己或自己的后代（防循环）
- 禁止超过最大层级（当前规则为 3 级）
- 目录命名保持原样（case-sensitive），create/update/display 全链路不做 `capitalize/title/lower/upper` 规范化

---

## 二、业务流程改造

### 1) 批量迁移用例到目录

在 Test Cases 页面提供明确入口：
- 选中多条用例 → 选择目标目录 → 提交
- 底层调用 `TestCaseService.update_category(ids, target_category_id)`
- 成功后同步刷新 `st.session_state.df`

### 2) 目录位置调整

提供两种操作：

- 同级排序（上移/下移或拖拽后提交顺序）
- 节点换父（选择新父目录）

操作后：
- 刷新目录树
- 刷新筛选态与列表
- 保证 path、level、sort_order 一致

### 3) 生成时 Priority 1:3（P1:P2）

适用范围：**同一次 PRD 生成出的全部用例（跨 AC）**

算法：
- 设总数 `N`
- `P1_count = round(N * 1/4)`（至少 1，若 N>0）
- 其余为 `P2`
- 分配顺序：按生成稳定顺序（不随机），前 `P1_count` 条设为 `P1`，其余 `P2`

备注：
- 不自动生成 `P0`
- `P0` 由 QA 在 Test Cases 页面手动改

---

## 三、UI 改造

### 1) Test Cases 页面

- 新增列：`priority`
  - 展示值：P0/P1/P2
  - 编辑控件：selectbox
- 新增筛选：按 priority 过滤（支持多选）
- 批量操作：
  - 批量改 priority（例如选中后设为 P0）
  - 批量移动目录（已有能力规范化）

### 2) 生成页面（Tester）

- 生成结果区增加 `priority` 列
- 保存入库时写入 `priority`
- 显示分配统计：`P1 x 条, P2 x 条`

### 3) 目录管理组件

- 新增目录排序操作入口
- 新增节点换父入口（选择目标父）

---

## 四、影响文件（初步）

- 数据与服务
  - `app/models/test_case.py`
  - `app/services/test_case_service.py`
  - `app/services/category_service.py`
  - `create_tables.sql` 或迁移脚本

- UI
  - `app/ui/testcases.py`
  - `app/ui/tester.py`
  - `app/ui/components/category_widget.py`
  - （若有）`app/ui/components/category_tree.py`

- 工具与加载
  - `app/utils.py`（DataFrame 列结构需包含 priority）

---

## 五、边界与异常处理

1. 目录移动边界
- 目标父不存在 → 拒绝并提示
- 目标为自身/后代 → 拒绝并提示
- 超过最大层级 → 拒绝并提示
- 目录名大小写按输入保留，重命名后应精确展示（含大小写）

2. 批量操作一致性
- 目录变更与排序写入应在事务中执行
- 失败时回滚并提示具体错误

3. Priority 兼容
- 历史数据无 priority 时保持为空展示（不自动改写）
- 仅新生成用例按规则写入 `P1/P2`；人工编辑时可设 `P0/P1/P2`

4. 生成比例边界
- N=0：不分配
- N=1：默认给 `P1`（满足“有高优先用例可供 QA 快速 review”）

---

## 六、验收标准

1. 目录重构
- 可将某节点下选中/全部用例迁移到目标节点
- 可调整同级顺序
- 可将节点换父，且子树 path/level 全量正确

2. Priority
- 生成后自动有 `P1/P2` 且整体比例约 1:3
- Test Cases 页面可查看/筛选/编辑 priority
- QA 可将任意用例改为 `P0`

3. 数据一致性
- 重启页面后数据不丢失
- 批量操作后 DB 与 UI 一致

---

## 七、实施策略

- 先做数据层（字段 + service）
- 再做目录结构操作接口（排序/换父）
- 再做 UI（priority + 批量重构）
- 最后做回归测试（生成、保存、筛选、移动、排序、换父）
