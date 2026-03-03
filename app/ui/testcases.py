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


    # Filters & Actions
    # ------------------
    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1, 1.5, 1, 0.5])
    
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

    with filter_col4:
        # Import / Template Popover
        st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True) # Align with selectbox
        with st.popover("📤 Import", use_container_width=True):
             st.markdown("### Import Test Cases")
             # Download Template
             try:
                 with open("docs/import_template.csv", "rb") as f:
                     st.download_button("📄 Download Template", data=f, file_name="import_template.csv", mime="text/csv", help="Download CSV template")
             except Exception as e:
                 st.error(f"Template not found: {e}")
             
             st.divider()
             
             st.info("Upload CSV/JSON with `input`, `expected_output`.")
             uploaded_file = st.file_uploader("Upload File", type=["csv", "json"], key="popover_uploader")
             
             if uploaded_file is not None:
                try:
                    if uploaded_file.name.endswith('.csv'):
                         try:
                             import_df = pd.read_csv(uploaded_file, encoding='utf-8')
                         except UnicodeDecodeError:
                             uploaded_file.seek(0)
                             import_df = pd.read_csv(uploaded_file, encoding='gb18030')
                    else:
                        import_df = pd.read_json(uploaded_file)
                    
                    # Validation
                    required_cols = ["input", "expected_output"]
                    if not all(col in import_df.columns for col in required_cols):
                        st.error(f"Missing columns: {', '.join(required_cols)}")
                    else:
                        update_existing = st.checkbox("Update existing cases by ID (if ID matches)", value=False, key="chk_update_cases")
                        
                        if st.button(f"Confirm Import", type="primary", key="btn_confirm_import"):
                            # Prepare data
                            # Ensure tags are lists
                            if "tags" in import_df.columns:
                                def normalize_tags(x):
                                    if isinstance(x, list): return x
                                    if pd.isna(x) or x == "": return []
                                    if isinstance(x, str):
                                        try:
                                            # Try to parse string representation of list like "['tag1', 'tag2']"
                                            import ast
                                            parsed = ast.literal_eval(x)
                                            if isinstance(parsed, list): return parsed
                                            return [x]
                                        except:
                                            # Treat string as single tag
                                            return [x] if x.strip() else []
                                    return []
                                import_df["tags"] = import_df["tags"].apply(normalize_tags)
                            else:
                                import_df["tags"] = [[] for _ in range(len(import_df))]

                            current_df = st.session_state.df.drop(columns=["Select"], errors='ignore')
                            
                            if update_existing:
                                if "id" not in import_df.columns:
                                    st.error("Column 'id' is required for updating existing cases.")
                                    st.stop()
                                
                                # Convert IDs to string for comparison
                                current_df["id"] = current_df["id"].astype(str)
                                import_df["id"] = import_df["id"].astype(str)
                                
                                # Create a dict mapping ID to index in current_df for fast lookup
                                id_to_index = {row_id: idx for idx, row_id in current_df["id"].items()}
                                
                                updated_count = 0
                                new_count = 0
                                
                                for _, row in import_df.iterrows():
                                    row_id = row.get("id")
                                    if row_id in id_to_index:
                                        # Update existing
                                        idx = id_to_index[row_id]
                                        for col in row.index:
                                            val = row[col]
                                            # Only update if value is not empty/NaN
                                            # Skip ID update itself
                                            if col == "id": continue
                                            
                                            # Check empty/NaN
                                            # Using pd.isna(list) returns array of bools which fails if check
                                            is_empty = False
                                            
                                            if isinstance(val, list):
                                                if not val: is_empty = True
                                            elif pd.isna(val):
                                                is_empty = True
                                            elif isinstance(val, str) and not val.strip():
                                                is_empty = True
                                            
                                            if not is_empty:
                                                # Special handling for tags: merge or overwrite?
                                                # Request said "update", usually implies overwrite or list-merge
                                                # Let's overwrite for simplicity unless user asks otherwise, 
                                                # or maybe merge unique?
                                                # "Update non-empty fields" -> Overwrite existing field with new non-empty value
                                                if col == "tags":
                                                    # Fix: Ensure logic handles list properly
                                                    current_df.at[idx, col] = val
                                                else:
                                                    current_df.at[idx, col] = val
                                        updated_count += 1
                                    else:
                                        # It's a new ID or ID not present -> Append
                                        # We can just append to a list and concat later or append to DF
                                        # Appending to DF row by row is slow, but consistent here.
                                        # Better: Collect new rows
                                        pass 
                                
                                # Filter import_df for ONLY new rows to concat
                                existing_ids = set(current_df["id"])
                                new_rows_df = import_df[~import_df["id"].isin(existing_ids)]
                                new_count = len(new_rows_df)
                                
                                combined_df = pd.concat([current_df, new_rows_df], ignore_index=True)
                                st.toast(f"Updated {updated_count} cases, Added {new_count} new cases.")
                                
                            else:
                                # Standard Append Mode (Drop ID to regenerate)
                                if "id" in import_df.columns:
                                    del import_df["id"]
                                
                                combined_df = pd.concat([current_df, import_df], ignore_index=True)
                                st.toast(f"Imported {len(import_df)} new cases.")
                            
                            # Save
                            final_df = save_data(combined_df)
                            
                            # Update State
                            if "Select" not in final_df.columns:
                                 final_df.insert(0, "Select", False)
                            st.session_state.df = final_df
                            st.session_state.df_content_sig = get_content_signature(final_df)
                            
                            st.rerun()
                            
                except Exception as e:
                    st.error(f"Error: {e}")
    
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
            "id": st.column_config.TextColumn("ID", width="small", disabled=False),
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
             # Use JobManager (Async) but simulate sync experience with progress bar
            from app.job_manager import get_job_manager
            mgr = get_job_manager()
            
            # Start Job
            job_id = mgr.run_background_job(cases_to_run, api_name=selected_api)
            
            # Progress UI
            progress_bar = st.progress(0, text="Initializing...")
            status_text = st.empty()
            
            import time
            from app.utils import HISTORY_JSON
            import json
            import os
            
            # Poll for completion
            while True:
                time.sleep(1) # Poll interval
                
                # Check status from History check
                # (JobManager updates history.json)
                job_data = None
                if os.path.exists(HISTORY_JSON):
                    try:
                        with open(HISTORY_JSON, "r", encoding="utf-8") as f:
                            hist = json.load(f)
                            for h in hist:
                                if h.get("id") == job_id:
                                    job_data = h
                                    break
                    except:
                        pass
                
                if job_data:
                    status = job_data.get("status", "running")
                    
                    # Update Progress
                    started = job_data.get("started_count", 0)
                    total = job_data.get("total", 1)
                    if total == 0: total = 1
                    
                    pct = min(started / total, 1.0)
                    progress_bar.progress(pct, text=f"Running... {started}/{total}")
                    
                    if status in ["completed", "failed", "cancelled"]:
                        progress_bar.progress(1.0, text=f"Finished: {status}")
                        break
                else:
                    # Should not happen unless file delete race
                    status_text.warning("Job data not found...")
                    break
            
            # Show results if completed
            if job_data and job_data.get("status") == "completed":
                st.toast(f"Completed! Ran {len(cases_to_run)} tests.", icon="🏃")
                st.success(f"Successfully ran {len(cases_to_run)} tests. View details in **Test Report**.")
                
                # Show simplified results result
                results = job_data.get("results", [])
                res_df = pd.DataFrame(results)
                cols = ["id", "input", "passed", "score", "reason"]
                cols = [c for c in cols if c in res_df.columns]
                st.dataframe(res_df[cols].style.format({"score": "{:.2f}"}), use_container_width=True)
                
            elif job_data and job_data.get("status") == "failed":
                st.error(f"Job failed: {job_data.get('error')}")
            
        except Exception as e:
            st.error(f"Failed to run tests: {e}")

