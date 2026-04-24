# Table Refresh / RowKey / Layout 修复总结

## 已完成任务
已按 `tasks.md` 完成全部 5 个顶层任务（含你新增的 Select All 跨页语义要求）。

## 核心修复内容

### 1) 修复节点切换后 root 显示残留数据问题
- 文件：`app/ui/testcases.py`
- 关键修复：
  - 移除“将当前筛选视图覆盖主数据”的问题路径（历史上会导致切回 root 仍停留子节点数据）。
  - 新增节点切换检测并重置分页到第 1 页：
    - `last_selected_category` 与 `testcases_current_page` 联动。
  - 表格渲染后，执行逻辑改为重新基于主数据集计算当前筛选视图，确保使用最新选择状态。

### 2) 恢复 ID 可重复语义（多轮 session）
- 文件：`app/ui/testcases.py`
- 关键修复：
  - 新增前端内部稳定行键 `__row_key`（仅前端使用，不写入后端结构）。
  - 选择同步、编辑回写改为基于 `__row_key` 定位，不再依赖 `id` 唯一。
  - 保持 `id` 列可重复展示，不改变现有 ID 值（含下划线场景）。

### 3) 表格组件 key 与刷新联动
- 文件：`app/ui/testcases.py`
- 关键修复：
  - `st.data_editor` key 改为包含 `selected_category + current_page + page_size`，避免节点切换时组件缓存污染。
  - 分页组件 key 改为带 `selected_category`，保障不同节点分页状态隔离。

### 4) Select All 语义与布局调整
- 文件：`app/ui/testcases.py`
- 关键修复：
  - “☑️ Select All” 改为对当前表格数据（跨页）全选，不再只选当前页。
  - “当前页全选”由表格 `Select` 列 header 内建勾选能力承担。
  - 将 `Select All / Cancel ALL / 统计 / 每页显示 / 分页器` 合并到同一行。
  - 缩小 Select All、Cancel ALL、每页显示选择器占位宽度。

### 5) 前端内部列持久化保护
- 文件：`app/ui/testcases.py`
- 关键修复：
  - 所有 `save_data(...)` 调用前剔除 `__row_key`，避免污染 JSON/后端数据结构。
  - 保存后重新补回 `__row_key` 到会话内数据。

## 验证
- 已执行 lints 检查：
  - `app/ui/testcases.py` 无 lint 报错。

## 说明
- 这次修复严格遵守“不修改服务器端数据结构”的约束。
- 多轮会话的“ID 可重复”设计意图已在前端行定位逻辑中恢复并兼容。