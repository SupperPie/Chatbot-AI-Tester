# Testcase Table Operations Fix

- [x] Task 1: 恢复表格行内新增功能
    - 1.1: 在 auto-save block 之前检测新增行（`__row_key` 为空或不在原 page_df 中）
    - 1.2: 为新增行分配 `__row_key`、设置默认字段（category_id、type、Select 等）
    - 1.3: 将新增行追加到 `st.session_state.df`，触发 `save_data()` 持久化并刷新页面

- [x] Task 2: Move 操作后清除选中状态
    - 2.1: 在 `move_to_category_dialog` 的 `st.rerun()` 前添加 `st.session_state.df['Select'] = False`

- [x] Task 3: 验证对话分组逻辑（仅验证，无代码修改）
    - 3.1: 确认生成 prompt、解析代码、加载/保存逻辑、执行引擎均遵循 multi_turn 规则
    - 3.2: 标记为已验证通过
