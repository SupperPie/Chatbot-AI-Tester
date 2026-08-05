# 飞书导出单元格超长截断任务计划
- [x] Task 1: 在飞书写入出口增加统一单元格字节截断
    - 1.1: 打开 `app/feishu_client.py` 的 `append_rows_to_sheet` 方法
    - 1.2: 新增按 UTF-8 字节长度截断的辅助函数（阈值 50000 bytes，安全截断值 49000 bytes）
    - 1.3: 在构造 payload 前对 `rows` 逐行逐 cell 执行 sanitize（超长截断）
    - 1.4: 保证多字节字符截断后字符串合法（`errors='ignore'`）

- [x] Task 2: 统一处理不同类型 cell 的输入
    - 2.1: `None` 转为空字符串
    - 2.2: 非字符串（数字/布尔/对象）转 `str()` 后再做字节判断
    - 2.3: 截断后追加标记 ` [...truncated]`

- [x] Task 3: 保持现有导出逻辑兼容并验证
    - 3.1: 确认 `export_report_to_feishu` 现有字段构造逻辑不变
    - 3.2: 构造超长 cell 的本地样例，验证不会再触发 `cell exceeded 50000 bytes`
    - 3.3: 校验正常长度内容不受影响

- [x] Task 4: 收尾与记录
    - 4.1: 更新 `tasks.md` 勾选状态
    - 4.2: 生成 `.comate/specs/feishu-cell-byte-truncation/summary.md`
    - 4.3: 在 summary 记录改动点、阈值策略和验证结果
