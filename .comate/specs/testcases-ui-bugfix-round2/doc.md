# Testcases UI Bugfix Round 2

## 目标
修复当前页面中用户反馈的 3 个问题：
1. 顶部 `参数说明手册 + Import` 显示不完整（截断/宽度不足）。
2. 选中目录树中“全部用例(637)”节点时，表格仍显示 707 条（过滤失效）。
3. 全页面按钮风格统一，但使用低饱和度的不同颜色区分功能组。

---

## 问题分析

### A) 顶部右侧控件显示不完整
- 现状：`参数手册` 和 `Import` 放在顶层三列的右两列，但这两列宽度不足，导致文本截断。
- 影响：可用性下降、视觉错位。
- 修复方向：
  - 调整标题区列宽比例；
  - 按钮文案改短（必要时）；
  - 使用同一行但更稳健的紧凑布局，避免换行与裁剪。

### A.1) 页签 icon 资源确定
- 用户已确认：先使用项目内现有图片 `img/eva_avatar.png` 作为页签 icon。
- 兼容要求：保留 fallback 方案（图片异常时回退 `🤖`）。

### B) 目录节点过滤失效（637节点仍显示707）
- 现状：目录树选中子节点后，表格表现为 root 全量。
- 已知风险点：
  - `category_widget._render_tree` 使用 `return_index` 映射，根节点与业务节点映射可能偏移；
  - `filter_test_cases` 依赖 `selected_category`，若 session 未更新或映射错误会直接走全量。
- 修复方向：
  - 将树选择返回改为基于节点 `tag`（category_id）而不是 index；
  - 统一以 `st.session_state.selected_category` 为单一数据源；
  - 增加最小日志，验证筛选输入与输出数量。

### C) 按钮风格统一但分组差异化
- 现状：部分按钮依赖 `type="primary"`，其余按钮保留默认，视觉体系不统一。
- 修复方向：
  - 在 `app/ui/styles.py` 中定义统一按钮基线（圆角、阴影、字体）。
  - 通过稳定选择器按功能组着色（低饱和配色）：
    - Run 组（浅金/浅橙）
    - Select 组（浅蓝/浅青）
    - Danger 组（浅红）
    - Utility（灰蓝）
  - 不依赖脆弱的列序号选择器（避免布局变化导致样式错位）。

---

## 影响文件
1. `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/testcases.py`
2. `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/components/category_widget.py`
3. `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/styles.py`

---

## 实现细节（示意）

### 1) 顶部控件布局
- `testcases.py` 顶部列从 `[6.5,1.4,1.3]` 调整为更可读比例，如 `[6.2,1.9,1.9]`。
- 手册按钮文案可简化为 `参数手册`，Import保留 `Import`。

### 2) 树选择返回 category_id
- `category_widget.py`：
  - `sac.TreeItem(..., tag=node['id'])`
  - `sac.tree(..., return_index=False)`
  - 直接读取返回 tag 作为 `selected_category`。
- 避免 index 映射偏移导致的“选中节点不等于实际筛选节点”。

### 3) 按钮风格统一
- `styles.py`：
  - 统一 `.stButton button` 基础样式；
  - 给关键按钮加稳定 data-testid / key 对应选择器（基于 key 关联容器）
  - 采用低饱和配色，避免高对比刺眼。

---

## 边界条件
- root 节点仍显示全量（707）。
- “全部用例(637)”等业务目录节点仅显示该节点范围。
- 不改变后端数据结构与 category 关系模型。
- 不改执行逻辑（Run Selected / Run Range）语义。

---

## 预期结果
1. 页签 icon 使用 `img/eva_avatar.png`（异常时回退 🤖）。
2. 参数手册与 Import 在右上角完整显示，不截断。
3. 选中“全部用例(637)”时表格显示 637 条（或该节点实际数量），不再是707全量。
4. 页面按钮风格统一，分组颜色区分清晰且低饱和。