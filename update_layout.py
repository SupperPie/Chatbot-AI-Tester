import re

with open('app/ui/testcases.py', 'r') as f:
    lines = f.readlines()

# 1. Replace the sidebar category code (lines 83-90)
start_sidebar = -1
for i, line in enumerate(lines):
    if "selected_category = 'root'" in line and "目录管理侧边栏" in lines[i-1]:
        start_sidebar = i - 1
        break

if start_sidebar != -1:
    sidebar_block = """    # Layout: Top Section
    top_left_col, top_right_col = st.columns([1, 2.5])
    
    selected_category = 'root'
    if ENABLE_CATEGORY_FEATURE:
        with top_left_col:
            selected_category = render_category_widget_safe()
"""
    lines[start_sidebar:start_sidebar+8] = [sidebar_block]

# We need to find the new index of "Control Panel"
control_panel_idx = -1
for i, line in enumerate(lines):
    if "# Control Panel" in line:
        control_panel_idx = i - 1
        break

run_controls_end_idx = -1
for i, line in enumerate(lines[control_panel_idx:]):
    if "run_range_clicked = st.button" in line:
        run_controls_end_idx = control_panel_idx + i
        break

if control_panel_idx != -1 and run_controls_end_idx != -1:
    # Indent everything between control_panel_idx and run_controls_end_idx
    for i in range(control_panel_idx, run_controls_end_idx + 1):
        if lines[i].strip() != "":
            lines[i] = "    " + lines[i]
            
    # Insert 'with top_right_col:' before control panel
    lines.insert(control_panel_idx, "    with top_right_col:\n")
    
    # We also need to fix labels and texts
    # "Management & Filters" -> "Configuration & Management"
    # "Filter by Tags" -> "Select Tags"
    for i in range(control_panel_idx, run_controls_end_idx + 2):
        lines[i] = lines[i].replace("#### 🛠️ Management & Filters", "#### ⚙️ Configuration & Management")
        lines[i] = lines[i].replace("🏷️ Filter by Tags", "🏷️ Select Tags")

with open('app/ui/testcases.py', 'w') as f:
    f.writelines(lines)
