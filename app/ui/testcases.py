import streamlit as st
import pandas as pd
from app.utils import load_data, save_data, run_tests_sync, save_history
from chat_client import get_available_apis

def render_testcases_page():
    st.title("📋 Test Cases Management")
    st.markdown("Manage, edit, and run your test cases.")
    
    # Initialize df in session state
    if "df" not in st.session_state:
        st.session_state.df = load_data()
    
    # Track content signature
    def get_content_signature(df):
        content_df = df.drop(columns=["Select"], errors='ignore')
        return content_df.to_json(orient='records', force_ascii=False)
    
    if "df_content_sig" not in st.session_state:
        st.session_state.df_content_sig = get_content_signature(st.session_state.df)

    # ------------------
    # Filters & Actions
    # ------------------
    filter_col1, filter_col2, filter_col3 = st.columns([1, 2, 1])
    
    with filter_col1:
        st.selectbox("🔍 Module Filter", options=["All Modules"], index=0, key="page_module_filter")
    
    with filter_col2:
        # Tags filter
        available_filter_tags = []
        if "df" in st.session_state and "tags" in st.session_state.df.columns:
            for tags_value in st.session_state.df["tags"]:
                if isinstance(tags_value, list):
                    available_filter_tags.extend(tags_value)
        available_filter_tags = sorted(list(set(available_filter_tags)))
        
        st.multiselect("🏷️ Tags Filter", options=available_filter_tags, default=[], key="page_tags_filter")
    
    with filter_col3:
        # API Selection
        available_apis = get_available_apis() if get_available_apis() else ["Bundle API"]
        selected_api = st.selectbox("⚙️ API Endpoint", options=available_apis, index=0, key="page_api_select")
    
    st.divider()
    
    # Action row 1
    range_col1, range_col2, range_col3, btn_col1, btn_col2 = st.columns([1, 1, 0.3, 1.2, 1.2])
    with range_col1:
        st.text_input("From TC", value="TC0001", help="Starting test case ID", key="start_tc")
    with range_col2:
        st.text_input("To TC", value="TC0001", help="Ending test case ID", key="end_tc")
    with range_col3:
        st.write("")
    with btn_col1:
        run_range_clicked = st.button("▶ Run Range", use_container_width=True, type="primary", key="btn_run_range")
    with btn_col2:
        run_selected_clicked = st.button("▶ Run Selected", use_container_width=True, type="primary", key="btn_run_selected")
    
    # Action row 2 (Tags)
    def get_all_tags(df):
        all_tags = set()
        if "tags" in df.columns:
            for tags_value in df["tags"]:
                if isinstance(tags_value, list):
                    all_tags.update(tags_value)
        return sorted(list(all_tags))

    available_tags = get_all_tags(st.session_state.df)
    
    if available_tags:
        tags_col1, tags_col2 = st.columns([3, 1])
        with tags_col1:
            action_tags = st.multiselect("🏷️ Run by Tags", options=available_tags, default=[], key="tags_multiselect")
        with tags_col2:
            st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)
            run_tags_clicked = st.button("▶ Run by Tags", type="primary", use_container_width=True, key="btn_run_tags")
    else:
        run_tags_clicked = False
        action_tags = []

    # ------------------
    # Data Editor
    # ------------------
    edited_df = st.data_editor(
        st.session_state.df,
        column_config={
            "Select": st.column_config.CheckboxColumn("✓", width="small", default=False),
            "id": st.column_config.TextColumn("ID", width="small", disabled=True),
            "input": st.column_config.TextColumn("Input Question", width="medium"),
            "expected_output": st.column_config.TextColumn("Expected Output", width="medium"),
            "tags": st.column_config.ListColumn("Tags"),
        },
        num_rows="dynamic",
        use_container_width=True,
        height=600,
        key="main_data_editor"
    )

    # ------------------
    # Auto-Save Logic
    # ------------------
    # Check for changes
    current_sig = get_content_signature(edited_df)
    
    if current_sig != st.session_state.df_content_sig:
        # Save to disk
        saved_df_clean = save_data(edited_df)
        
        # Restore Select state from the edited dataframe to prevent losing selection on edit
        if "Select" in edited_df.columns:
             # We need to ensure indices align if rows were added/removed, but usually data_editor handles this.
             # Simplest is to just re-insert the series assuming index alignment or just use edited_df logic
             # But save_data might have added IDs.
             pass 
        
        # Actually, let's just use edited_df for the session state to keep UI stable, 
        # as save_data only ensures IDs and writes to disk.
        # If save_data generated NEW IDs, we should use them. 
        # For simplicity in auto-save:
        
        # 1. Write to disk
        saved_df_clean = save_data(edited_df)
        
        # 2. Update session state from the clean saved version + restore Select
        # This ensures we have the canonical IDs if generated
        if "Select" in edited_df.columns:
            saved_df_clean.insert(0, "Select", edited_df["Select"].values)
        else:
             saved_df_clean.insert(0, "Select", False)

        st.session_state.df = saved_df_clean
        st.session_state.df_content_sig = current_sig
        
        # Using toast instead of success to be less obtrusive
        st.toast("✅ Changes saved automatically!", icon="💾")

    # ------------------
    # Execution Logic
    # ------------------
    cases_to_run = []
    
    if run_selected_clicked:
        selected_rows = edited_df[edited_df["Select"] == True]
        if selected_rows.empty:
            st.warning("Please select cases to run.")
        else:
             cases_to_run = selected_rows.drop(columns=["Select"]).to_dict(orient="records")
    
    elif run_range_clicked:
        start_id = st.session_state.start_tc
        end_id = st.session_state.end_tc
        mask = (edited_df['id'] >= start_id) & (edited_df['id'] <= end_id)
        range_rows = edited_df[mask]
        if range_rows.empty:
            st.warning(f"No cases found in range {start_id} to {end_id}")
        else:
            cases_to_run = range_rows.drop(columns=["Select"]).to_dict(orient="records")
            
    elif run_tags_clicked:
        if not action_tags:
            st.warning("Please select tags.")
        else:
            # Filter by tags
            def row_has_tag(row_tags):
                if not isinstance(row_tags, list): return False
                return any(tag in row_tags for tag in action_tags)
            
            mask = edited_df['tags'].apply(row_has_tag)
            tags_rows = edited_df[mask]
            
            if tags_rows.empty:
                st.warning("No cases found with selected tags.")
            else:
                 cases_to_run = tags_rows.drop(columns=["Select"]).to_dict(orient="records")
                 
    if cases_to_run:
        try:
            from app.utils import get_job_manager
            mgr = get_job_manager()
            job_id = mgr.run_background_job(cases_to_run, api_name=selected_api)
            
            st.toast(f"🚀 Job Started! ID: {job_id}", icon="🏃")
            st.success(f"Background job started with {len(cases_to_run)} cases. \n\nGo to **Test Report** to view progress.")
            
        except Exception as e:
            st.error(f"Failed to start job: {e}")
