# Category Tree Selection Consistency 修复任务清单

- [x] Task 1: 修复目录树选中状态同步链路
    - 1.1: 调整 `app/ui/components/category_widget.py` 中 `_render_tree` 的选中值解析逻辑，避免空返回时回退到 root
    - 1.2: 确保 `_render_tree` 仅在收到合法新选中值时更新 `st.session_state.selected_category`
    - 1.3: 校正 `sac.tree` 的初始选中绑定逻辑（index/tag 与当前选中节点一致）
    - 1.4: 保证切换节点时触发 `st.rerun()`，并在 rerun 后保持选中状态稳定

- [x] Task 2: 修复表格按目录过滤刷新逻辑
    - 2.1: 校验 `app/ui/testcases.py` 中 `selected_category -> filter_category -> filter_test_cases` 数据流
    - 2.2: 修复目录筛选异常静默吞错问题，将 `except: pass` 改为可观测日志
    - 2.3: 验证非 root 节点筛选结果仅包含该节点（含子节点）测试用例
    - 2.4: 验证 root 节点仍显示全部测试用例

- [x] Task 3: 修复新建目录父级上下文读取逻辑
    - 3.1: 调整 `render_category_widget` 中“新建目录”按钮的父目录取值来源，统一读取当前选中节点
    - 3.2: 修复 `add_category_parent_id` 在 root 与非 root 场景下的赋值分支
    - 3.3: 验证“机场礼遇”选中后新建目录弹窗显示 `父目录: 机场礼遇`
    - 3.4: 验证 root 选中时弹窗显示“将创建顶级目录”

- [x] Task 4: 回归验证与稳定性检查
    - 4.1: 手工回归切换多个层级节点，确认表格内容实时变化
    - 4.2: 手工回归目录管理动作（新建/重命名/删除）对选中状态的影响
    - 4.3: 检查日志输出，确认目录筛选异常路径可追踪
    - 4.4: 整理修复结果并确认满足验收标准
