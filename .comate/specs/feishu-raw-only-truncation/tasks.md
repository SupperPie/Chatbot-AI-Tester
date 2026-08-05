# 飞书导出仅 RAW 字段截断任务计划
- [x] Task 1: 移除写入出口的全量 cell 截断逻辑
    - 1.1: 打开 `app/feishu_client.py` 的 `append_rows_to_sheet`
    - 1.2: 删除对 `rows` 逐 cell sanitize 的统一截断代码
    - 1.3: 恢复 payload 直接使用 `rows` 写入

- [x] Task 2: 将截断范围收敛到 RAW 列
    - 2.1: 保留 `_truncate_cell` 辅助函数
    - 2.2: 多轮导出中仅对 `turn.raw` 使用 `_truncate_cell`
    - 2.3: 单轮导出中仅对 `item.raw` 使用 `_truncate_cell`
    - 2.4: 其他字段（Input/Expected/Reason/Thinking/Inform Base 等）不再调用 `_truncate_cell`

- [x] Task 3: 验证行为符合 RAW-only 规则
    - 3.1: 检查代码中 `_truncate_cell` 调用点仅剩 RAW 列
    - 3.2: 本地构造超长 RAW 文本验证会被截断
    - 3.3: 本地确认非 RAW 字段不会被统一截断

- [x] Task 4: 收尾记录
    - 4.1: 更新 `tasks.md` 勾选状态
    - 4.2: 生成 `.comate/specs/feishu-raw-only-truncation/summary.md`
    - 4.3: 在 summary 记录“仅 RAW 截断”的最终行为与验证结果
