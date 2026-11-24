# 目录数量与表格数据强一致修复设计

## 场景与结论

用户确认未设置任何筛选条件，但仍出现：
- 左侧目录显示有用例数量
- 右侧表格为空

该现象说明问题不在筛选输入，而在**数据刷新与缓存一致性**。

## 根因分析

1. 左侧目录数量来自 DB 聚合 + session 缓存 `category_counts_cache`，不是每次重算。
2. 右侧表格来自 `st.session_state.df`，仅在初始化或 `_force_reload` 为真时才 `load_data()`。
3. 在“移动目录/导入/删除/新增”等写操作后，存在路径未统一执行：
   - 清理 `category_counts_cache`
   - 置 `_force_reload=True`

因此会出现左侧与右侧口径短暂分离，表现为“左侧有数，右侧空表”。

## 技术方案

### 方案目标
把 Test Cases 页面改为“写后统一失效 + 下一轮强制重载”，保证目录计数与表格展示一致。

### 方案细节

1. 新增统一失效函数（在 `app/ui/testcases.py` 内）
- `invalidate_case_views()`：
  - `st.session_state.pop('category_counts_cache', None)`
  - `st.session_state['_force_reload'] = True`
  - `st.session_state['df_preprocessed'] = False`

2. 所有会修改测试用例或目录归属的操作后，统一调用该函数
- 移动目录
- 删除用例
- 导入新增/更新
- 表格行新增/删除
- 批量 priority 更新（同样会影响当前视图）

3. 在目录切换逻辑保持轻量兜底
- 保留已有页码重置
- 不再仅依赖目录切换来刷新计数

## 影响文件

- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/testcases.py`
  - 新增失效函数
  - 在各写操作成功分支中调用

- （可选）`/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/components/category_widget.py`
  - 仅保留读取缓存，不承担写后同步责任

## 边界与异常

- 写操作失败时不触发失效，避免误刷新掩盖错误。
- `__all__` 与子目录切换逻辑保持不变。
- 不改目录名处理，不影响大小写敏感要求。

## 预期结果

- 无筛选条件下，点击有数量的目录节点，右侧稳定显示对应数据。
- 写操作后无需手动刷新或来回切目录，左右视图自动一致。