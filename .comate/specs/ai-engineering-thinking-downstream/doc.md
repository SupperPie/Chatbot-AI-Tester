# AI Engineering thinking/result 下游渲染排查

## 背景

`chat_client.py:get_ai_engineering_response` 已按 `is_thinking` 正确拆分为 `result` / `thinking` 字段（doc: `ai-engineering-thinking-split`）。样例数据验证解析逻辑无误：
- 前 N 帧 `is_thinking:true` → thinking
- 后 M 帧 `is_thinking:false` → result
- `done` 帧 `content:""` 不再覆盖

但用户实测报告 UI 上仍出现"前十几个对，后面混到一起"。因此瓶颈疑似在下游（api_config 路由、test_engine 处理、UI 渲染）。

## 排查目标

定位 ai_engineering 类型响应从 `chat_client` 返回到 UI 展示的完整字段流转，找出 thinking 与 result 被合并/覆盖的位置。

## 排查范围

1. `data/api_config.json`：确认目标 API 条目的 `type` 字段确为 `ai_engineering`，未被误路由到 `supervisor`/其他 client。
2. `app/test_engine.py`：
   - `_call_chat_with_retry` 分发逻辑，确认 `type=ai_engineering` 命中 `get_ai_engineering_response`。
   - `resp_data["result"] → actual_output`、`resp_data["thinking"] → thinking_process` 映射是否有拼接/覆盖。
   - 多轮场景下，累积 turns 时是否将 thinking 拼到 result。
3. `app/ui/report.py` / `app/ui/testcases.py`：
   - `actual_output` 与 `thinking_process` 各自的展示列。
   - 是否存在 fallback：thinking 空则显示 result，或 result 展示时 concat thinking。
4. 数据库/持久化层（如有 `app/services/test_case_service.py`）：字段是否分列存储。

## 预期结论

- 若 `type` 错误 → 修正 api_config.json
- 若 test_engine 有拼接逻辑 → 精准剔除
- 若 UI 渲染有 concat/fallback → 拆开为独立列展示

## 不改动的部分

- `chat_client.py:get_ai_engineering_response`（已验证正确）
- Session/user_id 复用逻辑
- 其它 API 类型的 client
