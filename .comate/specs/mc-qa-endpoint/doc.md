# MC问答 API 端点配置

## 需求场景

在 Settings 页面的 endpoint list 中添加一个新的 API 类型 "MC问答"（Mastercard Q&A），用于调用 Dify Workflow 类型的接口。

## 接口信息

### 请求配置
- **URL**: `https://ai-flow-app-uk.dp-svc.com/api/chat-messages`
- **Method**: POST
- **Content-Type**: application/json

### 特殊 Headers
| Header | 值 |
|--------|-----|
| x-app-code | ZdbUw8IngEi4CwZD |
| x-app-passport | eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... (JWT Token) |

### 请求体
```json
{
  "response_mode": "streaming",
  "conversation_id": "43d24ccf-e55f-45ba-8685-149871cab985",
  "files": [],
  "query": "用户问题",
  "inputs": {},
  "parent_message_id": "可选"
}
```

### 响应解析
响应为 SSE 流式数据，需要从 `event: workflow_finished` 事件中提取 `data.outputs.answer` 作为最终回答。

```json
data: {"event":"workflow_finished",...,"data":{"outputs":{"answer":"最终回答内容"}}}
```

## 技术方案

### 新增 API 类型
创建新类型 `dify_workflow`（而非 `mc_qa`），因为这种响应格式是 Dify Workflow 的标准格式，具有复用性。

### 配置结构
在 `api_config.json` 中的配置：
```json
{
  "MC问答": {
    "url": "https://ai-flow-app-uk.dp-svc.com/api/chat-messages",
    "description": "Mastercard Travel Pass Q&A",
    "type": "dify_workflow",
    "token": "ZdbUw8IngEi4CwZD|eyJhbGciOiJIUzI1NiIs..."
  }
}
```

**token 格式**: `{x-app-code}|{x-app-passport}`，用 `|` 分隔两个认证值。

## 影响文件

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `/chat_client.py` | 新增函数 | 添加 `get_dify_workflow_response()` 函数 |
| `/chat_client.py` | 修改 | 在 `get_chat_response()` 中添加路由分支 |
| `/app/ui/settings.py` | 修改 | 在类型选项中添加 `dify_workflow` |

## 实现细节

### 1. get_dify_workflow_response() 函数

```python
def get_dify_workflow_response(message: str, url: str, token: str = None, user_id: str = None, session_id: str = None) -> str:
    """Dify Workflow API client (workflow_finished 响应格式).
    
    token 格式: "x-app-code|x-app-passport"
    """
    if user_id is None:
        user_id = str(uuid.uuid4())
    
    # 解析 token
    app_code, app_passport = "", ""
    if token and "|" in token:
        parts = token.split("|", 1)
        app_code, app_passport = parts[0], parts[1]
    
    # conversation_id 验证
    import re as _re
    _uuid_pattern = _re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', _re.IGNORECASE
    )
    conversation_id = session_id if session_id and _uuid_pattern.match(session_id) else ""

    payload = {
        "inputs": {},
        "query": message,
        "response_mode": "streaming",
        "conversation_id": conversation_id,
        "files": [],
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "x-app-code": app_code,
        "x-app-passport": app_passport,
    }

    # 流式请求处理
    response = requests.post(url, json=payload, headers=headers, stream=True, timeout=600)
    
    # 解析响应，从 workflow_finished 事件提取 outputs.answer
    for line in response.iter_lines():
        if line:
            decoded_line = line.decode("utf-8")
            if decoded_line.startswith("data: "):
                data = json.loads(decoded_line[6:])
                if data.get("event") == "workflow_finished":
                    outputs = data.get("data", {}).get("outputs", {})
                    final_answer = outputs.get("answer", "")
                    # 同时提取 retriever_resources 作为 inform_base
    
    return json.dumps({
        "result": final_answer,
        "thinking": "",
        "inform_base": retriever_info,
        "raw": raw_chunks,
        "ttft": ttft,
    })
```

### 2. get_chat_response() 路由分支

在 `chat_client.py` 的 `get_chat_response()` 函数中添加：
```python
elif api_type == "dify_workflow":
    return get_dify_workflow_response(message, url, token, user_id, session_id)
```

### 3. Settings 页面类型选项

在 `app/ui/settings.py` 的 `options` 列表中添加 `"dify_workflow"`。

## 边界条件

1. **token 格式错误**: 如果 token 不包含 `|` 分隔符，则 app_code 和 app_passport 为空，请求可能失败
2. **响应无 workflow_finished 事件**: 返回错误信息
3. **网络超时**: 600 秒超时

## 预期结果

1. Settings 页面可以选择 `dify_workflow` 类型
2. 配置 "MC问答" 端点后，可以正常进行测试
3. 测试结果正确解析 `outputs.answer` 作为回答内容
