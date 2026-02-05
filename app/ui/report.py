import streamlit as st
import pandas as pd
import json
import os
import time
from app.utils import HISTORY_JSON, export_pdf, delete_reports, run_tests_sync, save_history
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
            
            with ac_col3:
                # PDF EXPORT (Only if results exist)
                res_df = pd.DataFrame(entry.get('results', []))
                if not res_df.empty:
                    if st.button("📄 PDF", key=f"btn_pdf_{entry_id}"):
                        pdf_data = export_pdf(res_df) 
                        st.download_button(
                             label="Download",
                             data=pdf_data,
                             file_name=f"report_{entry_id}.pdf",
                             mime="application/pdf",
                             key=f"dl_pdf_{entry_id}"
                        )

            with ac_col4:
                # API SELECTOR
                st.selectbox("API", options=available_apis, key=f"api_sel_{entry_id}", label_visibility="collapsed")
            
            st.divider()

            # --------------------------
            # Data View
            # --------------------------
            res_df = pd.DataFrame(entry.get('results', []))
            
            if not res_df.empty:
                display_res_df = res_df.copy()
                if "type" in display_res_df.columns:
                    def format_output(row):
                         if row.get("type") == "multi_turn" and isinstance(row.get("turns"), list):
                             summary = []
                             for t in row["turns"]:
                                 status = "✅" if t.get("passed") else "❌"
                                 summary.append(f"T{t.get('turn')} {status}: Q: {t.get('user')} | A: {t.get('actual')}")
                             return "\n".join(summary)
                         return row.get("actual_output")
                    
                    if "turns" in display_res_df.columns:
                        display_res_df["actual_output"] = display_res_df.apply(format_output, axis=1)

                st.data_editor(
                    display_res_df,
                    column_config={
                        "case_id": st.column_config.TextColumn("ID", width="small"),
                        "input": st.column_config.TextColumn("Input", width="medium"),
                        "expected_output": st.column_config.TextColumn("Expected", width="medium"),
                        "actual_output": st.column_config.TextColumn("Actual Output", width="large"),
                        "thinking": st.column_config.TextColumn("Thinking Process", width="large"),
                        "passed": st.column_config.CheckboxColumn("Passed", width="small"),
                        "score": st.column_config.NumberColumn("Score", format="%.2f"),
                        "latency": st.column_config.NumberColumn("Response Time", format="%.2f s"),
                        "reason": st.column_config.TextColumn("Reason", width="large"),
                    },
                    use_container_width=True,
                    disabled=True,
                    hide_index=True,
                    key=f"hist_tbl_{entry_id}"
                )
            else:
                if status == "running":
                    st.info("Waiting for first result...")
                else:
                    st.text("No results data.")

