# AI Engineering 流式接口测试实现

## 需求场景

为 `https://ai-engineering-test.dragonpass.com.cn/stream` 接口配置测试请求，实现 SSE 流式响应解析和特定字段提取。

## 技术方案

### 接口规格

- **URL**: `https://ai-engineering-test.dragonpass.com.cn/stream`
- **Method**: POST
- **Protocol**: Server-Sent Events (SSE)

### 请求配置

**Headers**:
```
Content-Type: application/json
Accept: text/event-stream
```

**Body (JSON)**:
```json
{
    "query": "用户自然语言文本",
    "user_id": "用户ID",
    "thread_id": "会话ID",
    "lob": "dc" // 或 "ata"
}
```

### 响应解析逻辑

响应为 SSE 格式 (`data: {...}`)，JSON 结构包含字段：
- `type`: 消息类型 (`"content"` / `"done"`)
- `title`: 标题
- `content`: 内容文本
- `agent_id`: 代理ID
- `is_thinking`: 是否为思维链
- `session_id`: 会话ID
- `user_id`: 用户ID
- `data`: 结构化数据（仅在 `type=done` 时有值）
- `meta`: 元数据

**解析规则**:
1. `type == "content"`: 流式输出中，`data` 为空
   - `is_thinking == true`: 思维链内容 → 累积到 `thinking`
   - `is_thinking == false`: 正常回复 → 累积到 `result`
2. `type == "done"`: 流式结束
   - 提取 `content` 作为最终 `result`
   - 提取 `data` 作为结构化数据

### 结果输出格式

```json
{
    "result": "content字段内容（type=done时）",
    "thinking": "思维链内容累积",
    "inform_base": "",
    "raw": "完整原始响应",
    "ttft": 0.0
}
```

## 受影响文件

| 文件 | 修改类型 | 影响范围 |
|------|---------|---------|
| `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/chat_client.py` | 新增函数 | 添加 `get_ai_engineering_response()` |
| `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/chat_client.py` | 修改函数 | 在 `get_chat_response()` 添加 `ai_engineering` 类型路由 |
| `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/data/api_config.json` | 新增配置 | 添加 `AI Engineering` API 配置项 |

## 实现细节

### 1. 新增函数 `get_ai_engineering_response()`

**位置**: `chat_client.py` 第 505 行附近（在 `get_agent_qa_response` 之后）

```python
def get_ai_engineering_response(message: str, url: str, user_id: str = None, session_id: str = None, lob: str = "dc") -> str:
    """AI Engineering 流式接口客户端
    
    响应解析规则：
    - type="content": 流式输出中，根据 is_thinking 区分思维链/正常内容
    - type="done": 流式结束，提取 content 作为 result，data 包含结构化数据
    """
    if user_id is None:
        user_id = str(uuid.uuid4())
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]
    
    payload = {
        "query": message,
        "user_id": user_id,
        "thread_id": session_id,
        "lob": lob
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }

    print(f"[AI Engineering] Sending request to {url} with query: {message}")
    
    try:
        start_time = time.time()
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=600)
        
        if not response.ok:
            print(f"[AI Engineering] API Error {response.status_code}: {response.text}")
            return f"❌ SERVER DETAIL ({response.status_code}): {response.text}"
            
        final_answer = ""
        thinking_process = []
        raw_chunks = []
        structured_data = None
        
        ttft = 0.0
        got_first_token = False
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: "):
                    json_str = decoded_line[6:]
                    if json_str.strip() == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(json_str)
                        raw_chunks.append(json.dumps(data, ensure_ascii=False))

                        msg_type = data.get("type")
                        content = data.get("content", "")
                        is_thinking = data.get("is_thinking", False)
                        
                        if msg_type == "content":
                            # 流式输出中
                            if content:
                                if not got_first_token:
                                    ttft = time.time() - start_time
                                    got_first_token = True
                                if is_thinking:
                                    thinking_process.append(content)
                                else:
                                    final_answer += content
                                    
                        elif msg_type == "done":
                            # 流式结束，提取最终内容
                            if not got_first_token:
                                ttft = time.time() - start_time
                                got_first_token = True
                            if content:
                                final_answer = content  # done 时的 content 作为最终结果
                            structured_data = data.get("data")
                            break

                    except json.JSONDecodeError:
                        raw_chunks.append(f"Decode Error: {json_str}")
                        continue
        
        thinking_str = "".join(thinking_process)
        raw_full_str = "\n".join(raw_chunks)
        
        if not final_answer:
            if thinking_str:
                final_answer = "Refers to thinking process for details."
            elif raw_chunks:
                final_answer = "Raw data captured (parsing failed). See Raw Data."
            else:
                final_answer = "Error: No response content found."

        result_obj = {
            "result": final_answer, 
            "thinking": thinking_str,
            "inform_base": json.dumps(structured_data, ensure_ascii=False) if structured_data else "",
            "raw": raw_full_str,
            "ttft": ttft
        }
        
        return json.dumps(result_obj, ensure_ascii=False)

    except requests.exceptions.Timeout:
        return "Error: AI Engineering API Request Timed Out (600s)"
    except Exception as e:
        print(f"[AI Engineering] Error: {e}")
        return f"Error: {e}"
```

### 2. 修改 `get_chat_response()` 函数

在 `chat_client.py` 第 881 行附近，`elif api_type == "agent_qa":` 后添加：

```python
elif api_type == "ai_engineering":
    lob = config.get("lob", "dc")
    return get_ai_engineering_response(message, url=url, user_id=user_id, session_id=session_id, lob=lob)
```

### 3. API 配置项

在 `data/api_config.json` 中添加：

```json
"AI Engineering": {
    "url": "https://ai-engineering-test.dragonpass.com.cn/stream",
    "description": "AI Engineering 流式测试接口",
    "type": "ai_engineering",
    "lob": "dc"
}
```

## 边界条件与异常处理

1. **连接超时**: 600 秒超时保护
2. **HTTP 错误**: 返回状态码和错误详情
3. **JSON 解析失败**: 记录原始数据，继续处理
4. **无内容响应**: 返回友好错误提示，优先展示 thinking 或 raw 数据

## 预期结果

配置完成后，可在测试平台选择 "AI Engineering" API 进行流式接口测试，支持：
- 实时接收 SSE 流式数据
- 区分思维链和正常回复内容
- 提取 `type=done` 时的完整结果
- 保存原始响应数据用于调试
