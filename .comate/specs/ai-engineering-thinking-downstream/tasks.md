# AI Engineering thinking/result 下游渲染排查任务

- [x] Task 1: 确认 API 路由
    - 1.1: 查看 `data/api_config.json` 中出现问题的 API 条目 `type` 字段
    - 1.2: 在 `app/test_engine.py` 搜索 `_call_chat_with_retry` 或类似分发函数，确认 `ai_engineering` 类型走到 `get_ai_engineering_response`
    - 1.3: 若发现类型错误或分发漏走，记录并列入修复项

- [x] Task 2: 审查 test_engine 字段映射
    - 2.1: 定位 `resp_data["result"]` / `resp_data["thinking"]` 的读取处
    - 2.2: 检查有无字符串拼接（例如 `thinking + result` 或 `result += thinking`）
    - 2.3: 多轮聚合时确认 turns 拼接的是 result 而非把 thinking 一并 join
    - 2.4: 记录并修正发现的合并/覆盖逻辑

- [x] Task 3: 审查 UI 渲染层
    - 3.1: 定位 `app/ui/report.py` / `app/ui/testcases.py` 中 `actual_output` 与 `thinking_process` 列的渲染代码
    - 3.2: 检查 fallback 逻辑（thinking 空时显示 result、或 result 空时 fallback thinking）
    - 3.3: 若 UI 存在 concat/fallback 导致混淆，拆分为独立展示

- [x] Task 4: 端到端验证
    - 4.1: 用用户提供的样例（伦敦 Coldplay case）实跑
    - 4.2: 确认 thinking 列显示"**为您解析需求** ..."、result 列显示"您的这个问题..."
    - 4.3: 回归其它 API 类型（trip_planner、hotel、限差 limo 等）字段展示无回归
