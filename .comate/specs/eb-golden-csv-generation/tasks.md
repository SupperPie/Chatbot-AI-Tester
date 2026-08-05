# EB Golden CSV 生成任务计划
- [x] Task 1: 实现 Excel 到英文单条输入的数据抽取脚本
    - 1.1: 使用 pandas 读取 `Eleva_MVP_User_Testing_Plan_v1 - Copia.xlsx` 的三个 sheet
    - 1.2: 建立列名映射，兼容 `Expected result / Acceptance criteria` 与 `Expected Result / Acceptance Criteria`
    - 1.3: 过滤无效行（无 Test ID 或关键文本为空）
    - 1.4: 按规则生成 `input`（每个有效 Test ID 仅一条、仅保留英文）
    - 1.5: 生成 `retrieval_context`（优先 Expected，空则回退 Feature + Steps）
    - 1.6: 组装输出字段 `input,retrieval_context,expected_output`（expected_output 置空）

- [x] Task 2: 生成 EB_Golden CSV 文件产物
    - 2.1: 创建输出目录 `data/EB_Golden/`
    - 2.2: 导出 `product_test_cases_eb_golden.csv`
    - 2.3: 导出 `offline_services_eb_golden.csv`
    - 2.4: 导出 `human_escalation_eb_golden.csv`
    - 2.5: 导出合并文件 `eb_golden_all.csv`

- [x] Task 3: 校验 CSV 质量与覆盖
    - 3.1: 校验所有 CSV 字段顺序与格式一致
    - 3.2: 校验 `expected_output` 全为空
    - 3.3: 校验 `input` 为英文优先且每个有效 Test ID 仅对应一条记录
    - 3.4: 统计各 sheet 产出数量与总数量，确认覆盖有效测试项
    - 3.5: 抽样检查特殊行（EN/PT 混合、空字段回退场景）

- [x] Task 4: 交付与总结
    - 4.1: 更新任务勾选状态
    - 4.2: 生成 `.comate/specs/eb-golden-csv-generation/summary.md`
    - 4.3: 在 summary 中记录每个 sheet 的最终条数与处理说明
