import streamlit as st
import pandas as pd
import ast
from app.utils import load_data, save_data, run_tests_sync, save_history
from chat_client import get_available_apis

def render_testcases_page():
    title_col, manual_col = st.columns([5, 1])
    with title_col:
        st.title("📋 Test Cases Management")
        st.markdown("Manage, edit, and run your test cases.")
    with manual_col:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.popover("📖 参数说明手册", use_container_width=True):
            st.markdown("""
### 📖 测评参数使用手册

#### 1. 字段说明
- **retrieval_context** (检索上下文): 
  提供给大模型评估时的背景事实或参考知识。主要用于验证 AI 回答有没有胡编乱造（幻觉检测）。填入具体的参考文本片段即可。
- **conversation** (多轮对话): 
  仅在多轮测试(`multi_turn`)时生效的 JSON 数组配置。**单轮测试时此列无用，保持空白即可。**

#### 2. Validation (验证规则配置)
用于控制具体某道题的评分标准，填写 JSON 格式。可用类型（`type`）：
- **`semantic` *(默认)***: 语义验证。通过大模型（GEval）比较意思是否一致，不拘泥于字眼。
  - **`threshold`** (通过阈值): 取值 0.0 ~ 1.0。`0.5` 为宽松模式（意思大概对就行），`0.8` 以上为严格模式（意思必须高度完全对应）。
  - *示例*: `{"type": "semantic", "threshold": 0.5}`
- **`contains`**: 包含验证。确保实际回答里必定包含某些指定词汇。
  - **`keywords`**: 必须包含的词组。
  - *示例*: `{"type": "contains", "keywords": ["不能退款", "违约金"]}`
- **`exact`**: 精确验证。大模型实际输出必须和预期输出一字不差。
  - *示例*: `{"type": "exact"}`

#### 3. Overall Criteria (多轮/全局评价标准)
主要用于多轮测试，约束整题成败的全局判断：
- **`must_complete_all_turns`** (bool): 如果设为 true，那么多轮对话中只要中间一轮 AI 答错了或提前结束了，就算这整道题 Fail。
- **`min_success_rate`** (float): 最低通过率。如 0.8 表示必须答对 80% 的轮次，这题才算总评 Pass。
- *示例*: `{"must_complete_all_turns": true, "min_success_rate": 1.0}`
            """)
    
    # Initialize df in session state
    if "df" not in st.session_state:
        st.session_state.df = load_data()
    
    # Track content signature
    def get_content_signature(df):
        content_df = df.drop(columns=["Select"], errors='ignore')
        return content_df.to_json(orient='records', force_ascii=False)
    
    if "df_content_sig" not in st.session_state:
        st.session_state.df_content_sig = get_content_signature(st.session_state.df)

    @st.dialog("⚠️ Confirm Deletion")
    def confirm_delete_dialog(ids_to_delete):
        st.warning(f"Are you sure you want to permanently delete **{len(ids_to_delete)}** test cases? This action cannot be undone.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Cancel", use_container_width=True):
                st.rerun()
        with col2:
            if st.button("🗑️ Yes, Delete", type="primary", use_container_width=True):
                # Drop selected rows from the original DF
                current_df = st.session_state.df
                new_df = current_df[~current_df["id"].isin(ids_to_delete)]
                
                # Save the new filtered df to disk
                final_df = save_data(new_df)
                
                # Update session state
                if "Select" not in final_df.columns:
                     final_df.insert(0, "Select", False)
                st.session_state.df = final_df
                st.session_state.df_content_sig = get_content_signature(final_df)
                
                st.toast(f"🗑️ Deleted {len(ids_to_delete)} cases successfully!")
                st.rerun()


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
    range_col1, range_col2, btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1.2, 1.2, 1.2])
    with range_col1:
        st.text_input("From TC", value="TC0001", help="Starting test case ID", key="start_tc")
    with range_col2:
        st.text_input("To TC", value="TC0001", help="Ending test case ID", key="end_tc")
    with btn_col1:
        st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)
        run_range_clicked = st.button("▶ Run Range", use_container_width=True, type="primary", key="btn_run_range")
    with btn_col2:
        st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)
        run_selected_clicked = st.button("▶ Run Selected", use_container_width=True, type="primary", key="btn_run_selected")
    with btn_col3:
        st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)
        # Delete Selected 
        delete_selected_clicked = st.button("🗑️ Delete Selected", use_container_width=True, type="primary", key="btn_delete_selected")
    
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
    if "turn_index" in st.session_state.df.columns:
        st.session_state.df = st.session_state.df.sort_values(by=["id", "turn_index"], na_position="first").reset_index(drop=True)
    elif "id" in st.session_state.df.columns:
        st.session_state.df = st.session_state.df.sort_values(by="id").reset_index(drop=True)
    edited_df = st.data_editor(
        st.session_state.df,
        column_config={
            "Select": st.column_config.CheckboxColumn("✓", width="small", default=False),
            "id": st.column_config.TextColumn("ID", width="small", disabled=False),
            "input": st.column_config.TextColumn("Input Question", width="medium"),
            "expected_output": st.column_config.TextColumn("Expected Output", width="medium"),
            "tags": st.column_config.ListColumn("Tags"),
            "retrieval_context": st.column_config.Column("Retrieval Context", help="为大模型提供的参考上下文文件。用于验证模型的回答是否基于给定的知识库 (Faithfulness)。"),
            "overall_criteria": st.column_config.Column("Overall Criteria", help="用于评估打分的特殊判定要求或全局自定义标准。"),
            "validation": st.column_config.Column("Validation", help="验证规则 (JSON格式)。例: {\"type\": \"contains\", \"keywords\": [\"正确\"]} 或 {\"type\": \"semantic\"}。"),
            "turn_index": st.column_config.NumberColumn("Turn", width="small", help="多轮对话的顺序编号"),
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
             
    elif delete_selected_clicked:
        selected_rows = edited_df[edited_df["Select"] == True]
        if selected_rows.empty:
            st.warning("Please select cases to delete.")
        else:
            ids_to_delete = selected_rows["id"].tolist()
            confirm_delete_dialog(ids_to_delete)
    
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

