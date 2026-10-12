# 测试执行接口说明

本文档描述通过 HTTP 接口触发执行测试用例、查询进度与结果的用法，供 AI Agent 或外部脚本调用。

- 服务：`api_server.py`（FastAPI）
- 默认地址：`http://localhost:8000`
- 鉴权：所有 `/api/*` 接口需携带 `X-API-Key` 请求头（值来自服务端 `.env` 的 `API_KEY`）

> **端口说明**：本项目有两个独立服务，别混淆：
> - `8501` = Streamlit 前端网页（`streamlit_app.py`），日常点界面的地方，**不含**这些执行接口。
> - `8000` = FastAPI 接口服务（`api_server.py`），本文档的执行接口都在这里，**需要单独启动**。
>
> 两者共享同一个数据库：通过接口触发的执行任务，前端「测试报告」页（8501）同样能看到结果。

## 启动服务

```bash
cd /Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester

# 方式一
python3.11 -m uvicorn api_server:app --host 0.0.0.0 --port 8000

# 方式二
python api_server.py
```

> 端口 8000 在 `api_server.py` 末尾 `uvicorn.run(..., port=8000)` 硬编码，需改端口请改那一处。

执行任务在 API Server 进程内以后台线程运行，结果统一写入平台数据库（`test_history` / `test_results`，即前端「测试报告」页同一份数据），停止 API Server 不会丢失已写入的结果，但会中断正在执行的任务。

---

## 鉴权

所有 `/api/*` 请求必须携带 `X-API-Key` 请求头，值为服务端 `.env` 里的 `API_KEY`。

```bash
# 先在 shell 里设置好 key，后续示例统一用 $API_KEY
export API_KEY=你的API_KEY
```

- 未带 key 或 key 错误 → `401`
- 服务端未配置 `API_KEY` → `503`（拒绝所有 API 请求，公网部署必须配置）
- 根路径 `/` 不校验，可用于健康检查

---

## 接口总览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/meta/apis` | 列出可用 API 配置名 |
| POST | `/api/jobs` | 触发执行测试用例（支持多批） |
| GET | `/api/jobs` | 任务列表（可按状态过滤） |
| GET | `/api/jobs/{job_id}` | 查询单个任务进度 / 结果 / 总结 |

---

## 1. 查询可用 API 配置

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/meta/apis
```

响应示例：

```json
{
  "apis": ["Agent Q&A", "Bundle API", "Portal IM (PROD)", "Portal IM (TEST)", "..."]
}
```

`POST /api/jobs` 里的 `api_name` 必须从该列表中选择。

---

## 2. 触发执行测试用例

### 请求参数（`POST /api/jobs` body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `api_name` | string | 是 | API 配置名，来自 `/api/meta/apis` |
| `execution_mode` | string | 否 | `full`（语义+断言，默认）/ `semantic` / `assertion` |
| `max_workers` | int | 否 | 并发线程数，1-10，默认 3 |
| `report_name` | string | 否 | 报告名；多批时自动追加 `#1`、`#2` 后缀 |
| `case_ids` | string[] | 二选一 | 单个用例 ID 列表（等价于 `batches` 只含一个批次） |
| `batches` | string[][] | 二选一 | 多批：每个子列表生成一份独立测试报告 |
| `wait` | bool | 否 | `true` 阻塞到执行结束再返回；默认 `false` 异步 |
| `timeout_seconds` | int | 否 | `wait=true` 时的最长等待秒数，默认 1800 |

> 说明：用例 ID 为主数据源中的 `id` 字段，形如 `TC27567`。一个 ID 可能对应多轮（`type=multi_turn`），接口会自动取该 ID 的全部轮次作为一次执行。

### 示例 A：异步触发（推荐，agent 轮询）

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "api_name": "Bundle API",
    "execution_mode": "full",
    "max_workers": 3,
    "report_name": "AI 助手回归",
    "batches": [
      ["TC27567", "TC20000"],
      ["TC0002"]
    ],
    "wait": false
  }'
```

响应（立即返回，任务后台执行）：

```json
{
  "jobs": [
    { "job_id": "20261009123045", "total": 2, "report_name": "AI 助手回归 #1", "status": "running" },
    { "job_id": "20261009123046", "total": 1, "report_name": "AI 助手回归 #2", "status": "running" }
  ]
}
```

### 示例 B：同步阻塞（脚本一次性拿到结果）

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "api_name": "Bundle API",
    "execution_mode": "full",
    "case_ids": ["TC27567"],
    "wait": true,
    "timeout_seconds": 600
  }'
```

响应（执行完成后的总结，含结果明细）：

```json
{
  "jobs": [
    {
      "id": "20261009123045",
      "status": "completed",
      "api_name": "Bundle API",
      "report_name": null,
      "execution_mode": "full",
      "max_workers": 3,
      "total": 1,
      "passed": 1,
      "failed": 0,
      "started_count": 1,
      "pass_rate": 100.0,
      "error_message": null,
      "timestamp": "2026-10-09 20:30:45",
      "duration": "1m 23s",
      "results": [ { "...": "见下方结果字段" } ]
    }
  ]
}
```

---

## 3. 查询任务进度 / 结果 / 总结

```bash
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/api/jobs/20261009123045"

# 只看摘要不要明细
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/api/jobs/20261009123045?include_results=false"
```

响应字段：

| 字段 | 说明 |
|---|---|
| `status` | `running`（执行中）/ `completed` / `failed` / `cancelled` / `interrupted` |
| `total` / `started_count` | 计划总数 / 已执行数，用 `started_count/total` 可算进度 |
| `passed` / `failed` / `pass_rate` | 通过 / 失败 / 通过率（百分比） |
| `results` | 每条用例的结果明细 |

`results` 中每个元素的关键字段：

```json
{
  "id": "TC27567",
  "case_id": "TC27567",
  "input": "用户输入",
  "expected_output": "期望输出",
  "actual_output": "实际输出",
  "passed": true,
  "score": 0.92,
  "reason": "判定理由",
  "type": "multi_turn",
  "total_turns": 3,
  "passed_turns": 3,
  "success_rate": 100.0,
  "latency": 2.3,
  "ttft": 0.4
}
```

---

## 4. 任务列表

```bash
# 只看已完成的
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/api/jobs?status=completed&limit=10"

# 分页
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/api/jobs?limit=20&offset=20"
```

---

## Agent 推荐调用流程

1. `GET /api/meta/apis` 获取 `api_name` 候选值。
2. `POST /api/jobs`（`wait=false`）提交批次，拿到 `job_id` 列表。
3. 轮询 `GET /api/jobs/{job_id}`，直到 `status` 不再是 `running`。
4. 读取 `pass_rate` / `passed` / `failed` 作为执行总结；需要定位失败用例时取 `results` 里 `passed=false` 的项。

### Python 调用示例

```python
import time
import requests

BASE = "http://localhost:8000"
API_KEY = "你的API_KEY"                 # 或 os.environ["API_KEY"]
HEADERS = {"X-API-Key": API_KEY}

# 1. 查可用 API
apis = requests.get(f"{BASE}/api/meta/apis", headers=HEADERS, timeout=10).json()["apis"]

# 2. 异步触发
resp = requests.post(
    f"{BASE}/api/jobs",
    headers=HEADERS,
    json={
        "api_name": apis[0],
        "execution_mode": "full",
        "max_workers": 3,
        "case_ids": ["TC27567", "TC20000"],
    },
    timeout=10,
).json()

job_id = resp["jobs"][0]["job_id"]

# 3. 轮询到结束
while True:
    job = requests.get(f"{BASE}/api/jobs/{job_id}", headers=HEADERS, timeout=10).json()
    if job["status"] != "running":
        break
    time.sleep(2)

print(f"通过率: {job['pass_rate']}%  ({job['passed']}/{job['total']})")
```

---

## 错误码

| 状态码 | 含义 |
|---|---|
| 400 | 参数错误（`api_name` 不存在、`execution_mode` 非法、未提供用例等） |
| 401 | 未带 `X-API-Key` 或 key 错误 |
| 404 | `job_id` 不存在 |
| 500 | 服务端异常（详情见 `detail` 字段） |
| 503 | 服务端未配置 `API_KEY`，拒绝所有 API 请求 |