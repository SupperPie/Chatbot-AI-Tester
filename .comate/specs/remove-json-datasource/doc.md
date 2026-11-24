# 移除 JSON 数据源 · 统一 DB 单一数据源

## 目标

彻底移除以下两类 JSON 作为数据源的读写路径，UI/API/后台脚本全部单向依赖数据库。杜绝数据不一致：

1. 测试用例：`data/test_cases.json`
2. API 配置：`data/api_config.json`

（分类 categories 已经是纯 DB，不再重复迁移；`data/blind_reviews.json`、`data/EB_Golden/*.csv` 本次不改动。）

## 现状梳理

### 测试用例（test_cases.json）

- `app/utils.py:load_data()`（26-85）：DB 优先，DB 报错 or 空 → 静默回退读 JSON。
- `app/routers/cases.py`：整个 FastAPI 路由 `/api/cases` 直接读写 JSON。
- `app/routers/run.py:5, 17`：从 `cases.load_cases` 拿 JSON。
- `save_data()` 已是纯 DB，无需改。

### API 配置（api_config.json）

- `chat_client.py:12`：`CONFIG_FILE` 常量。
- `chat_client.py:load_api_configs()`（201-226）：`ApiConfigService().get_all()` 主源，失败回退 `open(CONFIG_FILE)`。
- `app/ui/settings.py:137-148`：Save Changes 除了 `ApiConfigService.save_all` 之外，**还额外把配置写回 JSON**（镜像备份）。
- `scripts/migrate_all_data.py`：一次性 seed 脚本，读 JSON 灌 DB，本次不删（保留作为初始化工具）。

**DB 已是主源**，问题在于：
- `chat_client.load_api_configs` 仍带 JSON 回退，DB 报错时会拿老 JSON。
- Settings 保存时 dual-write 到 JSON，如果 DB 写成功、JSON 写失败（或反之），会产生分裂快照。

## 修改方案

### 影响文件

- `app/utils.py`
- `app/routers/cases.py`
- `app/routers/run.py`
- `chat_client.py`
- `app/ui/settings.py`
- `app/services/test_case_service.py`（若需新增 `get_by_ids`）

### 改动 1：`app/utils.py:load_data` 移除 JSON 回退

- 删除 `ENABLE_CATEGORY_FEATURE` 开关，永远走 DB
- 删除 `if df is None:` 后的 JSON 分支
- DB 报错 → 返回空 DataFrame（保留列结构），打印 error
- 删除文件顶部 `DATA_FILE` 常量、`import json` / `os.makedirs` 等仅为 JSON 服务的代码（若还有其它函数用到则保留）

### 改动 2：`app/routers/cases.py` 全部改走 DB

- 删除 `DATA_FILE / load_cases / save_cases / _sanitize_case`（保留 pydantic `TestCase` 模型作为对外契约）
- `GET /api/cases` → `TestCaseService().get_all()` 映射为 pydantic
- `POST /api/cases`：
  - 有 id → `TestCaseService().upsert_records([case.dict()])`
  - 无 id → 计算下一个 `TCxxxx`（复用 `generate_tc_id`），赋值后 upsert
- `DELETE /api/cases/{case_id}` → `TestCaseService().delete_by_ids([case_id])`

### 改动 3：`app/routers/run.py` 不再走 JSON

- `from app.services.test_case_service import TestCaseService`
- 用 `service.get_by_ids(request.case_ids)`；若该方法不存在，则在 `TestCaseService` 增加：
  ```python
  def get_by_ids(self, ids: List[str]) -> List[TestCase]:
      return self.db.query(TestCase).filter(TestCase.id.in_(ids)).all()
  ```
- 把 ORM 对象转成 dict 传给 `engine.run_batch`（用现有 `load_data` 的字段映射同款）

### 改动 4：`chat_client.load_api_configs` 移除 JSON 回退

```python
def load_api_configs():
    from app.services.api_config_service import ApiConfigService
    try:
        return ApiConfigService().get_all()
    except Exception as e:
        print(f"[load_api_configs] DB failed: {e}")
        return {}
```

- 删除 `CONFIG_FILE` 常量及所有 `open(CONFIG_FILE)` 代码。

### 改动 5：`app/ui/settings.py` 保存流程仅写 DB

- 删除 `from chat_client import CONFIG_FILE` 及 `with open(CONFIG_FILE, "w") ... json.dump(...)` 这段镜像写文件的代码
- 只调用 `ApiConfigService().save_all(new_configs)`
- Debug 区不再 `importlib.reload(chat_client)`（原来是为了让改到 JSON 的配置生效；DB 单源不需要 reload）

### 改动 6：物理文件

- **保留** `data/test_cases.json`、`data/api_config.json` 物理文件不删（可作为一次性备份 forensics）。代码上没有任何路径再引用它们。

## 边界与验证

1. Streamlit：DB 有数据 → 正常；DB 报错 → 空表 + 控制台 error（不再展示 JSON 老快照）。
2. FastAPI `/api/cases` CRUD 与 UI 展示一致。
3. `/api/run` 执行的用例集与 UI 一致。
4. Settings 修改 API 配置 → 只在 DB 生效；JSON 文件保持原状（可能过时，不再作为数据源）。
5. `chat_client.get_chat_response` 通过 DB 读到的 `api_name` 分派正确。

## 回滚

改动集中在少数文件，`git revert` 单一 commit 即可。

## 不做

- 不删物理 JSON 文件（人工确认后再清理）
- 不动 `data/api_config.json` 之外的其他 JSON（blind_reviews / EB_Golden 保持）
- 不动 `scripts/migrate_all_data.py`（seed 工具留用）
- 不重构 `TYPE_DEFAULTS` / `merge_config_with_defaults`
