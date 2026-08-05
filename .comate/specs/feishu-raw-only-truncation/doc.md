# 飞书导出仅 RAW 字段截断设计

## 需求背景
当前实现是在 `append_rows_to_sheet` 对所有 cell 做统一字节截断。
你新要求是：**只处理 RAW 字段超长截断，其他字段不截断**。

## 需求场景与逻辑
- 目标错误：`cell exceeded 50000 bytes`
- 只对导出列中的 `Raw` 列执行字节截断。
- 其他列（Input/Expected/Reason/Thinking 等）保持原样，不做全局截断。

## 技术方案

### 改动范围
- 文件：`/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/feishu_client.py`
- 函数：
  - `FeishuClient.append_rows_to_sheet`（移除全 cell 兜底截断）
  - `export_report_to_feishu`（仅在 Raw 列赋值处截断）

### 实施方式
1. 删除 `append_rows_to_sheet` 里对 `rows` 的逐 cell sanitize。
2. 在 `export_report_to_feishu` 保留/复用 `_truncate_cell`，并**仅用于 Raw 字段**：
   - 多轮：`_truncate_cell(str(turn.get("raw", "")))`
   - 单轮：`_truncate_cell(str(item.get("raw", "")))`
3. 其他字段全部改为不调用 `_truncate_cell`。

## 影响函数与字段
- 多轮 row 构造（`app/feishu_client.py` 中 `item.get("type") == "multi_turn"` 分支）
- 单轮 row 构造（else 分支）
- 仅第 16 列 `Raw` 字段进行截断。

## 边界条件
- `raw` 为 `None`：写空字符串。
- `raw` 为 dict/list：先 `str()` 再按 UTF-8 字节截断。
- 多字节字符：`errors='ignore'` 保证截断后合法。

## 预期结果
- RAW 超长时不会触发飞书单元格超限。
- 非 RAW 列保持完整原值（不再被统一截断）。