# 统一用例统计口径与报告字段对齐方案（upcoming-update-preparation）

## 需求场景与处理逻辑

本次更新聚焦 4 个问题：

1. **统计口径不统一**：当前部分页面按“行（turn）”统计，部分按“用例（testcase id）”统计，导致多轮场景下总数不一致，甚至出现通过率异常（>100%）。
2. **Test Case 与 Test Report 列不对齐**：需要梳理“Test Case 页面列、导入列、Report 页面列”之间的来源与映射，形成一致规则。
3. **新增 `Actual_Output_CN`**：在有多语言输出时，将非中文输出翻译后写入该字段。
4. **Run 时 report name 弹窗确认后未自动关闭**：修复确认后关闭与状态清理行为。

核心目标：**所有统计统一以 testcase id 为唯一单位**，并保证页面展示、导入、落库、报告计算口径一致。

---

## 架构与技术方案

### A. 统计口径统一（testcase id）

#### 现状（已定位）
- TestCases 页面顶部统计当前为 `len(df)` / `len(filtered_df)`，属于按行统计。
- 目录树计数当前 `count(TestCase.id)`，注释说明包含多轮每个 turn。
- Report 页通过率展示依赖 `history.total/passed`，而这些值来自执行链路，链路中有按 case_id 去重也有按结果行计数，存在语义混用风险。

#### 方案
- 定义统一指标：
  - `total_cases = n_unique(testcase_id)`
  - `passed_cases = n_unique(testcase_id where passed=True)`
  - `failed_cases = total_cases - passed_cases`
  - `pass_rate = passed_cases / total_cases`
- UI 层所有“总数/筛选数/执行数/通过率”统一调用同一统计函数（服务层输出），禁止页面内直接 `len(df)` 作为业务统计口径。
- 对多轮用例：同一个 testcase id 的多 turn 在统计中只计 1 个 case。

---

### B. TestCase/Report 列对齐治理

#### 现状（已定位）
- TestCases 列定义在 `app/ui/testcases.py` 的 `st.data_editor(... column_config=...)`。
- 导入校验当前必填列仅 `input/expected_output`，模板在 `docs/import_template.csv`。
- Report 列定义在 `app/ui/report.py` 的 `column_config + target_cols`，并在多轮展示时做字段重映射。

#### 方案
- 先产出“字段矩阵”（三视图）：
  - TestCase 页面显示字段（编辑态）
  - 导入支持字段（CSV/JSON）
  - Report 页面显示字段（只读态）
- 将每个字段标注：
  - 来源（test_cases / test_results / 运行时派生）
  - 读写属性（可编辑/导入可写/运行生成）
  - 是否必填
- 按字段职责分层：
  - **用例定义字段**（input/expected_output/description/priority/module/...）
  - **执行结果字段**（actual_output/passed/score/reason/latency/...）
  - **业务关键字段**：`turn_index`（用于多轮排序、分组映射、去重与更新定位；在 tester / testcases / report 三处均参与业务逻辑，不归类为纯展示字段）
  - **展示辅助字段**：不保留（`progress` / `duration` / `status_tag` 不纳入本次字段治理范围）

> 本轮先完成“出处梳理+规则设计”，具体取舍（哪些列应出现在 Report）会在 tasks 执行前再与你逐项确认。

---

### C. 新增 `Actual_Output_CN`

#### 可行性评估
- 技术上可做，复杂度中等：
  - 需要在结果生成链路加入“语言检测+翻译”步骤；
  - 需要确定翻译引擎（现有 API / 独立翻译服务 / 本地模型）；
  - 需要考虑成本与失败回退。

#### 方案
- 在结果落库前处理：
  1. 若 `actual_output` 判定为中文，`actual_output_cn = actual_output`；
  2. 若非中文，调用翻译服务得到中文；
  3. 翻译失败时：`actual_output_cn` 置空并记录错误日志，不影响主流程通过/失败判定。
- 数据层：
  - 在 `test_results` 增加 `actual_output_cn` 字段（迁移 + ORM + service 输出 + report 展示可选列）。

---

### D. report name 弹窗确认后关闭

#### 现状（已定位）
- Run 的三个入口统一调用 `run_confirm_dialog(...)`。
- 对话框内确认/取消都触发 `st.rerun()`，理论上应关闭；当前出现“确认后不关闭”，推测与 session_state 消费顺序/二次触发路径有关。

#### 方案
- 调整对话框状态机为单次消费：
  - 点击 Confirm：仅设置一次 `confirmed_run` + `st.rerun()`；
  - 主流程读取并消费后立即清理状态（包括 report_name 临时态），防止 rerun 后再次命中 dialog 条件。
- 为三个入口统一封装“触发 -> 确认 -> 消费 -> 清理”的顺序，避免路径差异。

---

## 影响文件（预估）

### 页面层
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/testcases.py`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/report.py`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/tester.py`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/components/category_widget.py`

### 执行与任务层
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/test_engine.py`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/job_manager.py`

### 数据层
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/models/test_result.py`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/services/history_service.py`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/services/test_case_service.py`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/docs/import_template.csv`
- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/scripts/`（若需新增 migration）

---

## 实现细节（关键逻辑）

### 1) 统一统计函数（示意）

```python
def calc_case_metrics(df):
    case_ids = df["id"].dropna().astype(str)
    total_cases = case_ids.nunique()
    # passed_ids 来自执行结果聚合（同 id 多行只计一次）
    return {
        "total": total_cases,
        "passed": passed_cases,
        "failed": total_cases - passed_cases,
        "pass_rate": 0 if total_cases == 0 else passed_cases / total_cases,
    }
```

### 2) 列矩阵规则（示意）

```text
字段 | TestCase显示 | 导入支持 | Report显示 | 数据来源 | 备注
id | Y | Y(可选) | Y | test_cases / test_results.case_id | 统一主键语义
input | Y | Y(必填) | Y | test_cases / turns.user | 用例输入
expected_output | Y | Y(必填) | Y | test_cases / turns.expected | 期望输出
actual_output | N | N | Y | test_results | 执行生成
actual_output_cn | N | N | Y(可选) | test_results(翻译生成) | 新增字段
```

### 3) 弹窗状态机（示意）

```python
if confirm_clicked:
    st.session_state["confirmed_run"] = payload
    st.rerun()

confirmed = st.session_state.pop("confirmed_run", None)
if confirmed:
    start_job(confirmed)
    clear_run_dialog_state()
```

---

## 边界条件与异常处理

1. testcase id 为空或异常格式时，统计需跳过空值并打日志。
2. 多轮数据缺少 turn_index 时，不影响按 id 统计，但在展示层保留告警。
3. 翻译服务不可用时，不阻断测试执行；`actual_output_cn` 允许为空。
4. report 历史老数据无 `actual_output_cn` 时，UI 回退显示空值。

---

## 数据流路径

1. TestCases/Tester 读取用例 -> 统一按 `id` 聚合统计。
2. 触发执行 -> test_engine/job_manager 产出结果并按 case 维度维护统计。
3. history_service 输出 report 数据 -> report 页面按统一字段矩阵渲染。
4. 若启用翻译 -> actual_output 写入后派生 actual_output_cn 并落库。

---

## 预期结果

- 全平台统计口径统一为 testcase id。
- 多轮场景下各页面总数一致，通过率不再出现异常口径。
- TestCase/导入/Report 字段关系明确并可持续维护。
- Run report name 弹窗确认后行为稳定，自动关闭。
- `Actual_Output_CN` 具备可落地方案（是否启用可配置）。

---

## 待你确认

如果这版需求理解正确，我下一步会基于它生成 `tasks.md`，把工作拆成可执行任务并逐条落地。