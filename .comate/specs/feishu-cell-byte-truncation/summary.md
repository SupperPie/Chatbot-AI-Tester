# 飞书导出单元格超长截断总结

## 已完成改动
- 修改文件：`app/feishu_client.py`
- 修改函数：`FeishuClient.append_rows_to_sheet`
- 核心改动：在写入飞书前统一对 `rows` 做逐 cell 字节截断处理（全局兜底）

## 具体实现
- 阈值：`MAX_CELL_BYTES = 50000`
- 安全截断：`SAFE_CELL_BYTES = 49000`
- 处理规则：
  - `None` -> `""`
  - 非字符串 -> `str(cell)`
  - 超长 UTF-8 字节内容 -> 截断并追加 `" [...truncated]"`
  - 截断解码使用 `errors='ignore'`，避免多字节字符损坏
- 生效范围：
  - 所有通过 `append_rows_to_sheet` 写入飞书的数据（包含表头写入与数据行写入）

## 验证结果
本地验证脚本结果：
- `None` 成功转为空字符串
- `int`/`bool` 成功转字符串并保留值语义
- 短文本保持不变
- 长文本（约 90000 bytes）被截断到约 49014 bytes 并带 ` [...truncated]` 后缀

## 影响与收益
- 解决导出报错：`cell exceeded 50000 bytes`
- 即使上游字段遗漏局部截断，也会在最终写入前被统一兜底
- 对正常长度 cell 无行为变化