# Testcases UI 微调与稳定性修复任务清单

- [x] Task 1: 修复 testcases 页面运行时异常并稳定筛选变量初始化
    - 1.1: 在 `app/ui/testcases.py` 中修复 `filter_tags` 未定义即被引用的问题
    - 1.2: 校验 `filter_tags`、`filter_id_from`、`filter_id_to`、`filter_keyword` 的定义顺序，确保在 `filter_test_cases(...)` 调用前完成赋值
    - 1.3: 复核节点切换与 rerun 流程中变量作用域，避免再次出现 `UnboundLocalError`

- [x] Task 2: 调整页签图标与顶部布局
    - 2.1: 修改 `streamlit_app.py` 的 `st.set_page_config`，将页签 icon 调整为机器人风格（🤖）
    - 2.2: 在 `app/ui/testcases.py` 中将 `Import` 与 `参数说明手册` 调整为同一行展示
    - 2.3: 保持 `Import` 与手册交互逻辑不回归（popover 内容与上传逻辑不变）

- [x] Task 3: 调整管理区与筛选区文案和按钮位置
    - 3.1: 将 `Configuration & Management` 文案改为 `Management`
    - 3.2: 将 `筛选条件` 文案改为 `Filter`
    - 3.3: 将 `Run Selected` 与 `Run Range` 移动到标签 dropdown 下方
    - 3.4: 校验按钮移动后执行逻辑仍使用正确状态变量

- [x] Task 4: 调整全选交互语义与样式
    - 4.1: 将 `Select All` 与 `Cancel All` 样式调整为主操作按钮风格（与 Run 按钮同视觉等级，并应用目标颜色）
    - 4.2: 保留 `Select All` 的跨页全选语义
    - 4.3: 增加“当前页全选”按钮作为 checkbox header 能力不足时的兜底方案
    - 4.4: 确保“当前页全选”仅影响当前分页数据，“Select All”影响当前筛选结果全集

- [x] Task 5: 回归验证与结果收敛
    - 5.1: 验证页面可正常打开，不再出现 `filter_tags` 未定义异常
    - 5.2: 验证页签 icon、文案、布局调整符合预期
    - 5.3: 验证跨页全选、当前页全选、取消全选三种行为正确
    - 5.4: 验证节点切换、筛选、执行按钮行为无回归
