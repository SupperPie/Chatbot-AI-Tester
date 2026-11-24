# 子目录有数量但表格为空修复设计

## 需求场景与处理逻辑

在 Test Cases 页面中，左侧目录树显示某子节点有用例数量，但点击后右侧表格为空。用户确认未设置额外筛选条件。

处理目标：
- 目录树选中节点后，右侧必须按**同一个 category_id**过滤。
- 左侧计数与右侧列表展示口径一致。
- 不引入对目录名的大小写改写逻辑。

## 根因判断（基于现有代码）

高概率根因是目录树返回索引值后被错误映射：
- `sac.tree(return_index=True)` 的返回结构与当前 `index_map` 的“扁平索引映射”不稳定匹配。
- 现逻辑使用 `selected_index_list[-1]` 映射目录 ID，可能得到错误 category_id。
- 右侧按错误 category_id 筛选后为空。

相关代码路径：
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/components/category_widget.py`（目录树渲染与选中解析）
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/testcases.py`（filter_category 传递与表格筛选）
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/components/category_selector.py`（category_id 筛选接口）

## 架构与技术方案

采用“稳定 ID 映射 + 统一筛选口径”方案：

1. 目录树选中解析修正（核心）
- 在 `category_widget.py` 中，不再依赖 `selected_index_list[-1]` 直接扁平映射。
- 将树节点构建过程中的索引映射改为与返回结构严格对齐（路径索引逐层解析到最终节点），确保最终得到正确目录 ID。
- 仅当目录 ID 发生变化时更新 `st.session_state.selected_category`。

2. 目录切换后的筛选一致性兜底
- 在 `testcases.py` 中保持 `filter_category = selected_category` 的单一来源。
- 在目录切换时追加轻量校验日志（category_id 与 filtered count）便于后续排查。
- 不自动更改用户已输入的其他筛选项（除非确认存在历史残留导致误解时再做二次优化）。

3. 口径一致性验证
- 左侧计数（DB）与右侧列表（session df + category filter）以同一 category_id 做对照验证。

## 影响文件与修改点

1) `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/components/category_widget.py`
- 修改类型：逻辑修复
- 受影响函数：`_render_tree`
- 修改内容：
  - 修正 `sac.tree` 返回值到 category_id 的映射逻辑
  - 保留去抖逻辑，但确保去抖前后选中 ID 一致

2) `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/testcases.py`
- 修改类型：筛选链路一致性增强（最小改动）
- 受影响函数：`render_testcases_page`
- 修改内容：
  - 保持 `selected_category -> filter_category -> filter_test_cases` 的直接透传
  - 增加必要调试输出（不改变业务行为）

3) `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/.comate/specs/category-tree-selection-sync-fix/tasks.md`
- 后续生成任务拆解

## 实现细节（示意）

### A. 目录选中解析

```python
# 伪代码：按 sac.tree 返回结构解析最终节点 ID
selected = sac.tree(..., return_index=True)
new_selected_id = resolve_selected_id(selected, tree_structure, id_map)

if new_selected_id != current_selected_id:
    st.session_state.selected_category = new_selected_id
```

### B. 右表筛选透传

```python
filter_category = selected_category
filtered_df = filter_test_cases(
    st.session_state.df,
    category_id=filter_category,
    ...
)
```

## 边界条件与异常处理

- 根节点 `__all__`：保持全量展示逻辑不变。
- 非法/空返回：回退当前已选目录，不触发误切换。
- 树结构变化（新增/删除目录后）：重建映射并按当前 session 重新定位。
- 目录名大小写敏感：仅使用 category_id 过滤，不基于 name 推断，避免大小写误差。

## 数据流路径

用户点击目录树节点
→ `category_widget._render_tree` 解析选中节点
→ 更新 `st.session_state.selected_category`
→ `testcases.render_testcases_page` 读取 selected_category
→ `filter_test_cases(... category_id=selected_category)`
→ 表格展示对应目录数据

## 预期结果

- 点击任意有数量的子节点时，右侧表格稳定显示对应用例。
- 不再出现“左侧有数、右侧空表（因选中映射错误）”的情况。
- 不影响 Priority、标签、ID 范围、关键词等现有筛选能力。