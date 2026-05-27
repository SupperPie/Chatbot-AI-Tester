# 多轮对话评分机制升级任务

> **注意**: 本次修改仅涉及 `run_multi_turn_case` 方法，单轮对话的 `run_case` 方法保持不变。

- [x] Task 1: 新增 deepeval 多轮对话相关导入
    - 1.1: 导入 ConversationalTestCase 和 Turn
    - 1.2: 导入 ConversationalGEval 指标
    - 1.3: 添加导入失败的兼容处理（不影响现有单轮功能）

- [x] Task 2: 初始化 ConversationalGEval 指标
    - 2.1: 在 TestEngine.__init__ 中添加 conversational_metric 属性
    - 2.2: 配置 criteria 和 threshold
    - 2.3: 添加初始化失败的异常处理（失败时 conversational_metric=None）

- [x] Task 3: 重构 run_multi_turn_case 方法（不修改 run_case）
    - 3.1: 修改 API 调用循环，遇到错误直接 break 并记录
    - 3.2: 添加错误检测后直接返回的逻辑
    - 3.3: 构建 Turn 列表和 ConversationalTestCase
    - 3.4: 调用 ConversationalGEval 进行整体评分
    - 3.5: 移除单轮评分逻辑，保留基础数据记录
    - 3.6: 更新返回结果结构，保持与现有报告页面兼容
