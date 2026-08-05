# 飞书导出单元格超长截断设计

## 需求场景
在导出 Test Report 到飞书表格时，出现错误：
- `写入飞书表格失败: cell exceeded 50000 bytes`

目标：
- 导出前如果任意单元格超过 50000 bytes，则自动截断，避免导出失败。

## 现状分析
导出链路如下：
- UI 触发：`app/ui/report.py`
- 导出实现：`app/feishu_client.py:151` 的 `export_report_to_feishu`
- 飞书写入：`app/feishu_client.py:64` 的 `append_rows_to_sheet`

当前代码中：
- `export_report_to_feishu` 内已有 `_truncate_cell`（45000 bytes）用于部分字段。
- 但并非所有 cell 都经过该函数（例如 `input`、`expected`、`assertion_result_str` 等）。
- `append_rows_to_sheet` 作为最终写入点未做统一兜底。

因此仍会出现漏网字段触发 50000 bytes 限制。

## 技术方案
采用“最小改动 + 全局兜底”方案：

### 方案核心
在 `append_rows_to_sheet` 内，对 `rows` 做统一逐 cell 字节截断后再发请求。

### 截断规则
- 按 UTF-8 字节长度判断。
- 若 cell 字节数 `> 50000`，截断到安全值（建议 49000，留出 API/编码余量）。
- 截断后追加后缀：` [...truncated]`。
- 非字符串值先转字符串再判断（`None` 保持为空字符串）。

### 预期效果
- 不论上游是否遗漏 `_truncate_cell`，写入前都不会带着超长 cell 发到飞书。
- 解决导出失败问题。
- 对现有导出行为影响最小。

## 影响范围
主要修改文件：
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/feishu_client.py`

预期改动点：
1. 在 `append_rows_to_sheet` 增加统一 cell 截断函数（或复用同名函数）。
2. 在构造 payload 前，对 `rows` 进行一次全量 sanitize。

可选增强（保持小改优先）：
- 将 `export_report_to_feishu` 内部局部 `_truncate_cell` 迁移为模块级复用函数，避免重复逻辑。

## 边界条件与异常处理
- 多字节字符（中文/emoji）截断时按字节切片后用 `errors='ignore'` 保证 UTF-8 合法。
- 数值、布尔值、字典、列表：统一 `str()` 后截断。
- 空值：保留空字符串，避免写入 `None`。

## 验证方式
- 构造超长 `raw` / `thinking` / `input` 字段（>50000 bytes）。
- 调用导出逻辑，确认不再报 `cell exceeded 50000 bytes`。
- 抽查导出的被截断单元格包含 ` [...truncated]` 标记。

## 预期结果
- 导出 Test Report 到飞书稳定成功。
- 单个 cell 超长自动截断，不再导致整次导出失败。