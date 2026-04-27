# Release 2.2 发版手册

## 1. 版本概述

Release 2.2 基于 Release 2.1（数据库迁移已完成）进行功能增强与缺陷修复。

### 1.1 本版本变更清单

| 变更项 | 类型 | 涉及文件 |
|--------|------|----------|
| 数据持久化切换为 DB-only | 架构变更 | `app/utils.py` |
| 测试用例删除功能修复（二次确认 + DB 同步） | Bug 修复 | `app/ui/testcases.py`, `app/services/test_case_service.py` |
| 自动保存排除 Select 列（避免勾选触发保存） | Bug 修复 | `app/ui/testcases.py` |
| 表格行内新增功能恢复 | Bug 修复 | `app/ui/testcases.py` |
| Move 操作后清除选中状态 | Bug 修复 | `app/ui/testcases.py` |
| data_editor 行删除同步 DB | 功能增强 | `app/ui/testcases.py` |
| DB 写入类型清洗（_sanitize_record） | 功能增强 | `app/services/test_case_service.py` |
| 批量 upsert_all / delete_by_ids | 功能增强 | `app/services/test_case_service.py` |
| API Config DB 持久化 + 参数覆盖 | 功能增强 | `app/services/test_case_service.py`, `.comate/specs/api-config-override/` |
| 按钮渐变样式（CSS） | UI 优化 | `app/ui/styles.py` |
| Popover 锚点样式（Import/Gear） | UI 优化 | `app/ui/testcases.py`, `app/ui/components/category_widget.py` |
| 页签图标更换为大白 | UI 优化 | `streamlit_app.py`, `app/ui/icon.jpeg` |
| JSON 测试数据去重（737→735） | 数据清理 | `data/test_cases.json` |

### 1.2 重要架构变更

**`save_data()` 现在仅写 DB，不再写 JSON 文件。**

- `app/utils.py` 的 `save_data()` 直接调用 `TestCaseService.upsert_all()` 写入 PostgreSQL
- `data/test_cases.json` 仅作为历史迁移源文件保留，运行时不再被修改
- `load_data()` 优先从 DB 读取，仅在 DB 无数据时回退 JSON

---

## 2. 前置条件

本版本假定：
- Release 2.1 的数据库迁移已完成（`test_cases`、`categories`、`api_configs` 表已存在且有数据）
- 服务器 `.env` 中 `DATABASE_URL` 和 `DATABASE_SCHEMA` 已正确配置
- 无需重新执行数据迁移脚本

### 验证前置
```bash
python scripts/test_db_connection.py
```

---

## 3. 发版前备份（必做）

```bash
pg_dump "$DATABASE_URL" > backup_before_release_2_2.sql
```

---

## 4. 代码发布

```bash
# 切换或创建分支
git checkout -b release/2.2 || git checkout release/2.2

# 提交所有变更
git add -A
git commit -m "release/2.2: DB-only persistence, delete fix, table ops, UI enhancements"

# 推送
git push -u origin release/2.2
```

---

## 5. 部署后验证

### 5.1 基础功能
- [ ] 页面正常加载，页签图标显示为大白
- [ ] Test Cases 页面表格正常展示，数据从 DB 读取
- [ ] 编辑表格内容后自动保存（toast 提示）
- [ ] 勾选 checkbox 不触发自动保存

### 5.2 删除功能
- [ ] 勾选用例 → 点击 Delete → 弹出二次确认弹窗
- [ ] 确认删除后，DB 同步删除，页面数据刷新
- [ ] data_editor 中直接删除行，DB 同步删除

### 5.3 新增功能
- [ ] 表格底部点击 "+" 新增行 → 填写内容 → 自动保存并分配 TC ID

### 5.4 Move 功能
- [ ] 选中多个用例 → 执行 Move → 移动成功后选中状态自动清除（计数归零）

### 5.5 多轮对话
- [ ] 同 ID + type=multi_turn 的用例按 turn_index 排序显示
- [ ] 执行时按对话分组，共享 session

### 5.6 UI 样式
- [ ] Import 按钮绿色渐变
- [ ] Delete 按钮红色渐变
- [ ] Cancel All 按钮紫色渐变
- [ ] 齿轮按钮透明无边框

---

## 6. 回滚方案

```bash
# 回滚代码
git checkout release/2.1

# 如需回滚数据库
psql "$DATABASE_URL" < backup_before_release_2_2.sql
```

---

## 7. 已知限制

- `upsert_all()` 当前为逐条 SELECT + UPDATE/INSERT（N+1 查询），大数据量时保存较慢，计划在后续版本优化为批量 `INSERT ... ON CONFLICT`
- ID Range Filter 在 "Run Range" 按钮触发时存在索引对齐问题，计划后续修复
