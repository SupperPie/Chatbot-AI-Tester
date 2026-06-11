# 增量保存与分页修复

## 一、问题描述

用户报告了四个相关的体验/性能问题：

1. **全量保存问题**：在 `st.data_editor` 中只编辑了 1 条用例，但日志输出 `[save_data] 准备保存 3694 条记录`。当前 `save_data()` 把整张 DataFrame 推到 `service.upsert_all()`，触发 3694 次 DB 查询 + 多次批量 commit，导致用户感受到卡顿。
2. **批量编辑丢失问题**：用户在一页内编辑多条用例时，只有第一条编辑被成功保存到数据库，后续编辑丢失。
3. **分页失效问题**：编辑过表格中的任意单元格后，再点击分页组件（下一页 / 跳页）就失效。
4. **Streamlit 弃用告警**：`use_container_width=True` 应改为 `width='stretch'`，`use_container_width=False` 改为 `width='content'`。

## 二、根因分析

### 2.1 全量保存（性能问题）

文件：`app/utils.py:153` `save_data()`、`app/ui/testcases.py:891-926` 自动保存逻辑、`app/services/test_case_service.py:108` `upsert_all()`。

调用链：
- `testcases.py:909` `save_df = prepare_df_for_persistence(st.session_state.df)`（整张 DF 含 3694 行）
- `testcases.py:910` `saved_df_clean = save_data(save_df)`
- `utils.py:213` `service.upsert_all(to_save)`（逐条 query + update）

无论用户改了几行，都会做全量同步——这就是日志里 3694 的来源。

### 2.2 批量编辑丢失

文件：`app/ui/testcases.py:891-926` 自动保存逻辑。

关键流程：
1. 用户编辑第一条 → fragment 重新执行 → `page_edited == True` → 执行全量 `save_data` → 然后 **整体替换 `st.session_state.df = saved_df_clean`**（line 924）
2. `rebuild_internal_ids` 重建了所有 `__row_key`（虽然数值相同但 DF 对象已更换）。
3. 用户继续编辑第二条 → fragment 再次执行。
4. `display_df`（fragment 入参）仍然是外层上一次传入的旧数据，`page_df` 也是旧切片。
5. `st.data_editor` 由于 key 未变，保留了用户的编辑状态（含第一条的修改 + 第二条的新修改）。
6. 但 sync 回写到 `st.session_state.df` 时，由于 DF 对象已被替换，**有几种可能导致后续编辑丢失**：
   - `save_data` 内部的 ID 再生成/turn_index 处理可能覆盖某些字段值。
   - 全量 upsert 3694 条时，之前保存下来的第一条修改被再次覆盖（因为 display_df 里第一条仍是旧值，sync 把旧值写回 session_state 后再全量保存）。
   - 实际上最可能的情况是：**sync 循环写入了 edited_page_df 的所有行（包括未编辑行），但 edited_page_df 中对应的列值是从 data_editor 内部状态返回的，而 data_editor 内部在第二次 fragment rerun 时可能已被 Streamlit 部分重置**。

核心问题：每次编辑都触发"全量保存 + DF 整体替换"，破坏了后续编辑的数据一致性。解决方案是：**就地更新 + 增量保存，不替换 DF 对象**。

### 2.3 分页失效（Streamlit Fragment 状态问题）

文件：`app/ui/testcases.py:694` `@st.fragment def render_paginated_table(display_df)`、`app/ui/testcases.py:763-777` 分页组件、`app/ui/testcases.py:891-926` 自动保存。

关键流程：
1. 用户编辑单元格 → `st.data_editor` 触发 fragment 重新执行。
2. `page_edited == True`，执行 `save_data` 后把 `st.session_state.df = saved_df_clean`，但**没有调用 `st.rerun(scope="app")`**，只是 fragment 内部继续往下走。
3. 之后用户点击分页 → fragment 再跑一次。但 `display_df` 是 fragment 的入参，由外层 `render_testcases_page()` 在最后一次完整渲染时传入，这时它仍是**保存前的 filtered_df**。
4. 同时 `rebuild_internal_ids` 把 `st.session_state.df['__row_key']` 重置为 `rk_0..rk_N`，与 `display_df` 中保存前的 `__row_key` 不再对齐，select / row mapping 错位，看起来"分页失灵"。
5. 另外 `data_editor` 的 key 中包含 `testcases_current_page` 和 `testcases_page_size`，但是当 fragment 内 `st.rerun()` 只 rerun fragment 时，外层 `display_df` 不更新，slicing 出来的 `page_df` 仍是旧切片。

解决方案：在分页变化时调用 `st.rerun(scope="app")` 让外层重算 `filtered_df`。同时自动保存后不再替换 DF、不重建 __row_key，保持状态稳定。

### 2.4 Streamlit 弃用

新版 Streamlit 把 `use_container_width` 改名：
- `use_container_width=True` → `width='stretch'`
- `use_container_width=False` → `width='content'`

涉及 `st.button`、`st.popover`、`st.data_editor`、`st.selectbox` 等。

## 三、修复方案

核心思路：**自动保存路径不再做"全量推送 + DF 整体替换"**，改为：
- 通过 `__row_key` 精准定位被修改的行；
- 把这些行的最新值就地写入 `st.session_state.df`（保留原 DF 对象引用 / `__row_key`，不调用 `rebuild_internal_ids`、不替换整张 DF）；
- 只把这些行 upsert 到 DB；
- 不在每次单元格编辑后做 `st.rerun(scope="app")`，避免打断用户连续编辑；
- 仅在分页跳转时调用 `st.rerun(scope="app")`，确保外层 `display_df` 与 `st.session_state.df` 重新对齐。

### ⚠️ ID 安全说明（重要）

本次修改严格保证：**不会修改任何 testcase 的 ID**。

- 新引入的 `save_records()` / `upsert_records()` 路径中**完全没有** ID 生成/重分配逻辑（不调用 `generate_tc_id()`，不遍历分配 TCxxxx）。
- `upsert_records()` 把 `id` 和 `turn_index` 仅作为 DB 查询条件，写入字段时显式排除：
  ```python
  if k not in ('id', 'turn_index') and k in allowed_fields:
      setattr(existing, k, v)
  ```
- 原 `save_data()` 中的 ID 自动生成逻辑保留不动，仅在"新增行 / 导入" 等显式产生新数据的旧分支继续使用。
- 自动保存路径（行 ~886-926）将完全绕过 `save_data()`，因此 3694 条现有用例的 ID 不会被触碰。

### 3.1 增量保存接口

**改动 1：`app/services/test_case_service.py`**

新增 `upsert_records(records: List[Dict]) -> int`，语义为"只对给定的若干条记录做 upsert"，小批量直接 commit 一次。

```python
def upsert_records(self, records: List[Dict]) -> int:
    """只对给定的若干条记录做 upsert，不做全量同步。"""
    allowed_fields = {c.name for c in TestCase.__table__.columns}
    for r in records:
        if not r.get('id'):
            continue
        clean = _sanitize_record(r)
        ti = int(clean.get('turn_index') or 1)
        clean['turn_index'] = ti
        existing = self.db.query(TestCase).filter(
            TestCase.id == clean['id'],
            TestCase.turn_index == ti
        ).first()
        if existing:
            for k, v in clean.items():
                if k not in ('id', 'turn_index') and k in allowed_fields:
                    setattr(existing, k, v)
            existing.updated_at = datetime.utcnow()
        else:
            fields = {k: v for k, v in clean.items() if k in allowed_fields}
            fields['turn_index'] = ti
            fields.setdefault('created_at', datetime.utcnow())
            fields.setdefault('updated_at', datetime.utcnow())
            self.db.add(TestCase(**fields))
    self.db.commit()
    return len(records)
```

**改动 2：`app/utils.py` 新增 `save_records()`**

```python
def save_records(records: list[dict]) -> int:
    """只保存指定的若干条记录到 DB（增量保存）。"""
    from app.services.test_case_service import TestCaseService
    if not records:
        return 0
    # 清洗 turn_index
    for r in records:
        try:
            r['turn_index'] = int(r.get('turn_index') or 1)
        except (TypeError, ValueError):
            r['turn_index'] = 1
    print(f"[save_records] 增量保存 {len(records)} 条")
    service = TestCaseService()
    return service.upsert_records(records)
```

### 3.2 修改自动保存逻辑（`app/ui/testcases.py` 行 ~886-926）

替换为以下逻辑：

```python
# 自动保存：仅当内容列被修改时
_content_cols = [c for c in page_df.columns if c not in ('Select', '__row_key')]
page_edited = not edited_page_df[_content_cols].reset_index(drop=True).equals(
    page_df[_content_cols].reset_index(drop=True)
)
if page_edited:
    # 1. 通过 __row_key 找出真正被修改的行
    page_indexed = page_df.set_index('__row_key')
    edited_indexed = edited_page_df.set_index('__row_key')
    common_keys = [k for k in edited_indexed.index if k in page_indexed.index]

    def _row_changed(rk):
        for col in _content_cols:
            if col not in page_indexed.columns or col not in edited_indexed.columns:
                continue
            a = page_indexed.at[rk, col]
            b = edited_indexed.at[rk, col]
            # 处理 list/dict 比较
            if isinstance(a, (list, dict)) or isinstance(b, (list, dict)):
                if a != b:
                    return True
            else:
                # NaN-safe 比较
                if pd.isna(a) and pd.isna(b):
                    continue
                if a != b:
                    return True
        return False

    changed_keys = [rk for rk in common_keys if _row_changed(rk)]

    # 2. 就地把改动写回 st.session_state.df（不替换 DF 对象）
    for rk in changed_keys:
        edited_row = edited_indexed.loc[rk]
        main_idx = st.session_state.df.index[st.session_state.df['__row_key'] == rk]
        for col in _content_cols:
            if col not in st.session_state.df.columns:
                continue
            val = edited_row[col]
            if isinstance(val, (list, dict)):
                for idx in main_idx:
                    st.session_state.df.at[idx, col] = val
            else:
                st.session_state.df.loc[main_idx, col] = val

    # 3. 增量 upsert：只把改动的行写 DB
    if changed_keys:
        try:
            changed_rows_df = st.session_state.df[
                st.session_state.df['__row_key'].isin(changed_keys)
            ].drop(columns=['Select', '__row_key'], errors='ignore')
            save_records(changed_rows_df.to_dict(orient='records'))
            st.session_state.df_content_sig = get_content_signature(st.session_state.df)
            st.toast(f"✅ 已保存 {len(changed_keys)} 条修改", icon="💾")
        except Exception as e:
            logger.error(f"增量保存失败: {e}", exc_info=True)
            st.error(f"保存失败：{e}")
    # 注意：此处不调用 st.rerun()，让用户可以连续编辑多行；
    # 也不调用 rebuild_internal_ids，保持 __row_key 稳定。
```

要点：
- 不再调用 `save_data` 处理整张 DF；
- 不再调用 `rebuild_internal_ids`；
- 不再替换 `st.session_state.df`；
- 只对 `changed_keys` 做 DB upsert；
- 不调用 `st.rerun()`，允许连续编辑（这正是"批量编辑"的预期）。

### 3.3 修复分页失效

文件：`app/ui/testcases.py` 分页跳转处（行 ~775-777）：

```python
if current_page_idx != st.session_state.testcases_current_page:
    st.session_state.testcases_current_page = current_page_idx
    st.rerun(scope="app")  # 改为 app scope，确保外层 display_df 重新计算
```

由于自动保存路径不再替换 `st.session_state.df`，分页时 `display_df` 与 `st.session_state.df` 引用一致（外层 rerun 后会重新 `filter_test_cases`），分页将恢复正常。

### 3.4 Streamlit 弃用（可选项）

仅在确认 Streamlit 版本支持 `width=` 参数后做替换。本期可作为低优先级项，先解决前三个问题。

## 四、影响文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `app/services/test_case_service.py` | 新增方法 | 新增 `upsert_records()` |
| `app/utils.py` | 新增函数 | 新增 `save_records()` |
| `app/ui/testcases.py` | 改写自动保存逻辑 | 行 ~886-926：增量 + 就地更新，不替换 DF |
| `app/ui/testcases.py` | 修改分页跳转 | 行 ~777：`st.rerun()` → `st.rerun(scope="app")` |
| `app/ui/testcases.py` | 弃用替换（可选） | `use_container_width` → `width=...` |

## 五、边界与异常

- **连续编辑多行**：每次编辑触发 fragment 重跑，sync 仅写 changed 行到 session state 与 DB；DF 对象不被替换，`__row_key` 稳定，下一次编辑能正确对齐。
- **同一行编辑多列**：算"一行一次 upsert"，所有列一起写。
- **多轮对话（同 id 多 turn_index）**：`upsert_records` 按 `(id, turn_index)` 精准定位，不污染其他 turn。
- **新增/删除行（行 829-884）**：保持原 `save_data` + `rebuild_internal_ids` 逻辑（这些动作必然伴随 `st.rerun()`，不会与增量保存冲突）。
- **保存失败**：`st.error` 提示，session state 已就地更新（用户不会丢失编辑状态），下次编辑会再次触发增量保存。
- **`__row_key` 未对齐**：若极少数情况下 `display_df` 中的 key 不存在于 `st.session_state.df`，跳过该行（`common_keys` 已做交集过滤）。
- **ID 安全保证**：增量保存路径（`save_records` → `upsert_records`）**不包含任何 ID 生成/重分配逻辑**。`upsert_records` 中 `id` 和 `turn_index` 被显式排除在更新字段之外（仅用作 DB 查找条件）。现有 3694 条用例的 ID 不会被触碰。原 `save_data` 中的 ID 自动生成逻辑（`generate_tc_id()`）仅在新增行分支中保留使用。

## 六、预期效果

1. 编辑 1 条用例 → 日志显示 `[save_records] 增量保存 1 条`，DB 仅 1 次 query + 1 次 commit。
2. 在同一页连续编辑 3 条用例 → 全部写入 DB，不再丢失后续编辑。
3. 编辑后立即点击分页 → 正常翻页 / 跳页。
4. （可选）不再出现 `use_container_width` 弃用警告。
