# 多轮对话复合主键 + 迁移脚本修复 — 完成总结

## 完成的变更

### 1. DB Schema 变更
- `test_cases` 主键从 `id` 改为 `(id, turn_index)` 复合主键
- `turn_index` 从 `FLOAT NULL` 改为 `INTEGER NOT NULL DEFAULT 1`
- `test_case_tags` 的 FK 约束已删除（该表未被应用层使用）

### 2. Model 更新 (`app/models/test_case.py`)
- `turn_index` 改为 `Integer, primary_key=True, default=1`
- `Float` 导入替换为 `Integer`

### 3. Service 更新 (`app/services/test_case_service.py`)
- `upsert_all()` 使用 `(id, turn_index)` 复合键查找和匹配
- 删除逻辑适配复合键

### 4. Utils 更新 (`app/utils.py`)
- 移除 `normalize_case_id()` 函数和 `import re`
- `load_data()` 移除 `__raw_id` 创建和 `normalize_case_id` 调用
- `save_data()` 移除 `__raw_id` 相关逻辑，确保 `turn_index` 为 int

### 5. UI 更新 (`app/ui/testcases.py`, `app/ui/tester.py`)
- 清除所有 `__raw_id` 引用（19 处）
- 清除 `normalize_case_id` 导入和使用
- 删除/导入检查改用 `(id, turn_index)` 复合键

### 6. 迁移脚本重写 (`scripts/migrate_json_to_db.py`)
- 两阶段处理：预处理（按 ID 分组标记） → 写入
- 规则 1：同 ID 全 single 不同 input → 第一条保留原 ID，其余生成新 TC 编号
- 规则 2：混合 single/multi_turn → 修正 turn=1 的 single 为 multi_turn，多余 single 新 ID
- 规则 3：多轮对话保持原 ID + turn_index，不加 `_T{n}` 后缀
- 额外处理：同 ID + 同 turn_index 的 multi_turn 重复 → 拆为 single + 新 ID
- 批次提交失败时逐条重试

### 7. DDL 同步 (`scripts/create_tables.sql`)
- `test_cases` 表定义更新为复合主键
- `test_case_tags` FK 移除

## 迁移结果
- 源数据：1774 条记录
- 写入成功：1773 条（1 条无效跳过）
- 保持原 ID：1752 条
- 重命名（新 TC 编号）：19 条
- 修正 type（single → multi_turn）：2 条
- `_T{n}` 后缀记录：0
- 多轮对话用例数：80 个（共用同一 ID）
- 错误：0

## 修改的文件
| 文件 | 变更类型 |
|------|----------|
| `app/models/test_case.py` | 复合主键定义 |
| `app/services/test_case_service.py` | upsert_all 适配复合键 |
| `app/utils.py` | 移除 normalize_case_id / __raw_id |
| `app/ui/testcases.py` | 清理 __raw_id 引用 |
| `app/ui/tester.py` | 适配复合键查找 |
| `scripts/migrate_json_to_db.py` | 完全重写 |
| `scripts/create_tables.sql` | DDL 同步 |
