import streamlit as st
import pandas as pd
import json
import os
import time
from app.utils import export_pdf, delete_reports, run_tests_sync, save_history, update_history_entry
from chat_client import get_available_apis


def render_report_page():
    st.title("📊 Test Report History")

    try:
        from app.services.history_service import HistoryService
        service = HistoryService()
        history = service.get_all()
    except Exception as e:
        st.error(f"Error reading history from DB: {e}")
        return

    if not history:
        st.info("No history found.")
        return

    # API Selector for Rerun
    available_apis = get_available_apis() if get_available_apis() else ["Bundle API"]
    
    st.caption("Expand a report to view details or manage it.")

    # Check if any job is running to decide on auto-refresh
    any_running = any(e.get("status") == "running" for e in history)
    if any_running:
        if st.button("🔄 Refresh Progress"):
            st.rerun()
        # Optional: Auto-refresh via sleep (can be annoying if typing, so button is safer or use empty container)
        # st.empty().text("Running...") 

    for i, entry in enumerate(history):
        entry_id = entry.get('id')
        status = entry.get('status', 'completed')
        
        passed_count = entry.get('passed', 0)
        total_count = entry.get('total', 0)
        
        # Stats display
        if status == "running":
            # Estimate or use started_count if available
            started = entry.get('started_count', 0)
            # Total might be initial count, or updated.
            # Avoid div by zero
            if total_count == 0: total_count = 1 
            progress = min(started / total_count, 1.0)
            
            label = f"⏳ {entry.get('timestamp')} - Running... {started}/{total_count}"
        else:
            pass_rate = (passed_count / total_count * 100) if total_count > 0 else 0
            label = f"{entry.get('timestamp')} - Pass Rate: {pass_rate:.1f}% ({passed_count}/{total_count})"
        
        with st.expander(label):
            # SHOW PROGRESS BAR IF RUNNING
            if status == "running":
                st.progress(progress, text=f"Processing {started}/{total_count} cases...")
                st.info("Results are loading in real-time. Click Refresh above to update table.")

            # --------------------------
            # Action Buttons Row
            # --------------------------
            ac_col1, ac_col2, ac_col3, ac_col4 = st.columns([1.5, 1.5, 1.5, 3])
            
            with ac_col1:
                # DELETE BUTTON
                confirm_key = f"confirm_del_{entry_id}"
                if confirm_key not in st.session_state:
                    st.session_state[confirm_key] = False
                
                if not st.session_state[confirm_key]:
                    if st.button("🗑️ Delete", key=f"btn_del_{entry_id}"):
                        st.session_state[confirm_key] = True
                        st.rerun()
                else:
                    col_confirm, col_cancel = st.columns([1, 1])
                    if col_confirm.button("✅ Confirm", key=f"btn_conf_{entry_id}"):
                        if delete_reports([entry_id]):
                            st.success("Deleted.")
                            del st.session_state[confirm_key]
                            st.rerun()
                    if col_cancel.button("❌ Cancel", key=f"btn_canc_{entry_id}"):
                         st.session_state[confirm_key] = False
                         st.rerun()

            with ac_col2:
                # RERUN / STOP BUTTON
                if status != "running":
                    if st.button("▶ Rerun Report", key=f"btn_rerun_{entry_id}"):
                        res_df_curr = pd.DataFrame(entry.get('results', []))
                        if not res_df_curr.empty:
                            from app.utils import load_data
                            main_df = load_data()
                            
                            cases_to_rerun = []
                            for _, row in res_df_curr.iterrows():
                                cid = row.get("case_id")
                                # Find master definitions to get the freshest expected_output and criteria
                                mask = (main_df['id'] == cid)
                                
                                if mask.any():
                                    live_rows = main_df[mask]
                                    
                                    # Handle Multi-turn grouping natively like test_engine run_batch expects
                                    if len(live_rows) > 1:
                                        # It's a reconstructed multi-turn array from live database
                                        for _, m_row in live_rows.iterrows():
                                            cases_to_rerun.append(m_row.to_dict())
                                            # We only want to process the multi-turn group once per CID
                                        # To prevent duplicating if report had multiple turns listed as rows, 
                                        # break out if we've already added this CID (we must deduplicate CIDs in report loop first)
                                    else:
                                        cases_to_rerun.append(live_rows.iloc[0].to_dict())
                                else:
                                    # Fallback to historical snapshot if deleted from master testcases
                                    cases_to_rerun.append({
                                        "id": cid,
                                        "input": row.get("input", ""),
                                        "expected_output": row.get("expected_output", ""),
                                        "type": row.get("type", "single_turn"),
                                        "turns": row.get("turns", []) 
                                    })
                                    
                            # Remove duplicate dictionaries if CID had multiple lines in the old report parsing logic
                            # (Python dicts aren't hashable, so we filter by unique ID + turn_index)
                            seen = set()
                            unique_cases_to_rerun = []
                            for c in cases_to_rerun:
                                t_idx = str(c.get("turn_index", "0"))
                                unique_key = f"{c.get('id')}_{t_idx}"
                                if unique_key not in seen:
                                    seen.add(unique_key)
                                    unique_cases_to_rerun.append(c)
                            
                            try:
                                from app.utils import get_job_manager
                                mgr = get_job_manager()
                                target_api = st.session_state.get(f"api_sel_{entry_id}", "Bundle API")
                                job_id = mgr.run_background_job(unique_cases_to_rerun, api_name=target_api)
                                
                                st.success(f"Rerun started! Job ID: {job_id}")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Rerun failed: {e}")
                else:
                    # STOP BUTTON
                    if st.button("🛑 Stop Job", key=f"btn_stop_{entry_id}"):
                        from app.utils import get_job_manager
                        mgr = get_job_manager()
                        mgr.cancel_job(entry_id)
                        st.warning("Stopping job... please wait.")
                        time.sleep(1)
                        st.rerun()
            with ac_col4:
                # API SELECTOR
                # Try to find index of stored api_name
                stored_api = entry.get("api_name", "Bundle API")
                default_idx = 0
                if stored_api in available_apis:
                    default_idx = available_apis.index(stored_api)
                
                st.selectbox("API", options=available_apis, index=default_idx, key=f"api_sel_{entry_id}", label_visibility="collapsed")
                
                st.write("") # Spacer
                
                # ACTION BUTTONS CONTAINER
                top_action_container = st.container()

            
            st.divider()

            # --------------------------
            # Data View
            # --------------------------
            res_df = pd.DataFrame(entry.get('results', []))
            
            if not res_df.empty:
                # Unroll any multi-turn results into separate rows
                unrolled_rows = []
                for _, row in res_df.iterrows():
                    if "turns" in row and isinstance(row["turns"], list) and len(row["turns"]) > 0:
                        for idx, t in enumerate(row["turns"]):
                            new_row = row.copy().to_dict()
                            new_row["turn_index"] = t.get("turn", idx + 1)
                            new_row["input"] = t.get("user", "")
                            new_row["expected_output"] = t.get("expected", "")
                            new_row["actual_output"] = t.get("actual", "")
                            
                            is_manual = t.get("manual_review", False)
                            if is_manual:
                                new_row["passed"] = t.get("passed", False)
                            else:
                                score_val = float(t.get("score", 0)) if t.get("score") is not None else 0.0
                                new_row["passed"] = (score_val >= 0.5)
                            
                            new_row["latency"] = t.get("latency", 0)
                            new_row["ttft"] = t.get("ttft", 0)
                            new_row["thinking"] = t.get("thinking", "")
                            new_row["inform_base"] = t.get("inform_base", "")
                            new_row["raw"] = str(t.get("raw", ""))
                            new_row["retrieval_context"] = str(t.get("retrieval_context", ""))
                            unrolled_rows.append(new_row)
                    else:
                        row_dict = row.to_dict()
                        row_dict["turn_index"] = None
                        
                        is_manual = row_dict.get("manual_review", False)
                        if is_manual:
                            row_dict["passed"] = row_dict.get("passed", False)
                        else:
                            score_val = float(row_dict.get("score", 0)) if pd.notna(row_dict.get("score")) else 0.0
                            row_dict["passed"] = (score_val >= 0.5)
                        
                        row_dict["raw"] = str(row_dict.get("raw", ""))
                        
                        # Explicitly preserve retrieval_context as string
                        rc = row_dict.get("retrieval_context", "")
                        if isinstance(rc, list):
                            row_dict["retrieval_context"] = ", ".join(str(x) for x in rc)
                        else:
                            row_dict["retrieval_context"] = str(rc) if rc else ""
                            
                        unrolled_rows.append(row_dict)
                
                display_res_df = pd.DataFrame(unrolled_rows)
                
                # Format retrieval_context to a plain string
                if "retrieval_context" in display_res_df.columns:
                    display_res_df["retrieval_context"] = display_res_df["retrieval_context"].apply(
                        lambda x: ", ".join(x) if isinstance(x, list) else str(x)
                    )

                # Ensure review_comment exists
                if "review_comment" not in display_res_df.columns:
                    display_res_df["review_comment"] = ""
                else:
                    display_res_df["review_comment"] = display_res_df["review_comment"].fillna("").astype(str)

                # Configure standard columns order
                target_cols = [
                    "Select", "case_id", "turn_index", "input", "expected_output", "actual_output", "retrieval_context",
                    "score", "passed", "ttft", "latency", "reason", 
                    "review_comment", "thinking", "inform_base", "raw"
                ]
                # Ensure Select exists
                if "Select" not in display_res_df.columns:
                    display_res_df.insert(0, "Select", False)

                # Only keep columns that exist in the dataframe to prevent KeyError
                display_cols = [c for c in target_cols if c in display_res_df.columns]
                
                # Keep Select if we need it, but we don't use Select in history table right now.
                display_res_df = display_res_df[display_cols]
                
                all_cols = display_res_df.columns.tolist()
                editable_cols = ["Select", "passed", "review_comment"]
                disabled_cols = [c for c in all_cols if c not in editable_cols]

                edited_df = st.data_editor(
                    display_res_df,
                    column_config={
                        "Select": st.column_config.CheckboxColumn("✓", width="small", default=False),
                        "case_id": st.column_config.TextColumn("ID", width="small"),
                        "turn_index": st.column_config.NumberColumn("Turn", width="small"),
                        "input": st.column_config.TextColumn("Input", width="medium"),
                        "expected_output": st.column_config.TextColumn("Expected", width="medium"),
                        "actual_output": st.column_config.TextColumn("Actual Output", width="large"),
                        "retrieval_context": st.column_config.TextColumn("Retrieval Context", width="large"),
                        "thinking": st.column_config.TextColumn("Thinking Process", width="large"),
                        "inform_base": st.column_config.TextColumn("Inform Base (Tools)", width="large"),
                        "raw": st.column_config.TextColumn("Raw Data", width="large"),
                        "score": st.column_config.NumberColumn("Score", format="%.2f"),
                        "passed": st.column_config.CheckboxColumn("Passed", width="small"),
                        "review_comment": st.column_config.TextColumn("Review Comment", width="medium"),
                        "ttft": st.column_config.NumberColumn("TTFT", format="%.2f s"),
                        "latency": st.column_config.NumberColumn("Latency", format="%.2f s"),
                        "reason": st.column_config.TextColumn("Reason", width="large"),
                    },
                    use_container_width=True,
                    disabled=disabled_cols,
                    hide_index=True,
                    key=f"hist_tbl_{entry_id}"
                )

                # INJECT ACTION BUTTONS AFTER GETTING EDITED_DF
                with top_action_container:
                    act_col1, act_col2 = st.columns(2)
                    with act_col1:
                        # BLIND REVIEW EXPORT
                        with st.popover("🙈 Export to Blind Review", use_container_width=True):
                            st.markdown("### Export Config")
                            export_mode = st.radio("Mode", ["Create New Session", "Add to Existing Session"], key=f"br_mode_{entry_id}")
                            
                            from app.ui.blind_review import load_reviews, save_reviews
                            all_reviews = load_reviews()
                            
                            target_session_name = ""
                            if export_mode == "Create New Session":
                                default_name = f"Review {entry.get('timestamp', 'New')}"
                                target_session_name = st.text_input("Session Name", value=default_name, key=f"br_name_{entry_id}")
                            else:
                                if not all_reviews:
                                     st.warning("No existing sessions.")
                                else:
                                     session_opts = [r["name"] for r in all_reviews]
                                     target_session_name = st.selectbox("Select Session", session_opts, key=f"br_sel_{entry_id}")
                            
                            if st.button("Confirm Export", type="primary", key=f"btn_br_exp_{entry_id}"):
                                if not target_session_name:
                                    st.error("Session name required.")
                                else:
                                    # Logic to Prepare Data
                                    report_results = entry.get("results", [])
                                    if not report_results:
                                        st.error("No results to export.")
                                    else:
                                        import uuid
                                        from datetime import datetime
                                        
                                        session_data = None
                                        if export_mode == "Add to Existing Session":
                                            session_data = next((r for r in all_reviews if r["name"] == target_session_name), None)
                                        
                                        if not session_data:
                                            session_data = {
                                                "id": str(uuid.uuid4()),
                                                "name": target_session_name,
                                                "created_at": datetime.now().isoformat(),
                                                "items": []
                                            }
                                            if export_mode == "Create New Session":
                                                all_reviews.append(session_data)
                                        
                                        updated_count = 0
                                        added_count = 0
                                        
                                        for row in report_results:
                                            q_input = row.get("input", "")
                                            actual = row.get("actual_output", "")
                                            
                                            if row.get("type") == "multi_turn" and isinstance(row.get("turns"), list):
                                                lines = []
                                                for t in row["turns"]:
                                                    status = "✅" if t.get("passed") else "❌"
                                                    lines.append(f"T{t.get('turn')} {status}: Q: {t.get('user')} | A: {t.get('actual')}")
                                                actual_text = "\n".join(lines)
                                            else:
                                                actual_text = str(actual)
        
                                            match = next((item for item in session_data["items"] if item["input"] == q_input), None)
                                            
                                            if match:
                                                existing_keys = sorted(match["options"].keys())
                                                next_char = "A" if not existing_keys else chr(ord(existing_keys[-1]) + 1)
                                                match["options"][next_char] = actual_text
                                                updated_count += 1
                                            else:
                                                new_item = {
                                                    "input": q_input,
                                                    "options": {"A": actual_text},
                                                    "vote": None
                                                }
                                                session_data["items"].append(new_item)
                                                added_count += 1
                                        
                                        save_reviews(all_reviews)
                                        st.success(f"Exported! Added {added_count} new, Updated {updated_count} existing.")

                    with act_col2:
                        if st.button("🔄 Update Expect Result", use_container_width=True, key=f"btn_upd_exp_{entry_id}"):
                            selected_rows = edited_df[edited_df["Select"] == True]
                            if selected_rows.empty:
                                st.warning("Please select at least one test case to update.")
                            else:
                                from app.utils import load_data, save_data
                                main_df = load_data()
                                
                                updated_cases = 0
                                for _, sel_row in selected_rows.iterrows():
                                    cid = sel_row['case_id']
                                    tidx = sel_row.get('turn_index')
                                    new_val = sel_row['actual_output']
                                    
                                    if pd.isna(tidx) or tidx is None:
                                        mask = (main_df['id'] == cid)
                                    else:
                                        mask = (main_df['id'] == cid) & (main_df['turn_index'] == tidx)
                                        
                                    if mask.any():
                                        main_df.loc[mask, 'expected_output'] = new_val
                                        updated_cases += mask.sum()
                                        
                                if updated_cases > 0:
                                    final_df = save_data(main_df)
                                    if "df" in st.session_state:
                                        if "Select" not in final_df.columns:
                                            final_df.insert(0, "Select", False)
                                        st.session_state.df = final_df
                                        content_df = final_df.drop(columns=["Select"], errors='ignore')
                                        st.session_state.df_content_sig = content_df.to_json(orient='records', force_ascii=False)
                                    st.success(f"Successfully updated Expected Output for {updated_cases} rows.")
                                else:
                                    st.warning("No matching test cases found in reality to update.")

                # SAVE BUTTON
                if st.button("💾 Save Changes", key=f"btn_save_{entry_id}"):
                    try:
                        current_results = entry.get('results', [])
                        # Create lookup from edited_df
                        updates = {}
                        if not edited_df.empty:
                            for _, row in edited_df.iterrows():
                                updates[row['case_id']] = {
                                    'passed': row.get('passed'),
                                    'review_comment': row.get('review_comment')
                                }
                        
                        # Apply updates to original results list
                        updated_count = 0
                        for res in current_results:
                            cid = res.get('case_id')
                            if cid in updates:
                                res['passed'] = bool(updates[cid].get('passed', False))
                                res['review_comment'] = str(updates[cid].get('review_comment', ""))
                                res['manual_review'] = True
                                
                                # If it's multi-turn, also update all turns to mirror the manual pass 
                                # logic so they render consistently
                                if "turns" in res and isinstance(res["turns"], list):
                                    for t in res["turns"]:
                                        t['passed'] = res['passed']
                                        t['manual_review'] = True
                                        
                                updated_count += 1
                        
                        if update_history_entry(entry_id, current_results):
                            st.success(f"Successfully saved changes for {updated_count} cases!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Failed to save changes to history file.")
                    except Exception as e:
                        st.error(f"Error saving changes: {e}")
            
            else:
                if status == "running":
                    st.info("Waiting for first result...")
                elif status == "failed":
                    error_msg = entry.get("error", "Unknown error")
                    st.error(f"❌ Job failed: {error_msg}")
                    st.caption("Check server terminal logs for full traceback. Common causes: deepeval not installed, missing .env variables, or API connection issues.")
                else:
                    st.text("No results data.")

