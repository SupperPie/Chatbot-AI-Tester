# 目录计数与表格数据一致性修复任务计划

- [x] Task 1: 在 Test Cases 页面实现统一失效机制
    - 1.1: 在 `app/ui/testcases.py` 新增 `invalidate_case_views()`
    - 1.2: 失效函数统一处理 `category_counts_cache` 清理与 `_force_reload` 标记
    - 1.3: 保持 `df_preprocessed` 与分页状态在重载后可正确恢复

- [x] Task 2: 接入所有写操作后的统一失效调用
    - 2.1: 移动目录成功后调用失效函数
    - 2.2: 删除用例成功后调用失效函数
    - 2.3: 导入（新增/更新）成功后调用失效函数
    - 2.4: data_editor 新增/删除/批量 priority 修改成功后调用失效函数

- [x] Task 3: 验证目录切换与口径一致性
    - 3.1: 无筛选条件下，点击有数量目录，表格可见对应数据
    - 3.2: 写操作后无需手动刷新，左右视图保持一致
    - 3.3: `__all__` 与子目录切换保持正常

- [x] Task 4: 语法检查与总结
    - 4.1: 执行 `python3 -m py_compile app/ui/testcases.py`
    - 4.2: 更新 `tasks.md` 勾选状态
    - 4.3: 生成 `summary.md` 汇总修复结果
