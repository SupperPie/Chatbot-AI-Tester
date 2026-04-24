with open('app/ui/testcases.py', 'r') as f:
    content = f.read()

# 1. Fix overriding bug
bad_save_logic = """        # Auto-Save Logic
        current_sig = get_content_signature(current_edited_df)
        
        if current_sig != getattr(st.session_state, "df_content_sig", ""):
            saved_df_clean = save_data(current_edited_df)
            st.session_state.df = saved_df_clean
            st.session_state.df_content_sig = current_sig
            st.toast("✅ Changes saved automatically!", icon="💾")"""

good_save_logic = """        # Auto-Save Logic (Safely Update Main DataFrame)
        page_edited = not edited_page_df.equals(page_df)
        if page_edited:
            # Update the main df safely
            for idx, row in edited_page_df.iterrows():
                row_id = row['id']
                main_mask = st.session_state.df['id'] == row_id
                if main_mask.sum() == 1:
                    for col in edited_page_df.columns:
                        if col in st.session_state.df.columns:
                            st.session_state.df.loc[main_mask, col] = row[col]
            
            save_data(st.session_state.df)
            st.session_state.df_content_sig = get_content_signature(st.session_state.df)
            st.toast("✅ Changes saved automatically!", icon="💾")"""

content = content.replace(bad_save_logic, good_save_logic)

# 2. Fix layout by putting the Filter & Run section into top_right_col
# Currently it is outside.
# Let's wrap it in `with top_right_col:`
# We can find the line: `    # ------------------` followed by `    # Filter & Run Section`
# and prepend `    with top_right_col:\n`
# Then indent everything until `    st.divider()` or `    # ------------------\n    # Data Editor Section`

start_marker = "    # ------------------\n    # Filter & Run Section"
end_marker = "    st.divider()\n    \n    # ------------------\n    # Data Editor Section"

if start_marker in content and end_marker in content:
    pre, rest = content.split(start_marker, 1)
    middle, post = rest.split(end_marker, 1)
    
    # Prepend with top_right_col
    new_middle = "    with top_right_col:\n        # ------------------\n        # Filter & Run Section"
    
    # Indent everything in middle
    for line in middle.split('\n'):
        if line.strip():
            new_middle += "\n    " + line
        else:
            new_middle += "\n"
            
    content = pre + new_middle + "\n" + end_marker + post

with open('app/ui/testcases.py', 'w') as f:
    f.write(content)

