# Trip Planner: Split is_thinking Chunks into thinking / actual result

## Background
`get_trip_planner_response` in `chat_client.py` currently ignores the `is_thinking` field emitted by the supervisor SSE stream. It waits only for the final `type == "done"` frame and extracts `data.summary_state.details` as the answer, so the downstream `thinking` column stays empty.

The user wants:
1. **Chunks with `is_thinking: true`** → accumulated into the `thinking` field of the returned JSON (surfaced as the "Thinking" column in the report).
2. **Chunks with `is_thinking: false`** → accumulated into the `result` field (actual output).
3. Session/user ID handling is already correct (single-turn = fresh UUID per case; multi-turn = shared UUID per conversation group). **No changes to ID logic.**

## Response Format (assumed based on user request + SSE convention)
Each SSE frame typically looks like:
```json
data: {"type": "token", "is_thinking": true,  "content": "...partial reasoning..."}
data: {"type": "token", "is_thinking": false, "content": "...partial answer..."}
...
data: {"type": "done",  "data": {"summary_state": {"details": "...full markdown..."}}, "content": "..."}
```

The parser must be robust to:
- Frames missing the `is_thinking` field (treat as `false` = actual answer, safest default).
- Frames where `content` is missing or empty.
- Non-token frames (e.g., `type: "done"`, `type: "planning"`) — only their `content` field is aggregated if `is_thinking` is present; otherwise skipped for accumulation.
- The done frame carrying the canonical final `details` — if present, it **overrides** the accumulated `result` (server's authoritative answer).

## Technical Approach

### File Affected
`/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/chat_client.py` (only)

### Changes inside `get_trip_planner_response` — SSE branch

Replace the current loop (which discards token content) with:
```python
thinking_parts = []
answer_parts = []
final_answer_from_done = ""

for line in response.iter_lines():
    ... decode json_str as before ...
    data = json.loads(json_str)
    if not isinstance(data, dict):
        continue
    raw_chunks.append(json.dumps(data, ensure_ascii=False))

    if not got_first_token:
        ttft = time.time() - start_time
        got_first_token = True

    msg_type = data.get("type")
    content_piece = data.get("content", "") or ""
    is_thinking = bool(data.get("is_thinking", False))

    if msg_type == "done":
        final_answer_from_done = _extract_result(data)
        # done frame may also carry a content string; if it does and we
        # have not received it earlier, still capture it as an answer piece
        if content_piece and not final_answer_from_done:
            answer_parts.append(content_piece)
        break

    # Streaming token frames
    if content_piece:
        if is_thinking:
            thinking_parts.append(content_piece)
        else:
            answer_parts.append(content_piece)

thinking_text = "".join(thinking_parts)
final_answer = final_answer_from_done or "".join(answer_parts)
```

### Changes for the non-SSE (regular JSON) branch
Non-SSE responses return a single JSON blob. If that blob carries `is_thinking` at the top level, honor it; otherwise fall back to `_extract_result` (unchanged behavior).

```python
data = response.json()
if isinstance(data, dict):
    if data.get("is_thinking") is True:
        thinking_text = data.get("content", "") or ""
        final_answer = ""
    else:
        thinking_text = ""
        final_answer = _extract_result(data)
```

### Return shape (unchanged keys)
```python
return json.dumps({
    "result":     final_answer,
    "thinking":   thinking_text,
    "inform_base": "",
    "raw":        raw_str[:5000],
    "ttft":       ttft
}, ensure_ascii=False)
```

The downstream `test_engine.py` already routes `resp_data["thinking"]` to the report's `thinking_process` column, so no changes to the engine or UI are needed.

## Boundary Conditions
- Zero thinking chunks → `thinking_text = ""` (unchanged behavior).
- Zero non-thinking chunks but done frame has details → `final_answer` comes from done frame.
- No done frame but stream ends normally → `final_answer` = accumulated non-thinking parts.
- Malformed frames → still logged into `raw_chunks` under existing `JSONDecodeError` handling.

## Expected Outcome
- Test cases run against Trip Planner now show:
  - **"Thinking" column** = reasoning stream captured (agent's chain-of-thought).
  - **"Actual Result" column** = clean final answer only.
- Existing single-turn / multi-turn ID behavior is preserved.
- No breaking changes to other API types (bundle / dify / entitlements / ai_engineering / etc.).
