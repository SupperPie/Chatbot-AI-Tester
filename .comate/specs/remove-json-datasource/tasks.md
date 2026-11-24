# 移除 JSON 数据源任务计划

- [ ] Task 1: `app/utils.py` 移除 JSON 回退
    - 1.1: 删除 `ENABLE_CATEGORY_FEATURE` 分支与 `if df is None:` 后的 JSON 读取代码
    - 1.2: 保留 DB 加载与字段映射逻辑
    - 1.3: DB 报错时返回空 DataFrame（列结构与旧 fallback 保持一致）
    - 1.4: 顶部若 `DATA_FILE` / `os.makedirs` / `import json` 仅服务 JSON 用例，一并清理

- [ ] Task 2: `app/services/test_case_service.py` 新增 `get_by_ids`
    - 2.1: 增加 `def get_by_ids(self, ids: List[str]) -> List[TestCase]`
    - 2.2: 使用 `filter(TestCase.id.in_(ids))` 返回

- [ ] Task 3: `app/routers/cases.py` 全面走 DB
    - 3.1: 删除 `DATA_FILE / load_cases / save_cases / _sanitize_case`
    - 3.2: 保留 `TestCase` pydantic 模型作为 API schema
    - 3.3: `GET /api/cases` → `TestCaseService().get_all()` 映射
    - 3.4: `POST /api/cases`：无 id 时生成 `TCxxxx`，再 `upsert_records`
    - 3.5: `DELETE /api/cases/{id}` → `TestCaseService().delete_by_ids([id])`

- [ ] Task 4: `app/routers/run.py` 改用 DB
    - 4.1: 移除 `from app.routers.cases import load_cases`
    - 4.2: 使用 `TestCaseService().get_by_ids(request.case_ids)`（或 get_all 后 filter）
    - 4.3: 将 ORM 对象转成 dict 传入 `engine.run_batch`

- [ ] Task 5: `chat_client.load_api_configs` 移除 JSON 回退
    - 5.1: 删除 `CONFIG_FILE` 常量与 `open(CONFIG_FILE)` 分支
    - 5.2: DB 报错时返回 `{}`
    - 5.3: 检查是否还有其他函数引用 `CONFIG_FILE`

- [ ] Task 6: `app/ui/settings.py` 保存仅写 DB
    - 6.1: 删除 `from chat_client import CONFIG_FILE` 与 `with open(CONFIG_FILE, "w") ... json.dump(...)` 镜像写文件段
    - 6.2: 保存只调用 `ApiConfigService().save_all(new_configs)`
    - 6.3: 检查 Debug 区 `importlib.reload(chat_client)` 是否仍必要；无必要则移除

- [ ] Task 7: 全局回归确认
    - 7.1: `grep -rn "test_cases.json\\|api_config.json\\|CONFIG_FILE\\|load_cases\\|save_cases" app/ chat_client.py` 确认代码中无遗留引用（除 `scripts/migrate_all_data.py` 保留 seed 用途）
    - 7.2: `python3 -m py_compile` 关键文件全部通过

- [ ] Task 8: 手动验证清单（用户端）
    - 8.1: Streamlit：正常增删用例、切换分类，与 DB 状态一致
    - 8.2: `/api/cases` GET/POST/DELETE 三个端点行为正确
    - 8.3: `/api/run` 用例执行 OK
    - 8.4: Settings 修改 API 配置 → 重开页面仍然生效，且 `data/api_config.json` 无变化
