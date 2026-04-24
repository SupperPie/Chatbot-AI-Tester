# api-config-override: 同 Type 多配置 + 参数覆盖 + DB 持久化

## 需求场景与处理逻辑

当前架构中，`Type` 决定了 Request Body 构造方式和 Response 解析逻辑，二者硬编码在 `chat_client.py` 的各 `get_xxx_response()` 函数中。现有数据结构已支持 `url` 和 `token` 的配置化，但 Request Body 参数（payload 中除 `message` 以外的固定字段）无法通过 UI 配置。

此外，API 配置当前仅存储在 `data/api_config.json` 文件中。虽然数据库已有 `api_configs` 表（`create_tables.sql:134`），且迁移脚本 `migrate_all_data.py:29` 已支持导入，但代码的读写全走 JSON 文件。需要将 API 配置迁移到数据库，与 test_cases 保持一致的"DB 优先、JSON 回退"策略。

用户期望：
1. 同一 `Type` 可以创建多行配置（不同环境/不同参数）
2. `Type` 仅决定解析结构（Response 解析 + Request Body 默认模板）
3. `URL`、`Token`、`Request Body 参数` 均可在每行配置中独立覆盖
4. 未填写的字段自动回退到 Type 的默认值，UI 以灰色 placeholder 提示默认值
5. API 配置持久化到数据库（DB 优先，JSON 作为回退/初始数据源）

## 技术方案

### 核心思路："DB 持久化 + 默认模板 + 运行时覆盖"

1. **API 配置迁移到数据库**：
   - 新增 ORM Model `ApiConfig`（`app/models/api_config.py`）
   - 扩展数据库表 `api_configs`：新增 `token`、`request_params` 字段
   - 新增 Service 层 `ApiConfigService`（`app/services/api_config_service.py`）
   - `load_api_configs()` 改为 DB 优先读取，DB 不可用时回退 JSON
   - Settings 页面保存改为写 DB（同时保留 JSON 备份写入）
2. **新增默认模板注册表**：在 `chat_client.py` 中定义每个 Type 的默认 `url`、`token`、`request_params`
3. **运行时合并**：`get_chat_response()` 调用前，将配置中的字段与 Type 默认模板合并（配置优先）
4. **各 `get_xxx_response()` 接收 extra_params**：将合并后的参数传入，替代原先硬编码值
5. **UI 扩展**：Settings 页面新增 Request Params 列（JSON 编辑），空值时以 placeholder 展示默认值

### 不改动的部分
- Response 解析逻辑完全不变（各函数内的 SSE/JSON 解析代码）
- 统一返回格式 `{result, thinking, inform_base, raw, ttft}` 不变
- 多轮会话的 session 管理不变

## 影响文件

### 1. `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/scripts/create_tables.sql`
- **修改类型**: 表结构扩展
- 扩展 `api_configs` 表，新增 `token TEXT`、`request_params JSONB` 字段

### 2. `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/models/api_config.py`（新增）
- **修改类型**: 新增 ORM Model
- 定义 `ApiConfig` 类，字段映射到扩展后的 `api_configs` 表

### 3. `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/services/api_config_service.py`（新增）
- **修改类型**: 新增 Service 层
- 提供 `get_all()`, `save_all()`, `upsert()` 等数据库操作方法

### 4. `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/chat_client.py`
- **修改类型**: 核心逻辑重构
- **影响函数**:
  - 修改：`load_api_configs()` — DB 优先读取，回退 JSON
  - 新增：`TYPE_DEFAULTS` 常量 + `merge_config_with_defaults()` + `deep_merge()`
  - 修改：`get_chat_response()` (LINE 1055-1094) — 增加参数合并逻辑
  - 修改：各 `get_xxx_response()` 函数的 payload 构造段 — 从硬编码改为接收 `extra_params` 并合并

### 5. `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/settings.py`
- **修改类型**: UI 扩展 + 存储层切换
- **影响函数**: `render_settings_page()` (LINE 6-78)
  - 读取改为从 DB（通过 Service）加载
  - 新增 `Request Params` 列（JSON 文本编辑）
  - 保存改为写 DB + JSON 双写

### 6. `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/data/api_config.json`
- **修改类型**: 数据结构扩展（兼容回退数据源）
- 新增可选字段 `request_params`（dict），旧数据无此字段时默认为空 dict

## 实现细节

### 1. Type 默认模板注册表

```python
# chat_client.py 新增
TYPE_DEFAULTS = {
    "bundle": {
        "url": "",
        "token": "",
        "request_params": {
            "config": {
                "struc_properties_filter": [
                    "meta.semantic_info.intent",
                    "data.bundle_list"
                ]
            }
        }
    },
    "skills": {
        "url": "",
        "token": "",
        "request_params": {
            "stream_mode": "MESSAGES",
            "anchor": "",
            "mobile_no": "13112748887"
        }
    },
    "flight": {
        "url": "",
        "token": "",
        "request_params": {
            "line_of_business": "dev_lob",
            "additionalProp1": {}
        }
    },
    "limo": {
        "url": "",
        "token": "",
        "request_params": {
            "config": {
                "struc_properties_filter": ["meta.semantic_info.intent", ...]
            }
        }
    },
    "dify": {
        "url": "",
        "token": "",
        "request_params": {
            "inputs": {},
            "response_mode": "streaming"
        }
    },
    "dify_workflow": {
        "url": "",
        "token": "",
        "request_params": {
            "inputs": {},
            "response_mode": "streaming",
            "files": []
        }
    },
    "agent_qa": {
        "url": "",
        "token": "",
        "request_params": {
            "lob": "dc"
        }
    },
    "hotel": {
        "url": "",
        "token": "",
        "request_params": {
            "ex": { ... }  # 完整的酒店扩展参数默认值
        }
    },
    "ai_engineering": {
        "url": "",
        "token": "",
        "request_params": {
            "lob": "ata"
        }
    },
    "translation": {
        "url": "",
        "token": "",
        "request_params": {
            "config": {
                "translate_config": {
                    "sys_lang": "pt-BR"
                }
            }
        }
    }
}
```

### 2. 参数合并逻辑

```python
def merge_config_with_defaults(config: dict) -> dict:
    """将配置行与 Type 默认模板合并，配置值优先"""
    api_type = config.get("type", "bundle")
    defaults = TYPE_DEFAULTS.get(api_type, {})
    
    merged = {}
    # URL: 配置有值则用配置，否则用默认
    merged["url"] = config.get("url") or defaults.get("url", "")
    # Token: 同理
    merged["token"] = config.get("token") or defaults.get("token", "")
    # Request Params: 深合并，配置层覆盖默认层
    default_params = defaults.get("request_params", {})
    config_params = config.get("request_params", {})
    merged["request_params"] = deep_merge(default_params, config_params)
    
    return merged

def deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典，override 优先"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
```

### 3. get_chat_response() 修改

```python
def get_chat_response(message, api_name="Bundle API", user_id=None, session_id=None):
    configs = load_api_configs()
    config = configs.get(api_name)
    if not config:
        return f"Error: API Configuration '{api_name}' not found."
    
    # 合并默认值
    merged = merge_config_with_defaults(config)
    url = merged["url"]
    token = merged["token"]
    extra_params = merged["request_params"]
    
    if not url:
        return f"Error: No URL configured for '{api_name}'."
    
    api_type = config.get("type", "bundle")
    
    if api_type == "skills":
        return get_skills_response(message, url=url, user_id=user_id, session_id=session_id, extra_params=extra_params)
    elif api_type == "dify":
        return get_dify_response(message, url=url, token=token, user_id=user_id, session_id=session_id, extra_params=extra_params)
    # ... 其他类型同理
```

### 4. 各 get_xxx_response() 函数改造示例

以 `get_skills_response` 为例：

```python
def get_skills_response(message, url, user_id=None, session_id=None, extra_params=None):
    if user_id is None:
        user_id = str(uuid.uuid4())
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]
    
    # 基础 payload（message/session 等固定字段）
    payload = {
        "session_id": session_id,
        "message": message,
    }
    # 合并可覆盖参数（来自 Type 默认 + 配置覆盖）
    if extra_params:
        payload.update(extra_params)
    
    # ... 其余 SSE 解析逻辑不变
```

### 5. Settings UI 扩展

在 `st.data_editor` 的列配置中新增 `Request Params`：

```python
"Request Params": st.column_config.TextColumn(
    "Request Params (JSON)",
    help="自定义请求参数，JSON 格式。留空则使用 Type 默认值。",
    width="large"
),
```

保存时解析 JSON 字符串为 dict 并存入配置。在表格下方增加"当前 Type 默认参数预览"辅助区域。

## 边界条件与异常处理

1. **旧数据兼容**：`api_config.json` 中无 `request_params` 字段的行，`config.get("request_params", {})` 返回空 dict，合并后使用纯默认值，行为与改造前完全一致
2. **Token 为 "None" 字符串**：现有数据中部分行 token 值为 `"None"`，需在合并时将 `"None"` 视为空值
3. **request_params JSON 解析失败**：UI 保存时做 JSON 校验，解析失败则提示用户修正
4. **同名配置**：配置以 Name 为 key，当前已天然唯一；同 Type 不同 Name 即为多环境配置
5. **deep_merge 非 dict 值**：override 中非 dict 值直接覆盖，不递归

## 数据流

```
[api_config.json] → load_api_configs() → config dict
        ↓
merge_config_with_defaults(config)
    → 读取 TYPE_DEFAULTS[type]
    → deep_merge(defaults.request_params, config.request_params)
    → 返回 {url, token, request_params}
        ↓
get_chat_response() 按 type 路由
        ↓
get_xxx_response(message, url, ..., extra_params)
    → payload = {message, session, ...} + extra_params
    → HTTP POST → SSE/JSON 解析（不变）
    → 返回统一格式
```

## 预期结果

- 可在配置表中添加多个 Type 相同但 URL/Token/Request Params 不同的配置行
- Response 解析逻辑严格遵循 Type 定义，不受参数覆盖影响
- 未填写 request_params 时自动回退到 Type 默认值，行为与改造前一致
- UI 中 Request Params 列支持 JSON 编辑，空值时以帮助提示展示默认模板