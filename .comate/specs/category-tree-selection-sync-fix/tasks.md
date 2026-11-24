# 目录树选中与右侧表格同步修复任务计划

- [x] Task 1: 修复目录树选中节点 ID 解析
    - 1.1: 在 `app/ui/components/category_widget.py` 梳理 `sac.tree(return_index=True)` 返回结构
    - 1.2: 替换 `selected_index_list[-1]` 的不稳定映射逻辑，改为与返回结构严格对齐的解析
    - 1.3: 确保仅在目录 ID 实际变化时更新 `st.session_state.selected_category`
    - 1.4: 保持 `__all__` / 非法返回回退逻辑稳定

- [x] Task 2: 对齐 Test Cases 页面目录筛选链路
    - 2.1: 在 `app/ui/testcases.py` 校验 `selected_category -> filter_category -> filter_test_cases` 单一路径
    - 2.2: 保持现有筛选能力（Priority/Tags/ID/关键词）不被破坏
    - 2.3: 增加必要调试日志，便于确认目录 ID 与筛选结果一致

- [x] Task 3: 目录口径一致性与边界回归
    - 3.1: 验证 root（`__all__`）与子节点切换展示正确
    - 3.2: 验证新增/删除目录后树映射刷新与选中稳定
    - 3.3: 验证目录名大小写敏感场景不受影响（按 category_id 过滤）

- [x] Task 4: 语法检查与结果固化
    - 4.1: 对受影响文件执行 `python3 -m py_compile`
    - 4.2: 更新 `tasks.md` 勾选状态并记录执行结果
    - 4.3: 完成后生成 `summary.md` 汇总修复结果与验证结论
