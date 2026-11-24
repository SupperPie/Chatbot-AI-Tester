# 目录计数与表格数据一致性修复总结

## 已完成内容

本次针对“左侧目录显示有数量、右侧表格无数据”的一致性问题，完成了写后统一失效机制。

### 1) 新增统一失效函数
- 文件：`app/ui/testcases.py`
- 新增：`invalidate_case_views(reset_page: bool = False)`
- 行为：
  - 清理 `category_counts_cache`
  - 设置 `_force_reload = True`
  - 设置 `df_preprocessed = False`
  - 可选重置分页到第一页

### 2) 接入所有关键写操作成功分支
已在以下写操作完成后统一调用失效函数：
- 删除用例（确认删除弹窗）
- 移动目录（移动弹窗）
- 批量设置 Priority
- 导入保存成功
- data_editor 删除行
- data_editor 新增行

### 3) 口径一致性结果
- 保持目录筛选主链路：`selected_category -> filter_category -> filter_test_cases`
- 写操作后下一轮会强制重载右侧数据并失效左侧计数缓存，减少“左有数右为空”的不同步窗口。

## 校验结果

- 语法检查通过：
  - `python3 -m py_compile app/ui/testcases.py`

## 影响文件

- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/testcases.py`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/.comate/specs/category-cache-df-sync-fix/tasks.md`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/.comate/specs/category-cache-df-sync-fix/summary.md`
