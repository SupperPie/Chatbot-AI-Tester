# Testcases UI Micro Polish

## 需求场景与目标
本次仅做 `Testcases Management` 页面的轻量交互与文案微调，覆盖 6 项：
1. 浏览器页签图标改为可爱机器人风格（偏 Eva 形象）。
2. `Import` 与 `参数说明手册` 同行显示。
3. `Run Selected` 与 `Run Range` 下移到标签下方
4. 文案 `筛选条件` 改为 `Filter`。
5. 文案 `Configuration & Management` 改为 `Management`。
6. `Select All`、`Cancel All` 按钮样式改为与 `Run Selected` 一致，换个颜色。
7.表格中checkbox 列还是不支持整页勾选，如果组件本身不支持，那还是加个button吧
8.去到testcase 页面报错
UnboundLocalError: local variable 'filter_tags' referenced before assignment

File "/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/streamlit_app.py", line 56, in <module>
    main()
File "/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/streamlit_app.py", line 46, in main
    render_testcases_page()
File "/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/testcases.py", line 535, in render_testcases_page
    tags=filter_tags, 

同时保持现有功能不回归：分类筛选、分页、批量选择、执行逻辑正常。

---

## 当前问题分析

### 1) 页签 icon 缺失
- 当前在 `streamlit_app.py` 中已有：
  - `st.set_page_config(..., page_icon="img/eva_avatar.png")`
- 在浏览器页签中图标未显示，通常是文件路径解析/浏览器缓存/favicon兼容问题。
- 稳定方案：使用 emoji 页签图标（`🤖`）保证各环境显示一致。

### 2) 顶部控件未在一行
- `testcases.py` 顶部“参数说明手册”位于 title 右侧；`Import` 位于管理区另一行。
- 需要将两者并排同一行，避免上下跳动。

### 3) 执行按钮占用额外行
- 当前 `Run Selected`、`Run Range` 与筛选控件不在最紧凑布局。
- 需要挪到标签下方紧凑排列。

### 4) 文案统一
- `筛选条件` 与 `Configuration & Management` 需要改成英语指定词。

### 5) Select/Clear按钮视觉一致性
- 现有 `Select All` / `Cancel All` 与主操作按钮视觉不一致。
- 需要改为与 `Run Selected` 同视觉等级（primary 样式）。

---

## 技术方案

### A. 页签 icon
- 文件：`/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/streamlit_app.py`
- 修改点：
  - 将 `page_icon="img/eva_avatar.png"` 改为 `page_icon="🤖"`。
- 说明：不依赖静态资源路径，稳定、可跨环境显示。

### B. 顶部布局重排（Import + 参数说明手册同一行）
- 文件：`/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/testcases.py`
- 修改点：
  - 调整顶部列布局，把 `参数说明手册` 按钮放进管理区右侧与 `Import` 同一行。
  - 或将 `Import` 从管理区抽出到标题行右侧，与 `参数说明手册` 同列区域并列。
- 采用最小入侵：复用现有 popover，不改其内部逻辑。

### C. 执行按钮位置调整
- 文件：`app/ui/testcases.py`
- 修改点：
  - 将 `Run Selected`、`Run Range` 放置到标签筛选控件下一行（同区域内）。
  - 保持触发变量与执行逻辑不变，仅改布局位置。

### D. 文案替换
- 文件：`app/ui/testcases.py`
- 修改点：
  - `#### 🔍 筛选条件` -> `#### 🔍 Filter`
  - `#### ⚙️ Configuration & Management` -> `#### ⚙️ Management`

### E. Select All / Cancel All 样式统一
- 文件：`app/ui/testcases.py`
- 修改点：
  - 对 `Select All`、`Cancel All` 按钮设为与 `Run Selected` 一致的主样式（`type="primary"`）。
  - 文案统一为 `Select All` / `Cancel All`（大小写一致）。

---

## 影响文件
1. `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/streamlit_app.py`
2. `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/testcases.py`

---

## 边界条件与兼容性
- 不修改后端数据结构。
- 不改批量执行、筛选、分页核心业务逻辑。
- 仅做 UI 布局与文案微调。
- 如果按钮挪位涉及变量作用域，确保 `run_selected_clicked`、`run_range_clicked`、`run_tags_clicked` 在执行逻辑前已定义。

---

## 预期结果
1. 页签显示机器人 icon（🤖）。
2. `Import` 与 `参数说明手册` 同行。
3. `Run Selected` 和 `Run Range` 位于标签下方，减少一行占用。
4. 标题文案变更为：`Filter`、`Management`。
5. `Select All`、`Cancel All` 与 `Run Selected` 视觉样式一致。
