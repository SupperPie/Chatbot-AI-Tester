# AI Engineering 响应 is_thinking 拆分

## 需求背景

当前 `get_ai_engineering_response`（`chat_client.py:746`）在解析 SSE 流时，将所有 `type=content` 的 chunk 内容全部累加到 `final_answer`，最终返回 `{"result": final_answer, "thinking": ""}`。

实际接口每个 chunk 会额外带一个 `is_thinking` 布尔字段：
- `is_thinking = true`：属于模型思考过程（thinking），应落在 **thinking** 列
- `is_thinking = false`：属于最终答复正文，应落在 **actual result** 列

需要在流式解析中按 `is_thinking` 拆分累积，并分别填入返回体的 `thinking` / `result` 字段。

## Session/User ID 复用（Q1，已确认无需改动）

- 单轮：`app/test_engine.py:408` `_call_chat_with_retry(input_text, api_name=api_name)` 不传 ID → `get_ai_engineering_response` 每个 case 自生成新 UUID（`chat_client.py:765-768`）。
- 多轮：`app/test_engine.py:739-740` 为每个 `case_id` 生成一对 `(user_id, session_id)`，在 778-779 传给 `_call_chat_with_retry`，同一 case 内的所有 turn 复用。
- `extra_params` 合并时显式 pop 掉 `user_id/session_id/thread_id`（`chat_client.py:789-791`），防止外部配置覆盖。

结论：当前实现已满足"不同 case 用不同 ID、多轮同 case 复用 ID"的要求，本次不修改。

## 技术方案（Q2）

### 影响文件

- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/chat_client.py`
  - 函数：`get_ai_engineering_response`（第 746-875 行）
  - 修改范围：SSE 累积循环（819-853）、fallback 处理（857-861）、返回值构造（863-869）

### 改造点

1. 新增两个累加器：
   ```python
   answer_parts = []
   thinking_parts = []
   ```
   移除原 `final_answer = ""` 单一累加器（或保留但仅在 `done` 帧回退用）。

2. `type=content` 分支按 `is_thinking` 分流：
   ```python
   is_thinking = bool(data.get("is_thinking", False))
   if msg_type == "content":
       if content:
           if not got_first_token:
               ttft = time.time() - start_time
               got_first_token = True
           if is_thinking:
               thinking_parts.append(content)
           else:
               answer_parts.append(content)
   ```

3. `type=done` 分支：
   - 若 `done` 帧带 `content`，视为最终答复覆盖 `answer_parts`（保持与旧行为一致：`done` 的 content 是最终 result）。
   - `done` 帧一般不属于 thinking，忽略其 `is_thinking`。
   ```python
   elif msg_type == "done":
       if not got_first_token:
           ttft = time.time() - start_time
           got_first_token = True
       if content:
           answer_parts = [content]
       break
   ```

4. 返回体：
   ```python
   final_answer = "".join(answer_parts)
   thinking_text = "".join(thinking_parts)

   if not final_answer:
       final_answer = "Raw data captured (parsing failed). See Raw Data." if raw_chunks else "Error: No response content found."

   return json.dumps({
       "result": final_answer,
       "thinking": thinking_text,
       "inform_base": "",
       "raw": raw_full_str,
       "ttft": ttft
   }, ensure_ascii=False)
   ```

### 下游影响

- `app/test_engine.py` 已将返回 JSON 中 `result` → `actual_output`、`thinking` → `thinking_process`，本次仅是把此前一直为空的 `thinking` 填上内容，无需改动 test_engine 或 UI。
- 报告/UI 侧对 `thinking_process` 已有渲染逻辑，改动后 thinking 列会自动出现内容。

## 边界与异常

- `is_thinking` 字段缺失 → 默认 `False`，行为等价于旧逻辑（全进 answer）。
- 只有 thinking、没有 answer → `answer_parts` 为空，走 fallback 文案 "No response content found." / raw fallback；此时 UI 上 result 列会显示 fallback，thinking 列显示实际思考内容。
- `done` 帧带内容 → 直接覆盖 answer，符合原语义。
- JSON 解码错误 → 与旧逻辑一致，追加到 `raw_chunks` 并跳过。

## 预期结果

- ai_engineering 类型的测试用例，`thinking` 列显示模型思考过程，`actual result` 列仅显示 `is_thinking=false` 的正文。
- 其它 API 类型（trip_planner、entitlements 等）不受影响。
- 单轮/多轮的 session_id、user_id 语义保持不变。
