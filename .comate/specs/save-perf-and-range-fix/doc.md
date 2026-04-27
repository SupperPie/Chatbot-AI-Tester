# Save Performance & ID Range Filter Fix

## 问题 1：保存测试用例极慢

### 场景
用户点击保存后，`save_data()` 调用 `TestCaseService.upsert_all()`，对 ~735 条记录逐条执行 `SELECT` + `UPDATE/INSERT`，产生 1470+ 次数据库往返，导致保存耗时极长。

### 根因
`app/services/test_case_service.py:70-99` 的 `upsert_all()` 对每条记录:
1. `self.db.query(TestCase).filter(TestCase.id == clean['id']).first()` — 单条 SELECT
2. 存在则逐字段 `setattr` UPDATE，否则 `self.db.add()` INSERT

### 修复方案
使用 PostgreSQL 原生 `INSERT ... ON CONFLICT (id) DO UPDATE` 批量 upsert，一次 SQL 处理所有记录。通过 SQLAlchemy `insert().on_conflict_do_update()` 方言实现。

### 涉及文件
| 文件 | 修改类型 | 影响函数 |
|------|----------|----------|
| `app/services/test_case_service.py` | 修改 | `upsert_all()` |

### 实现细节
```python
from sqlalchemy.dialects.postgresql import insert as pg_insert

def upsert_all(self, records: List[Dict]) -> int:
    incoming_ids = {r['id'] for r in records if r.get('id')}
    
    # 删除不在 records 中的行（保持原逻辑）
    if incoming_ids:
        self.db.query(TestCase).filter(~TestCase.id.in_(incoming_ids)).delete(synchronize_session=False)
    else:
        self.db.query(TestCase).delete(synchronize_session=False)
    
    # 批量 upsert
    allowed_fields = {c.name for c in TestCase.__table__.columns}
    now = datetime.utcnow()
    
    batch = []
    for r in records:
        if not r.get('id'):
            continue
        clean = _sanitize_record(r)
        fields = {k: v for k, v in clean.items() if k in allowed_fields}
        fields.setdefault('created_at', now)
        fields.setdefault('updated_at', now)
        batch.append(fields)
    
    if batch:
        # 分批处理，每批 500 条
        BATCH_SIZE = 500
        update_cols = {c.name: getattr(pg_insert(TestCase).excluded, c.name)
                       for c in TestCase.__table__.columns if c.name != 'id'}
        update_cols['updated_at'] = now
        
        for i in range(0, len(batch), BATCH_SIZE):
            chunk = batch[i:i+BATCH_SIZE]
            stmt = pg_insert(TestCase).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=['id'],
                set_=update_cols
            )
            self.db.execute(stmt)
    
    self.db.commit()
    return len(batch)
```

性能预期：从 1470+ 次 DB 往返降至 ~4 次（1 DELETE + 2 INSERT batches + 1 COMMIT）。

> **备注**：`scripts/create_tables.sql` 中定义了 `draft_batches` / `test_case_drafts` 草稿表，但尚无 Python 代码集成。当前 ~735 条数据规模下，批量 `INSERT ... ON CONFLICT` 已足够高效，无需引入临时表中转。

---

## 问题 2：ID Range Filter 返回空结果

### 场景
用户在筛选条件中输入 `From ID: TC0732`, `To ID: TC0761`，页面上能看到被筛选出的用例，但点击 "Run Range" 按钮后提示 "No cases found in range TC0732 to TC0761"。

### 根因
`app/ui/testcases.py:832` 创建 mask 时索引不对齐：

```python
mask = pd.Series([True] * len(edited_df))  # 索引 [0,1,2,...,n-1]
mask = mask & (edited_df['id'] >= start_id)  # 索引来自原始 df [731,732,...,760]
```

Pandas `&` 按索引对齐，不匹配的位置产生 `NaN`（被当作 `False`），导致结果为空。

### 修复方案
使用 `edited_df.index` 作为 mask 的索引：

```python
mask = pd.Series([True] * len(edited_df), index=edited_df.index)
```

### 涉及文件
| 文件 | 修改类型 | 影响函数 |
|------|----------|----------|
| `app/ui/testcases.py` | 修改 | `run_range_clicked` 处理块 (line 832) |

### 边界条件
- 已经被 `filter_test_cases()` 筛选过的 `edited_df` 索引不连续 — 修复后正确对齐
- 空 DataFrame 时 `range_rows.empty` 仍正常工作
