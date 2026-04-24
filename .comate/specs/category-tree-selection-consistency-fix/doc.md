# Category Tree Selection Consistency Fix

## 背景与问题定义
在 `Test Cases Management` 页面中，目录树与用例表格存在状态不同步问题：
1. 点击子节点后页面会刷新，但表格仍显示全量数据。
2. 点击“新建目录”时，父目录上下文经常回落到“全部用例”（顶级目录），而不是当前选中节点。

这导致 UI 选中态、筛选态、对话框上下文三者不一致。

---

## 需求场景与处理逻辑

### 场景 A：目录切换后表格应按节点过滤
- 用户在目录树点击任一节点（如“机场礼遇”）。
- 系统应将当前选中 `category_id` 持久化到 `st.session_state.selected_category`。
- 表格筛选函数应读取该值并过滤 `st.session_state.df`。
- 当节点为 `root` 时，显示全部用例（保持默认行为）。

### 场景 B：新建目录应继承当前选中父节点
- 用户在目录树选中某个非 root 节点后点击“新建目录”。
- 弹窗应展示 `父目录: <当前选中路径>`。
- 仅当当前节点为 `root` 时，才进入“创建顶级目录”模式。

### 场景 C：异常时不应静默回退为全量
- 分类筛选相关异常不能直接 `pass`，否则会伪装为“筛选不生效”。
- 至少输出日志并保留可观测性，避免误判为业务逻辑正确。

---

## 架构与技术方案

核心思路：将“目录树选择状态”收敛为**唯一可信源** `st.session_state.selected_category`，并使组件渲染与业务过滤都只读写该字段。

### 方案要点
1. **目录树返回值稳定化**
   - `_render_tree()` 不在空返回时默认强制 root。
   - 优先保留现有 `selected_category`，只有在树组件返回合法新值时才覆盖。
2. **目录树状态与 UI 状态绑定**
   - 将当前选中值映射到树组件初始 `index`（或稳定 tag 方案）以避免 rerun 后漂移。
3. **操作区上下文取值时机修正**
   - “新建目录”父节点读取应发生在树组件更新后，且直接读取 `st.session_state.selected_category`。
4. **筛选异常可观测化**
   - 替换 `except: pass` 为 `logger.warning(...)`，避免静默失败。

---

## 影响文件与修改范围

### 1) `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/components/category_widget.py`
- 修改类型：状态流修正、事件顺序修正
- 影响函数：
  - `render_category_widget()`
  - `_render_tree(tree, service)`
- 关键改动：
  - 修复选中值在 rerun 中被 root 覆盖的问题。
  - 使操作按钮（新建/重命名/删除）使用当前真实选中节点。
  - 新建目录时：`add_category_parent_id = None if selected == 'root' else selected`。

### 2) `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/testcases.py`
- 修改类型：筛选链路增强、诊断增强
- 影响函数：
  - `filter_test_cases(...)`
  - `render_testcases_page()`（仅必要的状态读取对齐）
- 关键改动：
  - 确认 `selected_category -> filter_category -> filtered_df` 链路单向稳定。
  - 分类筛选异常改为可观测日志，不再静默吞掉。

---

## 实现细节（示例代码片段）

### 目录树选择值稳定化（示意）
```python
current_selected_id = st.session_state.get('selected_category', 'root')
selected_index_list = sac.tree(..., index=default_index, return_index=True, key='sac_category_tree')

new_selected_id = current_selected_id
if selected_index_list and isinstance(selected_index_list, list):
    try:
        sel_idx = int(selected_index_list[0])
        new_selected_id = index_map.get(sel_idx, current_selected_id)
    except (ValueError, TypeError):
        logger.warning('Invalid tree selected index: %s', selected_index_list)

if new_selected_id != current_selected_id:
    st.session_state.selected_category = new_selected_id
    st.rerun()

return st.session_state.get('selected_category', 'root')
```

### 新建目录父级上下文（示意）
```python
selected_id = st.session_state.get('selected_category', 'root')
if st.button('➕ 新建目录', ...):
    st.session_state.show_add_category_dialog = True
    st.session_state.add_category_parent_id = None if selected_id == 'root' else selected_id
```

### 筛选异常可观测（示意）
```python
try:
    category_ids = get_category_ids_with_children(category_id)
    if category_ids:
        filtered = filtered[filtered['category_id'].isin(category_ids)]
except Exception as e:
    logger.warning('Category filtering failed, category_id=%s, err=%s', category_id, e)
```

---

## 边界条件与异常处理

1. **root 节点**
   - root 保持“全部用例”语义，不做 category_id 限定。
2. **空目录/无子目录**
   - 能正常显示 0 条，不回退全量。
3. **目录被删除后仍被选中**
   - 若 `selected_category` 不存在于树中，回退 root，并记录日志。
4. **树组件返回异常值**
   - 保留原 selection，不覆盖为 root。
5. **数据库/查询异常**
   - 页面可用但告警可见，不使用静默吞错。

---

## 数据流路径

1. 用户点击目录树节点。
2. `_render_tree()` 解析并更新 `st.session_state.selected_category`。
3. `render_testcases_page()` 读取该值赋给 `filter_category`。
4. `filter_test_cases()` 基于 category + tags + id range + keyword 计算 `filtered_df`。
5. 表格渲染 `filtered_df`。
6. 新建目录点击时读取同一 `selected_category` 作为 `add_category_parent_id`。

---

## 预期结果

1. 点击“机场礼遇”后，仅显示该节点（含子节点）用例。
2. 点击“全部用例”后，显示全量用例。
3. 在“机场礼遇”节点下点击新建目录，弹窗显示 `父目录: 机场礼遇`。
4. 切换任意节点时，表格数据稳定响应刷新。
5. 发生筛选异常时可在日志看到明确原因。
