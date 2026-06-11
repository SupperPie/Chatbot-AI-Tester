# 增量保存、批量编辑修复与分页修复

- [x] Task 1: 新增 `upsert_records` 方法到 TestCaseService
    - 1.1: 在 `app/services/test_case_service.py` 末尾（`__del__` 前）新增 `upsert_records(self, records: List[Dict]) -> int` 方法
    - 1.2: 逻辑与 `upsert_all` 类似，但不分批 commit（小批量直接一次 commit）
    - 1.3: 用 `(id, turn_index)` 定位 DB 记录后，更新用户修改的字段值；如果用户修改了 id 字段本身，也正常写入（尊重用户操作）；但方法内部不包含任何自动生成/重分配 ID 的逻辑

- [x] Task 2: 新增 `save_records` 函数到 utils.py
    - 2.1: 在 `app/utils.py` 的 `save_data` 函数后面新增 `save_records(records: list[dict]) -> int`
    - 2.2: 清洗 `turn_index`（处理 NaN/空字符串/非数字边界）
    - 2.3: 调用 `TestCaseService().upsert_records(records)`
    - 2.4: 在 `app/ui/testcases.py` 顶部 import 中加入 `save_records`

- [x] Task 3: 改写自动保存逻辑为增量保存
    - 3.1: 替换 `app/ui/testcases.py` 行 886-926 的自动保存代码块
    - 3.2: 通过 `__row_key` 逐行对比 `page_df` 与 `edited_page_df`，找出真正被修改的行（`changed_keys`）
    - 3.3: 仅对 `changed_keys` 对应的行做就地写回 `st.session_state.df`（不替换 DF 对象）
    - 3.4: 调用 `save_records()` 增量写入 DB（不调用 `save_data`）
    - 3.5: 不调用 `rebuild_internal_ids`，保持 `__row_key` 稳定
    - 3.6: 不调用 `st.rerun()`，允许用户连续编辑多行
    - 3.7: 更新 `df_content_sig`，添加 toast 提示

- [x] Task 4: 修复分页跳转失效
    - 4.1: 将 `app/ui/testcases.py` 行 ~777 的 `st.rerun()` 改为 `st.rerun(scope="app")`
    - 4.2: 确保分页变化后外层 `display_df` 被重新计算

- [x] Task 5: 替换 `use_container_width` 弃用参数
    - 5.1: 在 `app/ui/testcases.py` 中将 `use_container_width=True` 替换为对应的新参数
    - 5.2: 将 `use_container_width=False`（data_editor）替换为对应的新参数
