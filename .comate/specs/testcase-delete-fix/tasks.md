# Testcase Delete Fix — 删除功能修复 + DB 读写统一

- [ ] Task 1: TestCaseService 新增 delete_by_ids 和 upsert_all 方法
    - 1.1: 新增 `delete_by_ids(ids)` 批量删除方法
    - 1.2: 新增 `upsert_all(records)` 全量同步方法（删除多余、更新已有、新增缺少）

- [x] Task 2: save_data() 改为 DB-first + JSON backup
    - 2.1: 在 ID 生成逻辑之后、JSON 写入之前，调用 `TestCaseService.upsert_all()` 写 DB
    - 2.2: 保留 JSON 写入作为备份
    - 2.3: DB 写入失败时 catch 异常，降级为仅 JSON

- [x] Task 3: 修复 auto-save 比较逻辑（排除 Select 列）
    - 3.1: `testcases.py:705` 的 `page_edited` 比较排除 Select 列
    - 3.2: auto-save 后保留原有 Select 状态而非重置为 False

- [x] Task 4: confirm_delete_dialog 增加 DB 删除
    - 4.1: 在 `confirm_delete_dialog` 的 "Yes, Delete" 分支中先调用 `TestCaseService.delete_by_ids()`
    - 4.2: 再执行现有的 session state 清理和 save_data

- [x] Task 5: data_editor 行删除同步到 DB
    - 5.1: 在 auto-save 逻辑中检测 `edited_page_df` 比 `page_df` 少的行
    - 5.2: 从 DB 删除这些行，从 session state 移除

- [x] Task 6: 清理 JSON 重复数据
    - 6.1: 按 `id` 字段去重 `data/test_cases.json`，保留首次出现
