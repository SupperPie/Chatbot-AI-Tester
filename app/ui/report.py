import streamlit as st
import pandas as pd
import json
import os
import time
from app.utils import HISTORY_JSON, export_pdf, delete_reports, run_tests_sync, save_history, update_history_entry
from chat_client import get_available_apis

def render_report_page():
    st.title("📊 Test Report History")
    
    if not os.path.exists(HISTORY_JSON):
        st.info("No history found.")
        return

    try:
        with open(HISTORY_JSON, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception as e:
        st.error(f"Error reading history: {e}")
        return

    if not history:
        st.info("No history available.")
        return

def render_report_page():
    st.title("📊 Test Report History")
    
    if not os.path.exists(HISTORY_JSON):
        st.info("No history found.")
        return

    try:
        with open(HISTORY_JSON, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception as e:
        st.error(f"Error reading history: {e}")
        return

    if not history:
        st.info("No history available.")
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
                            cases_to_rerun = []
                            for _, row in res_df_curr.iterrows():
                                 cases_to_rerun.append({
                                     "id": row.get("case_id"),
                                     "input": row.get("input", ""),
                                     "expected_output": row.get("expected_output", ""),
                                     "type": row.get("type", "single_turn"),
                                     "turns": row.get("turns", []) 
                                 })
                            
                            try:
                                from app.utils import get_job_manager
                                mgr = get_job_manager()
                                target_api = st.session_state.get(f"api_sel_{entry_id}", "Bundle API")
                                job_id = mgr.run_background_job(cases_to_rerun, api_name=target_api)
                                
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
                                # Prepare Export Items
                                # Logic: Group by ID or Input? User said "match input". 
                                # Input is safer if IDs change, but ID is structurally better.
                                # Let's use ID as primary match if available, else Input?
                                # Requirement: "针对同一个问题...把report中的output导过去" -> suggests Input Matching
                                # But we have IDs. Let's match by Input (Question) as requested to be robust across different executions.
                                
                                import uuid
                                from datetime import datetime
                                
                                # Load or Create Session Data
                                session_data = None
                                if export_mode == "Add to Existing Session":
                                    session_data = next((r for r in all_reviews if r["name"] == target_session_name), None)
                                
                                if not session_data:
                                    # Create New
                                    session_data = {
                                        "id": str(uuid.uuid4()),
                                        "name": target_session_name,
                                        "created_at": datetime.now().isoformat(),
                                        "items": []
                                    }
                                    if export_mode == "Create New Session":
                                        all_reviews.append(session_data)
                                
                                # Merge Logic
                                updated_count = 0
                                added_count = 0
                                
                                for row in report_results:
                                    q_input = row.get("input", "")
                                    actual = row.get("actual_output", "")
                                    
                                    # Handle Multi-turn formatting equivalent to report view if needed?
                                    # Blind review usually compares single final answer? 
                                    # If multi-turn, actual_output might be a list or we need to format it.
                                    # report view formats it string. Let's use simple actual object or formatted?
                                    # Let's check format logic in render_report function.
                                    # It formats on the fly. We should replicate that or store raw.
                                    # For blind review, formatted string is best.
                                    
                                    if row.get("type") == "multi_turn" and isinstance(row.get("turns"), list):
                                        # Simple format
                                        lines = []
                                        for t in row["turns"]:
                                            status = "✅" if t.get("passed") else "❌"
                                            lines.append(f"T{t.get('turn')} {status}: Q: {t.get('user')} | A: {t.get('actual')}")
                                        actual_text = "\n".join(lines)
                                    else:
                                        actual_text = str(actual)

                                    # Find matching item in session
                                    match = next((item for item in session_data["items"] if item["input"] == q_input), None)
                                    
                                    if match:
                                        # Append option
                                        # Find next letter
                                        existing_keys = sorted(match["options"].keys())
                                        if not existing_keys:
                                            next_char = "A"
                                        else:
                                            last_char = existing_keys[-1]
                                            next_char = chr(ord(last_char) + 1)
                                        
                                        match["options"][next_char] = actual_text
                                        updated_count += 1
                                    else:
                                        # New Item
                                        new_item = {
                                            "input": q_input,
                                            "options": {"A": actual_text},
                                            "vote": None
                                        }
                                        session_data["items"].append(new_item)
                                        added_count += 1
                                
                                # Save
                                save_reviews(all_reviews)
                                st.success(f"Exported! Added {added_count} new, Updated {updated_count} existing.")

            
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
                            new_row["passed"] = t.get("passed", False)
                            new_row["latency"] = t.get("latency", 0)
                            new_row["ttft"] = t.get("ttft", 0)
                            new_row["thinking"] = t.get("thinking", "")
                            new_row["inform_base"] = t.get("inform_base", "")
                            new_row["retrieval_context"] = str(t.get("retrieval_context", ""))
                            unrolled_rows.append(new_row)
                    else:
                        row_dict = row.to_dict()
                        row_dict["turn_index"] = None
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
                    "case_id", "turn_index", "input", "expected_output", "actual_output", "retrieval_context",
                    "score", "passed", "ttft", "latency", "reason", 
                    "review_comment", "thinking", "inform_base", "raw"
                ]
                # Only keep columns that exist in the dataframe to prevent KeyError
                display_cols = [c for c in target_cols if c in display_res_df.columns]
                
                # Keep Select if we need it, but we don't use Select in history table right now.
                display_res_df = display_res_df[display_cols]
                
                all_cols = display_res_df.columns.tolist()
                editable_cols = ["passed", "review_comment"]
                disabled_cols = [c for c in all_cols if c not in editable_cols]

                edited_df = st.data_editor(
                    display_res_df,
                    column_config={
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
                else:
                    st.text("No results data.")

