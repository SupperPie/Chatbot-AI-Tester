# Chatbot AI Tester 对外接口文档

面向 AI Agent / 第三方系统调用的 HTTP 接口说明。所有接口复用平台内部的 service 层，直接对 PostgreSQL 数据源读写。

- **版本**：`5.0`
- **Base URL**：`http://<host>:8000`
- **协议**：HTTP/JSON
- **鉴权**：除健康检查外，所有接口要求 `X-API-Key` 请求头

---

## 1. 鉴权

| 请求头 | 说明 |
|--------|------|
| `X-API-Key` | 取值来自服务端 `.env` 中的 `API_KEY` |

- 未携带 / 密钥错误 → `401 Invalid or missing X-API-Key header`
- 服务端未配置 `API_KEY` → `503 API_KEY not configured on server`
- 根路径 `GET /` 为健康检查，**无需鉴权**

```bash
curl -X GET "http://127.0.0.1:8000/"                            # 健康检查，unused key
curl -X GET "http://127.0.0.1:8000/api/v1/reports" \
     -H "X-API-Key: $API_KEY"                                    # 需鉴权
```

---

## 2. 通用约定

- 所有业务接口位于 `/api/v1/*` 前缀下。
- 列表类接口返回 `{"total": N, "items": [...]}`；删除/更新类返回 `{"ok": true, ...}`。
- `execution_mode` 枚举：`full`（语义+断言）/ `semantic`（仅语义）/ `assertion`（仅断言）。
- `priority` 枚举：`P0` / `P1` / `P2`。
- `type` 枚举：`single`（单轮）/ `multi_turn`（多轮）。

---

## 3. 测试用例（`/api/v1/cases`）

### 用例字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 用例 ID（如 `FAQ_001`、`TC0001`）。保存时缺省会自动生成 `TCxxxx` |
| `turn_index` | int | 轮次，多轮用例同一 id 按 turn_index 区分，默认 1 |
| `type` | string | `single` / `multi_turn` |
| `input` | string | 输入（必填） |
| `input_cn` | string | 输入中文 |
| `expected_output` | string | 期望输出 |
| `expected_output_cn` | string | 期望输出中文 |
| `retrieval_context` | string | 检索上下文 |
| `description` | string | 用例描述（对应 AC） |
| `validation` | string | 验证规则（JSON 字符串） |
| `overall_criteria` | string | 全局判定标准 |
| `category_id` | string | 所属分类 ID（默认 `root`） |
| `tags` | list | 标签数组 |
| `assertions` | list | 断言组件绑定 `[{"ref": "AC001", "params": {...}}]` |
| `priority` | string | `P0`/`P1`/`P2` |
| `module` | string | 模块标签 |

### 3.1 列表

```http
GET /api/v1/cases?category_id=cat_84c5e675&limit=20&offset=0
```

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/cases?category_id=cat_84c5e675&limit=2" \
     -H "X-API-Key: $API_KEY"
```

响应：

```json
{
  "total": 245,
  "items": [
    {
      "id": "FAQ_001",
      "turn_index": 1,
      "type": "single",
      "input": "What categories are included in Local Offers?",
      "expected_output": "",
      "category_id": "cat_84c5e675",
      "tags": [],
      "assertions": [],
      "priority": null,
      "module": null
    }
  ]
}
```

### 3.2 编写 → 保存单条

```http
POST /api/v1/cases
```

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/cases" \
     -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "id": "FAQ_001",
       "type": "single",
       "input": "What categories are included in Local Offers?",
       "expected_output": "Local Offers includes dining, wellness and airport services.",
       "category_id": "cat_84c5e675",
       "tags": ["smoke"],
       "priority": "P1"
     }'
```

响应（有 id → 更新；缺省 id → 新建并自动分配）：

```json
{ "ok": true, "id": "FAQ_001", "turn_index": 1 }
```

### 3.3 批量导入 / 更新

```http
POST /api/v1/cases/import
```

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/cases/import" \
     -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "cases": [
         { "id": "FAQ_002", "type": "single", "input": "What types of discounts are available?" },
         { "id": "FAQ_003", "type": "single", "input": "Are Local Offers digital or physical?" }
       ]
     }'
```

响应：

```json
{ "ok": true, "saved": 2, "total": 2 }
```

> 底层使用 PostgreSQL `INSERT ... ON CONFLICT (id, turn_index) DO UPDATE`，同一 id 重复导入会覆盖更新。

### 3.4 批量删除

```http
DELETE /api/v1/cases
```

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/cases" \
     -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{ "ids": ["FAQ_001", "FAQ_002"] }'
```

响应：

```json
{ "ok": true, "deleted": 2 }
```

### 3.5 批量更新（分类 / 优先级 / 模块）

```http
POST /api/v1/cases/bulk-update
```

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/cases/bulk-update" \
     -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{ "ids": ["FAQ_001"], "category_id": "cat_84c5e675", "priority": "P0" }'
```

响应：

```json
{ "ok": true, "updated": 2 }
```

---

## 4. 执行（`/api/v1/jobs`）

执行采用后台 Job 模型：触发后立即返回 `report_id`，agent 用它轮询进度、取消或续跑。

### 4.1 触发执行

```http
POST /api/v1/jobs
```

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/jobs" \
     -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "case_ids": ["FAQ_001", "FAQ_002"],
       "api_name": "Agent Q&A",
       "execution_mode": "full",
       "max_workers": 5,
       "report_name": "smoke-20261019"
     }'
```

响应（`report_id` 即后续查询/操作的 job ID）：

```json
{ "report_id": "20261019120000", "submitted_cases": 2 }
```

| 字段 | 说明 |
|------|------|
| `case_ids` | 用例 ID 列表（多轮用例按 id 整体执行） |
| `api_name` | 目标接口名，取值见「附录 A」 |
| `execution_mode` | `full` / `semantic` / `assertion`，默认 `full` |
| `max_workers` | 并发线程数，默认 5 |
| `report_name` | 报告名称（可选） |

### 4.2 查询进度

```http
GET /api/v1/jobs/{report_id}
```

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/jobs/20261019120000" \
     -H "X-API-Key: $API_KEY"
```

关键字段：

```json
{
  "id": "20261019120000",
  "status": "running",
  "total": 40,
  "started_count": 13,
  "passed": 10,
  "failed": 3,
  "api_name": "Agent Q&A",
  "report_name": "smoke-20261019",
  "execution_mode": "full"
}
```

- `status` 取值：`running` / `completed` / `cancelled` / `interrupted` / `failed`
- 进度 = `started_count / total`

### 4.3 取消

```http
POST /api/v1/jobs/{report_id}/cancel
```

### 4.4 续跑（只跑剩余用例）

```http
POST /api/v1/jobs/{report_id}/continue?max_workers=5
```

响应：

```json
{ "ok": true, "message": "Continue started (27 remaining)", "remaining": 27 }
```

---

## 5. 测试报告（`/api/v1/reports`）

### 5.1 报告列表

```http
GET /api/v1/reports?limit=20&offset=0
```

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/reports?limit=3" \
     -H "X-API-Key: $API_KEY"
```

真实响应示例：

```json
{
  "total": 40,
  "items": [
    {
      "id": "20261016145417",
      "timestamp": "2026-10-16 14:54:17",
      "api_name": "Portal IM (PROD)",
      "report_name": "[q&a][Prod]Smoke_20261016_R2",
      "execution_mode": "full",
      "total": 40,
      "passed": 37,
      "failed": 3,
      "status": "completed",
      "started_count": 40
    }
  ]
}
```

### 5.2 报告详情（含 results）

```http
GET /api/v1/reports/{report_id}
```

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/reports/20261016145417" \
     -H "X-API-Key: $API_KEY"
```

### 5.3 批量删除

```http
DELETE /api/v1/reports
```

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/reports" \
     -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{ "ids": ["20261016145413", "20261016145415"] }'
```

响应：

```json
{ "ok": true, "deleted": 2 }
```

### 5.4 导出到飞书

#### 5.4.1 单个报告导出

```http
POST /api/v1/reports/{report_id}/export/feishu
```

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/reports/20261016145417/export/feishu" \
     -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "feishu_url": "https://xxx.feishu.cn/wiki/QKLQwwM0BixcMjkTZWVc4Wvmnoh?sheet=eRNryN",
       "create_new_sheet": true,
       "sheet_title": "q&a冒烟-20261016"
     }'
```

响应：

```json
{ "success": true, "message": "成功导出 40 条记录到飞书表格", "rows_count": 40 }
```

#### 5.4.2 批量导出（多报告 → 一个/多个文档）

```http
POST /api/v1/reports/export/feishu
```

| `mode` | 含义 |
|--------|------|
| `new_sheet_per_report` | 每个报告在目标文档里**新建一个 sheet**（多报告 → 同一文档） |
| `append_same_sheet` | **追加到同一 sheet**（需在 target 里提供 `sheet_id`） |

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/reports/export/feishu" \
     -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "mode": "new_sheet_per_report",
       "exports": [
         { "report_id": "20261016145417", "feishu_url": "https://xxx.feishu.cn/wiki/AAA" },
         { "report_id": "20261016145415", "feishu_url": "https://xxx.feishu.cn/wiki/AAA" }
       ]
     }'
```

> 给不同 `report_id` 配不同 `feishu_url` 即「导出到多个文档」。

响应：

```json
{
  "results": [
    { "report_id": "20261016145417", "success": true, "message": "成功导出 40 条记录到飞书表格", "rows_count": 40 },
    { "report_id": "20261016145415", "success": true, "message": "成功导出 18 条记录到飞书表格", "rows_count": 18 }
  ]
}
```

---

## 6. 元信息（`/api/v1`）

### 6.1 分类树

```http
GET /api/v1/categories/tree
```

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/categories/tree" \
     -H "X-API-Key: $API_KEY"
```

真实响应（节选）：

```json
[
  {
    "id": "cat_7bbbb089",
    "name": "AI_Lab",
    "level": 1,
    "path": "AI_Lab",
    "children": [
      { "id": "cat_84c5e675", "name": "Supervisor Agent", "level": 2, "path": "AI_Lab/Supervisor Agent", "children": [] }
    ]
  }
]
```

### 6.2 API 配置列表

```http
GET /api/v1/api-configs
```

响应为 `{api_name: {url, description, type, token, request_params}}`，`api_name` 即「触发执行」时的取值。

---

## 附录 A：可用 `api_name`（真实数据，节选）

| api_name | type |
|----------|------|
| `Agent Q&A` | agent_qa |
| `Bundle API` | bundle |
| `DC_Q&A` | dc_qa |
| `Flight API` | flight |
| `Limo API` | limo |
| `Portal IM (PROD)` | portal_im |
| `Portal IM (UAT)` | portal_im |
| `Supervisor Agent` | ai_engineering |
| `Translation` | translation |
| `Trip Planner` | trip_planner |
| `权益(中信)` / `权益(国内）` / `权益(国际）` | entitlements |
| `【UAT】Q&A` 等 `【UAT】*` 系列 | 各类 |

> 完整列表请调用 `GET /api/v1/api-configs` 实时获取。

## 附录 B：错误码约定

| 状态码 | 含义 |
|--------|------|
| `200` | 成功 |
| `400` | 参数错误（缺少必填字段 / 枚举非法 / 空列表） |
| `401` | 缺少或错误的 `X-API-Key` |
| `404` | 目标资源不存在（report / case 未找到） |
| `500` | 服务端异常 |
| `503` | 服务端未配置 `API_KEY` |