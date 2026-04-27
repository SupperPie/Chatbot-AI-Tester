# Testcase Delete Fix — 执行总结

## 修复的 Bug

### Bug 1: 删除确认对话框不弹出
- **根因**: `page_edited` 比较包含 Select 列 → 勾选 checkbox 触发 auto-save → Select 被重置为 False → delete handler 找不到已选行
- **修复**: `testcases.py:712-715` — 排除 Select 列进行比较；auto-save 同步内容时跳过 Select 列；保存后恢复原有选中状态

### Bug 2: 删除不持久化到 DB
- **根因**: `save_data()` 只写 JSON，`load_data()` 读 DB → 删除后重新加载数据回来
- **修复**:
  - `test_case_service.py` 新增 `delete_by_ids()` 和 `upsert_all()` 方法
  - `utils.py:save_data()` 改为 DB-first（调用 `upsert_all`）+ JSON backup
  - `testcases.py:confirm_delete_dialog` 先调用 `delete_by_ids()` 从 DB 删除

### Bug 3: data_editor 直接删行未同步
- **修复**: `testcases.py:712-730` — 检测 `edited_page_df` 比 `page_df` 少的行，从 DB 删除并更新 session state

### Bug 4: JSON 重复数据
- **修复**: `data/test_cases.json` 按 id 去重，移除 2 条重复记录（737 → 735）

## 修改的文件

| 文件 | 变更 |
|------|------|
| `app/services/test_case_service.py` | +`delete_by_ids()`, +`upsert_all()` |
| `app/utils.py` | `save_data()` 增加 DB 写入 |
| `app/ui/testcases.py` | auto-save 排除 Select；delete_dialog 增加 DB 删；data_editor 行删除同步 |
| `data/test_cases.json` | 去重 2 条 |
