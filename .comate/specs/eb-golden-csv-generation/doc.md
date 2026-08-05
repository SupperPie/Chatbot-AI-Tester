# EB Golden 测试用例 CSV 生成设计

## 需求场景与处理逻辑
你提供了 `Eleva_MVP_User_Testing_Plan_v1 - Copia.xlsx`（3 个 sheet），希望基于该手册生成可导入测试库的 CSV，用于 EB_Golden。你已说明：
- 不直接写数据库
- 生成 CSV 文件
- `expected_output` 先置空
- 仅使用 `input` 与 `retrieval_context` 作为核心内容

因此方案采用：**从 Excel 自动抽取 → 生成标准化 CSV（expected_output 为空） → 放入 `data/EB_Golden/`**。

---

## 覆盖策略（每个 sheet 生成多少）
目标是“覆盖手册内容”，采用“**有效行全覆盖（不做示例拆分）**”规则。

### 覆盖规则
1. 仅处理有 `Test ID` 且存在有效文本的行；空白占位行跳过。
2. 不进行编号示例拆分（`1) / 2) / 3)` 不拆分）。
3. 不进行 EN/PT 语言拆分，统一只保留英文输入。
4. `retrieval_context` 来自该行 `Expected result / Acceptance criteria`（或同义列）。
5. `expected_output` 固定空字符串。

### 预计产出量（按当前表结构）
- **Product Test Cases**：预计约 **74 条**（每个有效 Test ID 一条）。
- **Offline Services Test Cases**：有效内容约 **11 条**。
- **Human Escalation Tests**：预计约 **17 条**（每个有效 Test ID 一条）。

> 最终条数以“过滤无效行后的实际统计”为准，并在 summary.md 给出精确计数（每 sheet 与总计）。

---

## 技术方案

### 方案概览
使用 `pandas` 读取 Excel 三个 sheet，按统一解析器输出三份 CSV（每 sheet 一份）+ 一份合并 CSV。

### 产物路径
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/data/EB_Golden/product_test_cases_eb_golden.csv`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/data/EB_Golden/offline_services_eb_golden.csv`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/data/EB_Golden/human_escalation_eb_golden.csv`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/data/EB_Golden/eb_golden_all.csv`

### CSV 字段定义
输出字段固定为：
- `input`
- `retrieval_context`
- `expected_output`（空）

说明：虽然你强调只用 `input` 与 `retrieval_context`，但保留空 `expected_output` 字段便于后续直接导入系统（系统通常要求该字段存在）。

---

## 实现细节

### 1) 行过滤与归一化
- 识别各 sheet 的列名差异（例如 `Expected result / Acceptance criteria` vs `Expected Result / Acceptance Criteria`）。
- 过滤无效行：`Test ID` 为空且关键文本字段为空。
- 清洗文本：去除重复空白、换行统一。

### 2) 输入生成策略（英文单条）
- 每个有效 Test ID 仅生成 1 条 `input`。
- 优先取英文内容（`Test data / inputs` 或 `Steps` 中的英文句子）。
- 若同一单元格含 EN/PT 混合内容，仅保留 EN 段落。
- 不进行编号示例拆分，也不进行多语言拆分。

### 3) retrieval_context 生成
- 优先取 `Expected result / Acceptance criteria`。
- 若为空，则回退到 `Feature + Steps` 拼接，保证 `retrieval_context` 非空且可读。

### 4) 去重与质量控制
- 按 `input + retrieval_context` 去重。
- 去掉明显无语义占位文本。
- 保留语言标签信息到输入正文（若是 EN/PT 场景）。

---

## 数据流
1. 读取 Excel（三个 sheet）
2. 逐行解析有效测试项
3. 每个有效 Test ID 生成 1 条英文输入（不拆分）
4. 组装为 `input/retrieval_context/expected_output`
5. 每 sheet 导出 CSV
6. 合并导出总 CSV
7. 输出统计（总数、每 sheet 数）

---

## 边界条件与异常处理
- 列名不一致：建立列名映射后再读取。
- 行内容为空：自动跳过。
- 输入中仅有 PT 无 EN：回退 `Steps` 或 `Feature` 的英文文本。
- 英文文本缺失：保留可读原文并标记到 summary 统计。
- 特殊字符（引号、换行）：交给 CSV 转义机制处理。

---

## 受影响文件
- 新增目录（数据产物）：
  - `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/data/EB_Golden/`（CSV 输出）
- 可能复用现有参考文件（只读）：
  - `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/docs/import_template.csv`

> 不改动业务运行代码（`app/` 下 Python 代码不修改），只产出 CSV 数据文件。

---

## 预期结果
- 你将拿到可直接查看/导入的 EB_Golden CSV 文件。
- 每个 sheet 都有独立文件 + 全量合并文件。
- `expected_output` 全为空，满足你“先不写 expected”的要求。
- 覆盖范围透明：在 summary 中给出每个 sheet 的覆盖与拆分统计。