# Testcase Table Operations Fix - Summary

## 修改文件
| 文件 | 修改内容 |
|------|----------|
| `app/ui/testcases.py` | 新增行检测与持久化逻辑 (line 734-769); Move 后清除选中状态 (line 274) |

## Task 1: 恢复表格行内新增功能
- `st.data_editor` 已有 `num_rows="dynamic"` 支持新增行，但新增行因无 `__row_key` 导致 auto-save 无法匹配，数据丢失
- 在 auto-save block 前新增检测逻辑：比较 `edited_page_df` 与 `page_df` 的行数和 `__row_key`，识别新增行
- 为新增行分配 `__row_key`、设置默认 `category_id`/`type`/`Select`，追加到 `st.session_state.df`
- 调用 `save_data()` 持久化到 DB（自动分配 TC ID），刷新页面

## Task 2: Move 操作后清除选中状态
- 在 `move_to_category_dialog` 的 `st.rerun()` 前添加 `st.session_state.df['Select'] = False`
- 纯 UI 状态重置，一行修改

## Task 3: 对话分组逻辑验证
- 确认各层（生成 prompt → 解析 → 加载/保存 → UI 排序 → 执行引擎）均遵循 "ID 相同 + type=multi_turn = 同一对话, turn_index = 轮数" 规则
- 无需代码修改
