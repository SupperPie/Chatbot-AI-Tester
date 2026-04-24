# Release 2.1 发版手册（服务器接入同库场景）

## 1. 场景说明（当前适用）

当前本地与服务器连接的是同一个 PostgreSQL 数据库，且数据库与表结构已完成初始化。

本次发版目标是：
- 服务器应用正确连接数据库
- 完成服务器数据到数据库的迁移与覆盖
- 冲突规则满足：按 `input` 判断，若相同则整条记录以服务器数据覆盖数据库

> 说明：数据库初始化与建表步骤在本文保留为“可选操作”，仅用于新环境首次部署。

---

## 2. 服务器连接数据库配置（必做）

在服务器部署目录创建/更新 `.env`：

```env
DATABASE_URL=postgresql://DB_USER:DB_PASSWORD@DB_HOST:DB_PORT/DB_NAME
DATABASE_SCHEMA=ai_chatbot_tester
```

示例：
```env
DATABASE_URL=postgresql://tester_user:StrongPass@192.168.26.241:5432/dp_testmate
DATABASE_SCHEMA=ai_chatbot_tester
```

### 配置检查
```bash
python scripts/test_db_connection.py
```

预期：输出成功连接信息；若失败，先修复网络/权限/账号后再继续。

---

## 3. （可选）数据库初始化与建表（仅新环境）

> 当前你的环境已完成，可跳过。

```bash
psql "$DATABASE_URL" -c "CREATE SCHEMA IF NOT EXISTS ai_chatbot_tester;"
PGOPTIONS="--search_path=ai_chatbot_tester,public" psql "$DATABASE_URL" -f scripts/create_tables.sql
python scripts/migrate_categories.py
```

---

## 4. 发版前备份（必做）

### 4.1 备份数据库
```bash
pg_dump "$DATABASE_URL" > backup_before_release_2_1.sql
```

### 4.2 备份服务器数据文件
```bash
tar -czf data_backup_before_release_2_1.tar.gz data/
```

---

## 5. 数据迁移执行（必做）

### 5.1 Dry Run
```bash
python scripts/migrate_json_to_db.py --dry-run --file data/test_cases.json
python scripts/migrate_all_data.py --dry-run --only all
```

### 5.2 正式迁移
```bash
python scripts/migrate_json_to_db.py --file data/test_cases.json
python scripts/migrate_all_data.py --only all
python scripts/migrate_categories.py
```

---

## 6. 冲突策略（必须遵循）

冲突判断标准：`input`

处理规则：
- 若数据库中存在相同 `input`，则整条业务数据以服务器数据覆盖数据库
- 若不存在相同 `input`，插入新记录

伪代码：

```python
existing = db.query(TestCase).filter(TestCase.input == src_input).first()
if existing:
    # 服务器覆盖数据库
    existing.expected_output = src_expected_output
    existing.tags = src_tags
    existing.type = src_type
    existing.turn_index = src_turn_index
    existing.validation = src_validation
    existing.overall_criteria = src_overall_criteria
    existing.category_id = src_category_id
else:
    db.add(TestCase(...))
```

---

## 7. 迁移后校验（必做）

### 7.1 数量校验
- 源数据总数
- 源数据按 `input` 去重数
- 迁移后数据库总数
- 迁移后数据库按 `input` 去重数

### 7.2 抽样一致性
随机抽样记录，核对字段：
- `input`
- `expected_output`
- `tags`
- `validation`
- `overall_criteria`

### 7.3 业务链路验证
在页面执行一批包含多轮会话的数据，确认同一业务ID在执行链路中按预期聚合。

---

## 8. 回滚方案

迁移异常时：

```bash
psql "$DATABASE_URL" < backup_before_release_2_1.sql
rm -rf data
tar -xzf data_backup_before_release_2_1.tar.gz
```

---

## 9. 代码发布（release/2.1）

```bash
# 创建或切换分支
git checkout -b release/2.1 || git checkout release/2.1

# 提交
git add -A
git commit -m "release/2.1: deployment guide and migration policy update"

# 推送
git push -u origin release/2.1
```

---

## 10. 发布验收清单

- [ ] 服务器 `.env` 数据库连接已更新并验证通过
- [ ] 已完成发版前数据库与 data 目录备份
- [ ] 已执行 dry-run 与正式迁移
- [ ] 已验证冲突策略：`input` 相同则服务器覆盖数据库
- [ ] 已完成抽样一致性与页面链路验证
- [ ] 代码已推送至 `release/2.1`
