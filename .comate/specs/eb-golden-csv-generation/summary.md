# EB Golden CSV 生成结果总结

## 完成情况
已按确认后的规则完成全部任务：
- 每个有效 Test ID 仅生成 1 条记录
- 不做编号拆分
- 不做 EN/PT 拆分，仅保留英文优先
- 输出字段固定为 `input,retrieval_context,expected_output`
- `expected_output` 全为空

## 产物文件
- `data/EB_Golden/product_test_cases_eb_golden.csv`
- `data/EB_Golden/offline_services_eb_golden.csv`
- `data/EB_Golden/human_escalation_eb_golden.csv`
- `data/EB_Golden/eb_golden_all.csv`

## 覆盖统计
- Product Test Cases：
  - 有效 Test ID：74
  - 生成条数：74
- Offline Services Test Cases：
  - 有效 Test ID：11
  - 生成条数：11
- Human Escalation Tests：
  - 有效 Test ID：16（该 sheet 第 1 行为说明文本，第 2 行为表头，从第 3 行开始为数据）
  - 生成条数：16
- 合并总数：101

## 质量校验结果
- 所有 CSV 列顺序一致：`input,retrieval_context,expected_output`
- `expected_output` 为空：101/101
- `input` 非空：101/101
- `retrieval_context` 非空：101/101

## 说明
- 本次按你要求采用“英文单条”策略：每个有效 Test ID 一条，不拆分示例编号和多语言。
- 对于含 EN/PT 的输入，优先保留 EN 内容；若 EN 缺失，则回退到 `Steps` 或 `Feature` 的英文文本。