# 增量保存与分页修复 - 完成总结

## 修改文件

| 文件 | 改动 |
|------|------|
| `app/services/test_case_service.py` | 新增 `upsert_records()` 方法 |
| `app/utils.py` | 新增 `save_records()` 函数 |
| `app/ui/testcases.py` | 自动保存逻辑改为增量保存；分页 rerun scope 改为 app；`use_container_width` 全部替换为 `width=` |

## 解决的问题

1. **全量保存 → 增量保存**：编辑 1 条用例不再触发 3694 次 DB 查询。改为通过 `__row_key` 逐行对比只提取修改的行，调用 `save_records()` 做精准 upsert。

2. **批量编辑丢失**：不再在自动保存后整体替换 `st.session_state.df`、不再调用 `rebuild_internal_ids`，保持 DF 对象和 `__row_key` 稳定，允许用户连续编辑多行并逐次保存。

3. **分页失效**：分页跳转处 `st.rerun()` 改为 `st.rerun(scope="app")`，确保外层 `display_df` 被重新计算，分页切片与数据源对齐。

4. **弃用告警**：`use_container_width=True` → `width="stretch"`，`use_container_width=False` → `width="content"`，共替换 18 处。

## ID 安全保证

增量保存路径（`save_records` → `upsert_records`）不包含任何 ID 自动生成/重分配逻辑。现有用例 ID 不会被系统修改，只有用户手动编辑才能改变 ID。
