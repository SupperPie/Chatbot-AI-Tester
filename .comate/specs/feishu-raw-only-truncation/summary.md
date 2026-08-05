# 飞书导出仅 RAW 截断总结

## 完成内容
按你的要求已完成“仅 RAW 字段截断”：

1. 移除了 `append_rows_to_sheet` 中对所有 cell 的统一截断逻辑。
2. 保留 `export_report_to_feishu` 内 `_truncate_cell`。
3. 截断调用点仅保留在 RAW 列：
   - 多轮：`app/feishu_client.py:247`
   - 单轮：`app/feishu_client.py:272`
4. 其他字段（Input/Expected/Actual/Reason/Thinking/Inform Base 等）不再截断。

## 改动文件
- `app/feishu_client.py`

## 验证结果
- `_truncate_cell` 调用点检查：仅剩 RAW 字段两处。
- 本地长文本验证：
  - RAW 超长（60000 bytes）会截断并追加 ` [...truncated]`
  - 非 RAW 字段保持原样，不被截断

## 最终行为
导出飞书时：
- 只对 RAW 列执行字节截断保护。
- 其余列按原值写入飞书。