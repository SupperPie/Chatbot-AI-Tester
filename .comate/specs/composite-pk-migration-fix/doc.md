# 多轮对话复合主键 + 迁移脚本修复

## 背景
`test_cases` 表当前 PK 只有 `id`，多轮对话通过 `_T{n}` 后缀区分行（如 `TC0621`, `TC0621_T2`），再由 `normalize_case_id()` 在应用层去掉后缀。这是一个 workaround，现在要改正：多轮对话在 DB 中共用同一个 `id`，用 `(id, turn_index)` 复合主键区分。

## 修改范围

### 1. DB Schema 变更
- `test_cases` 主键：`id` → `(id, turn_index)`
- `turn_index`：`FLOAT NULL` → `INTEGER NOT NULL DEFAULT 1`
- `test_case_tags` 表：FK 引用 `test_cases(id)` 需处理（该表未被应用层使用，可直接 drop FK 或 drop 表）

**SQL 迁移步骤**：
```sql
-- 1. 清空已有的错误迁移数据
TRUNCATE test_cases CASCADE;

-- 2. 修改 turn_index 列
ALTER TABLE test_cases ALTER COLUMN turn_index SET NOT NULL;
ALTER TABLE test_cases ALTER COLUMN turn_index SET DEFAULT 1;
ALTER TABLE test_cases ALTER COLUMN turn_index TYPE INTEGER USING COALESCE(turn_index::INTEGER, 1);

-- 3. 更改主键
ALTER TABLE test_cases DROP CONSTRAINT test_cases_pkey;
ALTER TABLE test_cases ADD PRIMARY KEY (id, turn_index);

-- 4. 处理 test_case_tags FK（unused table）
ALTER TABLE test_case_tags DROP CONSTRAINT IF EXISTS test_case_tags_test_case_id_fkey;
```

### 2. Model (`app/models/test_case.py`)
```python
# 之前
id = Column(String(50), primary_key=True)
turn_index = Column(Float)

# 之后
id = Column(String(50), primary_key=True)
turn_index = Column(Integer, primary_key=True, default=1)
```

### 3. Service (`app/services/test_case_service.py`)

**`upsert_all()`**：查找由 `id` 改为 `(id, turn_index)`
```python
# 之前
existing = self.db.query(TestCase).filter(TestCase.id == clean['id']).first()

# 之后
ti = clean.get('turn_index', 1) or 1
existing = self.db.query(TestCase).filter(
    TestCase.id == clean['id'],
    TestCase.turn_index == int(ti)
).first()
```

**`incoming_ids` 集合和删除逻辑**：改为 `(id, turn_index)` 元组
```python
# 之前
incoming_ids = {r['id'] for r in records if r.get('id')}
self.db.query(TestCase).filter(~TestCase.id.in_(incoming_ids)).delete(...)

# 之后
incoming_keys = {(r['id'], int(r.get('turn_index') or 1)) for r in records if r.get('id')}
incoming_ids = {k[0] for k in incoming_keys}
# 删除 id 不在 incoming 中的记录
self.db.query(TestCase).filter(~TestCase.id.in_(incoming_ids)).delete(...)
# 对于 id 在 incoming 中但 (id, turn_index) 不在的记录，也需要删除
# 但逐条匹配复合键效率较低，改用全量重建或精细过滤
```

**`delete_by_ids()`**：按 `id` 删除所有 turn，逻辑不变（删除一个测试用例 = 删除它所有轮次）。

**`update_category()`**：按 `id` 更新所有 turn，逻辑不变。

### 4. Utils (`app/utils.py`)

**`load_data()`**：
- 移除 `__raw_id` 和 `normalize_case_id` 相关逻辑
- `id` 直接就是逻辑 ID，不需要再做转换
- `turn_index` 从 DB 加载已经是 Integer

**`save_data()`**：
- 移除 `__raw_id` 的 drop 逻辑
- `upsert_all` 传入的记录直接包含 `(id, turn_index)`

### 5. UI (`app/ui/testcases.py`)

**行删除** (line 719-724)：
- 当前用 `__raw_id`（含 `_T` 后缀）调用 `delete_by_ids`
- 改为用 `id` 调用 `delete_by_ids`（删除整个测试用例的所有轮次）
- 或者如果需要删除单个轮次，传 `(id, turn_index)` 对

**移动到目录** (line 262)：
- `TestCase.id.in_(ids_to_move)` — 逻辑不变，移动整个用例的所有轮次

**导入检查** (line 474)：
- `TestCase.id == case_id` → 加 `turn_index` 条件

**`__raw_id` 引用清理**：
- 所有 `__raw_id` 引用改为直接使用 `id`（或 `id` + `turn_index` 组合）

### 6. 迁移脚本 (`scripts/migrate_json_to_db.py`)

**核心修复 — 预处理规则**：

按 ID 分组后：

| 情况 | 描述 | 处理方式 |
|------|------|----------|
| 情况 1 | 全是 single，不同 input | 第一条保持原 ID，其余生成新 ID（`TC{NNNN}`） |
| 情况 2 | 混合 single + multi_turn | single turn=1 改为 multi_turn turn=1（配对 turn=2）；多余 single 生成新 ID |
| 情况 3 | 纯 multi_turn（或含已修正的 turn=1） | 全部保持原 base ID，用 turn_index 区分（复合 PK 天然支持，不再加 `_T{n}` 后缀） |

**关键变化**：不再生成 `_T{n}` 后缀，多轮对话的所有行直接用原始 `case_id` + 不同 `turn_index` 写入。

## 边界条件
- `turn_index` 为 `None`/`NaN`/`float` → 统一转为 `int`，single 默认 1
- 同 ID 多条 multi_turn turn=1 → 保留第一条，多余的生成新 ID
- `test_case_tags` 表未使用，drop FK 约束即可
- `test_results.case_id` 无 FK 约束，不受影响
- 已有的 `_T{n}` 后缀记录需清空后重新迁移

## 预期结果
- 1774 条 JSON 记录正确迁移到 DB
- 多轮对话共用同一 `id`，通过 `turn_index` 区分
- 同 ID 冲突的 single 记录获得新的唯一 ID
- 应用层不再需要 `normalize_case_id()` 和 `_T{n}` 后缀逻辑
