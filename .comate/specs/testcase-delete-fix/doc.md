# Testcase Delete Fix — 删除功能 Bug 修复 + 全面 DB 读写

## 背景
用户在 Testcases 页面选择 2 条测试用例后点击 Delete 按钮，出现两个问题：
1. 二次确认对话框没有弹出
2. 数据中出现重复条目（`GEN_001_T11` 和 `GEN_001_T12` 各出现 2 次）

用户已将数据从 JSON 迁移到 DB，要求后续所有读写都走 DB。

## Bug 分析

### Bug 1: 确认对话框不弹出

**根因**：自动保存逻辑 (`testcases.py:705`) 用 `edited_page_df.equals(page_df)` 比较了所有列（包括 Select）。

**详细流程**：
1. 用户勾选 checkbox → 点击 Delete → 全页 rerun
2. Fragment `render_paginated_table()` 先执行：
   - `st.data_editor` 恢复 checkbox → 同步 Select 到 `st.session_state.df`
   - `page_edited = not edited_page_df.equals(page_df)` → **True**（Select 列变了）
   - auto-save 触发 → `save_data()` → 返回的 df 不含 Select
   - Select 列用 `False` 重新填充 → **所有选中状态丢失**
3. Delete handler：`selected_rows = edited_df[edited_df["Select"] == True]` → 空集 → 对话框不弹

**修复**：`page_edited` 比较排除 Select 列。

**修改**：`app/ui/testcases.py:705`
```python
# Before
page_edited = not edited_page_df.equals(page_df)

# After
_content_cols = [c for c in page_df.columns if c != 'Select']
page_edited = not edited_page_df[_content_cols].reset_index(drop=True).equals(
    page_df[_content_cols].reset_index(drop=True)
)
```

### Bug 2: save_data / load_data 读写不一致

**根因**：`load_data()` 从 DB 读，`save_data()` 只写 JSON。删除操作不会持久化到 DB。

**修复**：将 `save_data()` 改为写 DB（同时保留 JSON 备份），删除操作增加 DB 删除。

#### 2.1 `TestCaseService` 新增方法

`app/services/test_case_service.py` 增加：

```python
def delete_by_ids(self, ids: List[str]) -> int:
    """按 ID 列表批量删除测试用例"""
    count = self.db.query(TestCase).filter(TestCase.id.in_(ids)).delete(synchronize_session=False)
    self.db.commit()
    return count

def upsert_all(self, records: List[dict]) -> int:
    """全量同步：以传入 records 为准，DB 中多余的删除，缺少的新增，已有的更新"""
    from sqlalchemy.dialects.postgresql import insert
    
    # 删除 DB 中不在 records 里的行
    incoming_ids = {r['id'] for r in records if r.get('id')}
    self.db.query(TestCase).filter(~TestCase.id.in_(incoming_ids)).delete(synchronize_session=False)
    
    # Upsert 所有记录
    for r in records:
        existing = self.db.query(TestCase).filter(TestCase.id == r['id']).first()
        if existing:
            for k, v in r.items():
                if k != 'id' and hasattr(existing, k):
                    setattr(existing, k, v)
        else:
            self.db.add(TestCase(**{k: v for k, v in r.items() if hasattr(TestCase, k)}))
    
    self.db.commit()
    return len(records)
```

#### 2.2 `save_data()` 改写为 DB-first

`app/utils.py:save_data` 改为先写 DB，再写 JSON 作为备份：

```python
def save_data(df: pd.DataFrame):
    to_save_df = df.drop(columns=["Select", "__row_key", "__raw_id"], errors='ignore').copy()
    
    # ... existing ID generation logic ...
    
    # 1. 写 DB (primary)
    try:
        from app.services.test_case_service import TestCaseService
        service = TestCaseService()
        records = to_save_df.to_dict(orient="records")
        service.upsert_all(records)
    except Exception as e:
        print(f"[save_data] DB write failed: {e}")
    
    # 2. 写 JSON (backup)
    to_save = to_save_df.to_dict(orient="records")
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=4, ensure_ascii=False)
    
    return to_save_df
```

#### 2.3 `confirm_delete_dialog` 增加 DB 删除

`app/ui/testcases.py` 的 `confirm_delete_dialog` 中，在删除前先从 DB 删：

```python
# 从 DB 删除
try:
    from app.services.test_case_service import TestCaseService
    service = TestCaseService()
    service.delete_by_ids(ids_to_delete)
except Exception as e:
    logger.warning(f"DB delete failed: {e}")

# 从 session state 删除并保存
current_df = st.session_state.df
key_col = '__raw_id' if '__raw_id' in current_df.columns else 'id'
new_df = current_df[~current_df[key_col].isin(ids_to_delete)]
final_df = save_data(prepare_df_for_persistence(new_df))
```

### Bug 3: data_editor 内删除行未同步

**现状**：`st.data_editor` 设 `num_rows="dynamic"` 允许直接在表格删行，但 auto-save 只更新现有行，不处理删除。

**修复**：auto-save 检测删除的行并同步到 session state 和 DB。

```python
# 检测被删除的行
if len(edited_page_df) < len(page_df):
    edited_keys = set(edited_page_df['__row_key'].tolist())
    original_keys = set(page_df['__row_key'].tolist())
    deleted_keys = original_keys - edited_keys
    if deleted_keys:
        # 从 DB 删除
        deleted_raw_ids = st.session_state.df[
            st.session_state.df['__row_key'].isin(deleted_keys)
        ]['__raw_id'].tolist()
        try:
            from app.services.test_case_service import TestCaseService
            TestCaseService().delete_by_ids(deleted_raw_ids)
        except Exception as e:
            logger.warning(f"DB delete failed: {e}")
        # 从 session state 移除
        st.session_state.df = st.session_state.df[
            ~st.session_state.df['__row_key'].isin(deleted_keys)
        ]
```

### Bug 4: DB 重复数据清理

`GEN_001_T11` 和 `GEN_001_T12` 在 DB 中不应重复（主键是 `id`），但 JSON 中有重复。因为现在 DB 是 primary source，只需清理 JSON 备份即可。DB 通过主键约束天然去重。

## 受影响文件

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `app/ui/testcases.py` | 修改 | Bug1: auto-save 排除 Select；Bug2: delete_dialog 增加 DB 删；Bug3: data_editor 行删除同步 |
| `app/services/test_case_service.py` | 修改 | 新增 `delete_by_ids`、`upsert_all` 方法 |
| `app/utils.py` | 修改 | `save_data()` 改为 DB-first + JSON backup |
| `data/test_cases.json` | 修改 | 清理重复数据 |

## 边界条件
- 多轮对话的 `__raw_id`（如 `GEN_001_T11`）就是 DB 主键 `id`，每条 turn 唯一
- DB 主键约束防止重复插入，`upsert_all` 用 update-or-insert 逻辑
- DB 写失败时降级为 JSON-only，不影响用户操作
- `load_data()` 已经 DB-first，无需修改
