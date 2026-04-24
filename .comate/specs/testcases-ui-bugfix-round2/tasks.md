# Testcases UI Bugfix Round 2 任务清单

- [x] Task 1: 修复顶部右上角控件显示不完整
    - 1.1: 调整 `app/ui/testcases.py` 顶部标题区列宽，确保参数手册与 Import 完整显示
    - 1.2: 保持“参数手册”在原顶部位置，Import 与其同一行对齐
    - 1.3: 验证参数手册与 Import 在常见窗口宽度下不换行、不截断

- [x] Task 2: 修复目录节点过滤错误（637节点显示707）
    - 2.1: 重构 `app/ui/components/category_widget.py` 树选中值返回逻辑，使用稳定 category_id（tag）而非脆弱 index 映射
    - 2.2: 确保 `st.session_state.selected_category` 在节点切换后准确更新
    - 2.3: 校验 `app/ui/testcases.py` 过滤链路（selected_category -> filter_test_cases）
    - 2.4: 验证“全部用例(637)”节点仅显示该节点数据，root 节点显示全量

- [x] Task 3: 统一页面按钮风格并使用低饱和分组颜色
    - 3.1: 在 `app/ui/styles.py` 统一按钮基础样式（圆角、阴影、字体）
    - 3.2: 为不同功能组按钮配置低饱和颜色主题（Run/Select/Danger/Utility）
    - 3.3: 避免使用脆弱列序号选择器，改为更稳定的选择器策略
    - 3.4: 确保 Select All、Cancel All、Run 系列、Move/Delete、Import/参数手册风格统一且可区分

- [x] Task 4: 恢复页签图标为图片并加回退
    - 4.1: 修改 `streamlit_app.py`，将 `page_icon` 设置为 `img/eva_avatar.png`
    - 4.2: 增加 icon fallback 策略（图片不可用时回退 🤖）
    - 4.3: 验证页签图标在浏览器中正常显示

- [x] Task 5: 回归验证与收尾
    - 5.1: 运行语法检查，确保 `testcases.py`、`category_widget.py`、`styles.py`、`streamlit_app.py` 无语法错误
    - 5.2: 检查 lints，确保无新增关键问题
    - 5.3: 回归验证页面布局、节点筛选、按钮样式、页签图标
    - 5.4: 输出修复总结
