import re

# 1. Fix category_widget.py
with open('app/ui/components/category_widget.py', 'r') as f:
    content = f.read()

# Replace the broken sac_items logic
broken_pattern = r"            children_items = build_sac_tree\(node\.get\('children', \[\]\)\)\s+item = sac\.TreeItem\(label=label, icon=icon, children=children_items if children_items else None\)\s+items\.append\(item\)\s+return items\s+\)\s+sac_items = \[root_item\]"
fixed = """            children_items = build_sac_tree(node.get('children', []))
            item = sac.TreeItem(label=label, icon=icon, children=children_items if children_items else None)
            items.append(item)
        return items

    sac_items = build_sac_tree(tree)"""
content = re.sub(broken_pattern, fixed, content)

with open('app/ui/components/category_widget.py', 'w') as f:
    f.write(content)

# 2. Fix testcases.py
with open('app/ui/testcases.py', 'r') as f:
    lines = f.readlines()

# A) Fix the overriding bug
for i, line in enumerate(lines):
    if "current_sig != getattr(st.session_state, \"df_content_sig\", \"\"):" in line:
        # We need to replace the block
        # Find the end of the block (else: ... st.session_state.df = current_edited_df)
        start_idx = i - 1 # from current_sig = ...
        end_idx = i
        for j in range(i, i+30):
            if "logger.debug(\">>> render_paginated_table() fragment 结束\")" in lines[j]:
                end_idx = j
                break
        
        replacement = """        # ------------------
        # Auto-Save Logic (Safely Update Main DataFrame)
        # ------------------
        # Check if the current paginated slice actually changed
        page_edited = not edited_page_df.equals(page_df)
        if page_edited:
            # Safely update the main dataframe
            for idx, row in edited_page_df.iterrows():
                row_id = row['id']
                main_mask = st.session_state.df['id'] == row_id
                if main_mask.sum() == 1:
                    for col in edited_page_df.columns:
                        if col in st.session_state.df.columns:
                            st.session_state.df.loc[main_mask, col] = row[col]
            
            # Save the full dataframe
            save_data(st.session_state.df)
            st.session_state.df_content_sig = get_content_signature(st.session_state.df)
            st.toast("✅ Changes saved automatically!", icon="💾")
        
"""
        lines[start_idx:end_idx] = [replacement]
        break

# B) Fix the layout: move filter & run into top_right_col
# First, remove the "with top_right_col:" at line 227 (if it exists) and wrap the whole thing.
# Actually, top_right_col is defined around line 119.
# The simplest way to fix the layout is to find the whole Control Panel and Filter section and wrap them.
# Let's find where Filter & Run starts and put "with top_right_col:" before it, IF it's not already.
# Wait, currently it is:
# with top_right_col:
#     # Control Panel
# ... (Import logic)
# st.markdown("#### 🔍 筛选条件")  <-- outside!
for i, line in enumerate(lines):
    if "st.markdown(\"#### 🔍 筛选条件\")" in line:
        filter_start = i
        break

for i, line in enumerate(lines[filter_start:]):
    if "# ------------------" in line and "Data Editor" in line:
        filter_end = filter_start + i
        break

# Indent filter section
for i in range(filter_start-3, filter_end):
    if not lines[i].startswith("        "):
        if lines[i].startswith("    "):
            lines[i] = "    " + lines[i]

# Add "with top_right_col:" if it closed before
# Actually, it's safer to just let it be in the right column by injecting it right after the import block.
# Let's just output it to a new file to be safe.
with open('app/ui/testcases.py', 'w') as f:
    f.writelines(lines)
