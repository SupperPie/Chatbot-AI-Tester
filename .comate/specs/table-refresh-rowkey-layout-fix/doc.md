# Table Refresh, Row Identity, and Layout Fix

## 需求归类
这是一个前端交互与状态一致性修复需求，覆盖：
1. 节点切换后的数据刷新正确性。
2. ID 可重复语义恢复（多轮 session）。
3. 表格行唯一标识从 `id` 解耦。
4. 操作栏与分页栏布局调整。

---

## 场景与处理逻辑

### 场景 A：在“全部用例”与子节点间切换，表格数据不应丢失或残留
- 当前问题：切到子节点后再回“全部用例”，仍停留在上一个节点数据（或出现空表）。
- 目标：
  - 保持一个“全量主数据集”作为唯一数据源。
  - 分类筛选仅作用于视图层（filtered_df/page_df），不回写覆盖主数据集。
  - 切回 root 时必须强制使用主数据集重算 `filtered_df`，不能复用上次子节点视图缓存。
  - 切回 root 时重置分页到第 1 页，避免因页码越界导致误显示为旧数据或空数据。

### 场景 B：ID 允许重复（同一 session 多轮）
- 当前问题：多处逻辑把 `id` 当唯一键使用，重复 ID 时选择/编辑同步会失效。
- 目标：
  - 取消前端层面对 ID 唯一性的依赖。
  - 引入仅前端使用的稳定行标识（如 `__row_key`），用于选择同步、编辑同步、分页回写。
  - 保证 `id` 可重复展示，不触发重复 key 报错。

### 场景 C：布局调整
- Select All / Cancel All 与分页控件同一行。
- 缩小 Select / Cancel 按钮宽度。
- 缩小“每页显示条数”选择器宽度。

---

## 架构与技术方案

### 1) 数据状态分层
- `st.session_state.df_master`：全量主数据，仅在加载/保存后更新。
- `filtered_df`：根据分类/标签/ID区间/关键词从 `df_master` 计算得到。
- `page_df`：分页视图。

关键原则：
- 禁止将 `filtered_df` 或 `page_df` 直接赋值给 `df_master`。

### 2) 行唯一标识解耦
- 在数据加载后为每行生成 `__row_key`（不可编辑、仅前端内部使用）。
- 同步 Select 和编辑结果时，统一使用 `__row_key` 定位行。
- `id` 仍然是业务字段，可重复、可展示，不作为定位键。

### 3) 表格 key 与状态刷新
- `st.data_editor` 的 widget key 结合分页+筛选签名（至少包含 `selected_category`），避免节点切换后的组件状态复用污染。
- 切换分类后分页回到第一页，避免“页码超界看空”的伪空数据问题。
- 当 `selected_category == 'root'` 时，禁用节点缓存复用路径，直接从 `df_master` 重建视图，确保不会停留在上一个节点数据。

### 4) 布局重排
- 将 “Select All / Cancel All / 统计 / 每页显示 / 分页器” 放在同一行容器中。
- 使用更紧凑列比例（按钮窄宽、分页器占主宽）。

---

## 影响文件与修改点

### `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/testcases.py`
- 需要修改函数：
  - `render_testcases_page()`
  - `render_paginated_table(display_df)`
  - 选择同步、自动保存、分页栏布局片段
- 修改类型：
  - 状态管理重构（主数据集与视图数据集分离）
  - 行定位逻辑从 `id` 改为 `__row_key`
  - UI 布局调整

### `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/utils.py`（可选最小改动）
- 仅在必要时补充：确保加载后可附加前端内部列，不落盘。
- 默认优先在 `testcases.py` 内部处理，不改后端数据结构。

---

## 实现细节（代码级示意）

### A. 生成并维护前端行键
```python
if '__row_key' not in df.columns:
    df['__row_key'] = [f"rk_{i}" for i in range(len(df))]
```

### B. 选择同步由 ID 改为 row_key
```python
page_keys = filtered_df.iloc[start_idx:end_idx]['__row_key'].tolist()
st.session_state.df_master.loc[
    st.session_state.df_master['__row_key'].isin(page_keys), 'Select'
] = True
```

### C. 编辑回写由 ID 改为 row_key
```python
rk = edited_page_df.iloc[i]['__row_key']
mask = st.session_state.df_master['__row_key'] == rk
st.session_state.df_master.loc[mask, 'Select'] = edited_page_df.iloc[i]['Select']
```

### D. 切换节点时分页重置
```python
if selected_category != st.session_state.get('last_selected_category', 'root'):
    st.session_state.testcases_current_page = 1
    st.session_state.last_selected_category = selected_category
```

### E. 布局合并同一行
```python
ctrl1, ctrl2, ctrl3, ctrl4, ctrl5 = st.columns([1.1, 1.1, 1.6, 1.0, 5.2])
# Select All / Cancel / Stats / page_size / pagination
```

---

## 边界条件与异常处理
- root 节点：必须显示 `df_master` 全量数据。
- 子节点无数据：显示 0 条，但不污染 `df_master`。
- 重复 ID：允许展示与编辑，不因重复而跳过同步。
- ID 含下划线：不做拆分、不做语义变换，按原值透传。
- 导入/保存：不改变服务器端结构；`__row_key` 为前端内部列，保存时剔除。

---

## 数据流
1. load_data() -> 初始化 `df_master` + `__row_key`。
2. 分类切换 -> 计算 filtered_df（只读）。
3. 分页 -> page_df。
4. 编辑/勾选 -> 按 `__row_key` 回写 `df_master`。
5. save_data() 前剔除前端内部列（`__row_key` 等）。

---

## 预期结果
1. 在 root 与子节点间反复切换，数据稳定显示。
2. 表格允许重复 ID，且无重复 key 报错。
3. Select All/Cancel 与分页同一行；按钮和每页选择器更紧凑。
4. 不修改服务器端数据结构，不破坏多轮 session 设计意图。
