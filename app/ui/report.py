import streamlit as st
import pandas as pd
import json
import os
import time
import math
from app.utils import export_pdf, delete_reports, run_tests_sync, save_history, update_history_entry
from chat_client import get_available_apis


def _read_max_workers(entry_id=None) -> int:
    """读取并发线程数并 clamp 到 1-10。
    优先读取当前 report 的 thread 设置（f"max_workers_{entry_id}"），
    回退到 testcases 页面的全局 page_max_workers_input。
    """
    raw = None
    if entry_id:
        raw = st.session_state.get(f"max_workers_{entry_id}")
    if raw is None:
        raw = st.session_state.get("page_max_workers_input", "3")
    try:
        v = int(str(raw).strip())
    except Exception:
        return 3
    if v < 1:
        return 1
    if v > 10:
        return 10
    return v


@st.dialog("🚀 Rerun - Report Name")
def _rerun_confirm_dialog(entry_id, cases, api_name, case_count):
    """Rerun 前的确认弹窗：输入本次 Test Report 的名称。
    默认值：{endpoint}_{当天日期}_{时间戳}，用户可编辑。
    """
    from datetime import datetime as _dt
    default_name = f"{api_name}_{_dt.now().strftime('%Y%m%d')}_{_dt.now().strftime('%H%M%S')}"

    st.info(f"即将重新执行 **{case_count}** 条测试用例（API: **{api_name}**）")

    report_name = st.text_input(
        "本次 Test Report 名称",
        value=default_name,
        key=f"rerun_report_name_{entry_id}",
        help="显示在 Test Report 页面的报告名称，可自定义编辑"
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("取消", width="stretch"):
            st.session_state.pop(f"confirmed_rerun_{entry_id}", None)
            st.rerun()
    with col2:
        if st.button("▶ 开始执行", type="primary", width="stretch"):
            name = (report_name or "").strip() or default_name
            st.session_state[f"confirmed_rerun_{entry_id}"] = {
                'cases': cases,
                'report_name': name,
            }
            st.rerun()


@st.fragment
def _render_report_table_fragment(entry_id, full_display_df, tbl_key_suffix, all_cols, disabled_cols):
    """表格片段：隔离勾选/编辑导致的重绘范围，避免勾选一行就刷新整个页面。
    内部使用分页，大数据量时每次只渲染 TBL_PAGE_SIZE 行到 data_editor，
    大幅减少前端 DOM 和数据传输量。
    """
    TBL_PAGE_SIZE = 50  # 表格内部分页，每页 50 行

    # 表格分页状态
    pg_key = f"_tbl_pg_{entry_id}"
    if pg_key not in st.session_state:
        st.session_state[pg_key] = 1
    tbl_page = st.session_state[pg_key]

    total_rows = len(full_display_df)
    total_tbl_pages = max(1, math.ceil(total_rows / TBL_PAGE_SIZE))
    if tbl_page > total_tbl_pages:
        tbl_page = total_tbl_pages
        st.session_state[pg_key] = tbl_page

    t_start = (tbl_page - 1) * TBL_PAGE_SIZE
    t_end = min(t_start + TBL_PAGE_SIZE, total_rows)

    # Action Row 2: Select Controls + Pagination
    op_col1, op_col2, op_col3, op_spacer, pg_prev, pg_info, pg_next = st.columns(
        [0.8, 0.8, 0.8, 2, 0.5, 1.2, 0.5]
    )
    with op_col1:
        if st.button("☑ 全选", key=f"btn_select_all_{entry_id}", use_container_width=True):
            st.session_state[f"select_all_{entry_id}"] = True
            st.session_state[f"tbl_ver_{entry_id}"] = st.session_state.get(f"tbl_ver_{entry_id}", 0) + 1
            st.rerun(scope="fragment")
    with op_col2:
        if st.button("☐ 取消", key=f"btn_deselect_all_{entry_id}", use_container_width=True):
            st.session_state[f"select_all_{entry_id}"] = False
            st.session_state[f"tbl_ver_{entry_id}"] = st.session_state.get(f"tbl_ver_{entry_id}", 0) + 1
            st.rerun(scope="fragment")
    with op_col3:
        if total_rows > TBL_PAGE_SIZE:
            st.caption(f"共 {total_rows} 行")
    with pg_prev:
        if st.button("◀", key=f"pg_prev_{entry_id}", disabled=(tbl_page <= 1), use_container_width=True):
            st.session_state[pg_key] = max(1, tbl_page - 1)
            st.rerun(scope="fragment")
    with pg_info:
        st.caption(f"第 {tbl_page}/{total_tbl_pages} 页")
    with pg_next:
        if st.button("▶", key=f"pg_next_{entry_id}", disabled=(tbl_page >= total_tbl_pages), use_container_width=True):
            st.session_state[pg_key] = min(total_tbl_pages, tbl_page + 1)
            st.rerun(scope="fragment")

    # 消费 select_all 状态（应用到全量数据的 Select 列）
    select_all_state = st.session_state.pop(f"select_all_{entry_id}", None)
    if f"rerun_select_{entry_id}" not in st.session_state:
        st.session_state[f"rerun_select_{entry_id}"] = set()
    rerun_select = st.session_state[f"rerun_select_{entry_id}"]
    if select_all_state is True:
        full_display_df["Select"] = True
        rerun_select.clear()
        rerun_select.update(range(total_rows))
    elif select_all_state is False:
        full_display_df["Select"] = False
        rerun_select.clear()

    # 恢复持久化的 Select 状态（跨 fragment rerun 保持勾选）
    for ridx in list(rerun_select):
        if ridx < total_rows:
            full_display_df.at[ridx, "Select"] = True

    # 只取当前页的数据传给 data_editor（大幅减少前端数据量）
    page_df = full_display_df.iloc[t_start:t_end].reset_index(drop=True).copy()

    # 对大文本列做显示截断（只影响表格展示，不修改 full_display_df 原始数据）
    _DISP_TRUNC = 200
    _LONG_COLS = ("input", "expected_output", "actual_output", "retrieval_context",
                  "reason", "assertion_result", "review_comment", "thinking",
                  "inform_base", "raw")
    for _lc in _LONG_COLS:
        if _lc in page_df.columns:
            page_df[_lc] = page_df[_lc].apply(
                lambda v: (str(v)[:_DISP_TRUNC] + "…") if isinstance(v, str) and len(v) > _DISP_TRUNC
                          else ("" if (v is None or (isinstance(v, float) and pd.isna(v))) else v)
            )

    tbl_key = f"hist_tbl_{entry_id}_v{tbl_key_suffix}_p{tbl_page}"
    edited_page_df = st.data_editor(
        page_df,
        column_config={
            "Select": st.column_config.CheckboxColumn("✓", width="small", default=False),
            "case_id": st.column_config.TextColumn("ID", width="small"),
            "priority": st.column_config.TextColumn("Priority", width="small"),
            "module": st.column_config.TextColumn("Module", width="small"),
            "turn_index": st.column_config.NumberColumn("Turn", width="small"),
            "input": st.column_config.TextColumn("Input", width="medium"),
            "expected_output": st.column_config.TextColumn("Expected", width="medium"),
            "actual_output": st.column_config.TextColumn("Actual Output", width="large"),
            "retrieval_context": st.column_config.TextColumn("Retrieval Ctx", width="medium"),
            "thinking": st.column_config.TextColumn("Thinking", width="medium"),
            "inform_base": st.column_config.TextColumn("Inform Base", width="medium"),
            "raw": st.column_config.TextColumn("Raw", width="medium"),
            "score": st.column_config.NumberColumn("Score", format="%.2f", width="small"),
            "passed": st.column_config.CheckboxColumn("Passed", width="small"),
            "review_comment": st.column_config.TextColumn("Comment", width="medium"),
            "ttft": st.column_config.NumberColumn("TTFT", format="%.1f", width="small"),
            "latency": st.column_config.NumberColumn("Latency", format="%.1f", width="small"),
            "reason": st.column_config.TextColumn("Reason", width="medium"),
            "assertion_result": st.column_config.TextColumn("Assertion", width="medium"),
        },
        use_container_width=True,
        disabled=disabled_cols,
        hide_index=True,
        key=tbl_key,
        height=min(600, 35 * max(1, len(page_df)) + 40),
    )

    # 将当前页的编辑（勾选/passed/comment）同步回全量 DataFrame
    editor_state = st.session_state.get(tbl_key, {})
    edited_rows = editor_state.get("edited_rows", {}) if isinstance(editor_state, dict) else {}
    if edited_rows:
        for page_ridx_str, patch in edited_rows.items():
            page_ridx = int(page_ridx_str)
            global_ridx = t_start + page_ridx
            for col, val in patch.items():
                if global_ridx < total_rows:
                    full_display_df.at[global_ridx, col] = val
            if "Select" in patch:
                if patch.get("Select"):
                    rerun_select.add(global_ridx)
                else:
                    rerun_select.discard(global_ridx)

    # 返回全量 DataFrame（带最新勾选状态），供外部 Rerun/Export 使用
    return full_display_df


def render_report_page():
    st.title("📊 Test Report History")

    # 僵尸 Job 检测：每次进入 Report 页时强制扫描一次
    try:
        from app.utils import get_job_manager
        _mgr = get_job_manager()
        _mgr.detect_stale_jobs()  # 显式调用，不依赖 _ensure_initialized 的一次性 flag
    except Exception as e:
        print(f"Warning: stale job detection failed: {e}")

    try:
        from app.services.history_service import HistoryService
        service = HistoryService()
        # 初始加载只获取摘要，不加载 results（性能优化）
        history = service.get_all(include_results=False)
    except Exception as e:
        st.error(f"Error reading history from DB: {e}")
        return

    if not history:
        st.info("No history found.")
        return

    # API Selector for Rerun (只调用一次)
    available_apis = get_available_apis() or ["Bundle API"]

    # --------------------------------------------------
    # Filter Controls
    # --------------------------------------------------
    all_apis_in_history = sorted(set(
        e.get('api_name') or 'Unknown' for e in history
    ))
    api_filter_options = ["All"] + all_apis_in_history

    f_col1, f_col2, f_col3, f_col4 = st.columns([2.2, 2.6, 1.1, 0.5])
    with f_col1:
        filter_date = st.date_input(
            "📅 Date",
            value=None,
            key="rpt_filter_date",
            help="按日期筛选（YYYY/MM/DD）",
        )
    with f_col2:
        filter_api = st.selectbox(
            "🔌 API",
            api_filter_options,
            key="rpt_filter_api",
            help="按接口筛选",
        )
    with f_col3:
        # 每页数量放到 filter 同一行，视觉上属于「查询设置」
        _page_size_default = st.session_state.get("report_page_size", 10)
        _opts = [10, 20, 50]
        if _page_size_default not in _opts:
            _opts.append(_page_size_default)
            _opts.sort()
        new_page_size = st.selectbox(
            "每页",
            _opts,
            index=_opts.index(_page_size_default),
            key="rpt_page_size_sel",
            help="每页显示的报告数量",
        )
        if new_page_size != _page_size_default:
            st.session_state.report_page_size = new_page_size
            st.session_state.report_page = 1
            st.rerun()
    with f_col4:
        # Clear 按钮做成小图标按钮，仅在有生效筛选时高亮
        _has_filter = (
            st.session_state.get("rpt_filter_date") is not None
            or st.session_state.get("rpt_filter_api", "All") != "All"
        )
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button(
            "🗑",
            key="rpt_clear_filters_btn",
            help="清除所有筛选条件",
            type="primary" if _has_filter else "secondary",
            use_container_width=True,
            disabled=not _has_filter,
        ):
            for _k in ['rpt_filter_date', 'rpt_filter_api']:
                if _k in st.session_state:
                    del st.session_state[_k]
            st.session_state.report_page = 1
            st.rerun()

    # Apply filters (preserve original timestamp-desc order)
    filtered_history = history
    if filter_date is not None:
        date_str = filter_date.strftime("%Y-%m-%d")
        filtered_history = [e for e in filtered_history if e.get('timestamp', '')[:10] == date_str]
    if filter_api != "All":
        filtered_history = [e for e in filtered_history
                            if (e.get('api_name') or 'Unknown') == filter_api]

    if not filtered_history:
        st.info("No reports match the current filters.")
        return

    # --------------------------------------------------
    # Pagination
    # --------------------------------------------------
    if 'report_page' not in st.session_state:
        st.session_state.report_page = 1
    if 'report_page_size' not in st.session_state:
        st.session_state.report_page_size = 10

    # Reset to page 1 when filters change
    prev_filter_key = f"__rpt_prev_filter_{filter_date}_{filter_api}"
    if prev_filter_key not in st.session_state:
        st.session_state[prev_filter_key] = True
        st.session_state.report_page = 1

    page_size = st.session_state.report_page_size
    total = len(filtered_history)
    total_pages = max(1, math.ceil(total / page_size))
    if st.session_state.report_page > total_pages:
        st.session_state.report_page = total_pages

    page = st.session_state.report_page
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total)
    page_history = filtered_history[start_idx:end_idx]

    # Stats row（Per page 已合并到 filter 栏）
    _active_bits = []
    if filter_date is not None:
        _active_bits.append(f"📅 {filter_date.strftime('%Y-%m-%d')}")
    if filter_api != "All":
        _active_bits.append(f"🔌 {filter_api}")
    _active_str = f" · 筛选：{' | '.join(_active_bits)}" if _active_bits else ""
    st.caption(
        f"Showing {start_idx + 1}–{end_idx} of {total} reports{_active_str} · Expand a report to view details."
    )

    # Check if any job is running to decide on auto-refresh
    any_running = any(e.get("status") == "running" for e in page_history)
    if any_running:
        if st.button("🔄 Refresh Progress"):
            st.rerun()

    for i, entry in enumerate(page_history):
        entry_id = entry.get('id')
        status = entry.get('status', 'completed')
        
        passed_count = entry.get('passed', 0)
        total_count = entry.get('total', 0)
        
        # Stats display
        api_name = entry.get('api_name') or 'Unknown'
        ts = entry.get('timestamp', '')
        dur = entry.get('duration', '')
        dur_part = f" [{dur}]" if dur else ""
        # 自定义报告名（Run 弹窗中输入），显示在标签最前面
        report_name = entry.get('report_name')
        name_part = f"{report_name} | " if report_name else ""

        if status == "running":
            # Estimate or use started_count if available
            started = entry.get('started_count', 0)
            # Total might be initial count, or updated.
            # Avoid div by zero
            if total_count == 0: total_count = 1
            progress = min(started / total_count, 1.0)

            label = f"⏳ {name_part}{ts}{dur_part} - Running... {started}/{total_count} - API: {api_name}"
        elif status == "interrupted":
            started = entry.get('started_count', 0)
            remaining = total_count - started if total_count > started else 0
            label = f"🔴 {name_part}{ts}{dur_part} - Interrupted {started}/{total_count} (remaining {remaining}) - API: {api_name}"
        elif status == "cancelled":
            started = entry.get('started_count', 0)
            remaining = total_count - started if total_count > started else 0
            label = f"⏸ {name_part}{ts}{dur_part} - Cancelled {started}/{total_count} (remaining {remaining}) - API: {api_name}"
        elif status == "failed":
            started = entry.get('started_count', 0)
            label = f"❌ {name_part}{ts}{dur_part} - Failed {started}/{total_count} - API: {api_name}"
        else:
            pass_rate = (passed_count / total_count * 100) if total_count > 0 else 0
            label = f"{name_part}{ts}{dur_part} - Pass Rate: {pass_rate:.1f}% ({passed_count}/{total_count}) - API: {api_name}"
        
        with st.expander(label):
            # 懒加载+缓存：展开时才加载 results 详情，并缓存到 session_state 避免每次交互都查DB
            cache_key = f"entry_detail_cache_{entry_id}"
            # running 状态下每次都刷新（进度需要）；completed 等终态走缓存
            if status == "running" or cache_key not in st.session_state:
                entry_detail = service.get_by_id(entry_id)
                if entry_detail:
                    entry = entry_detail
                    if status != "running":
                        st.session_state[cache_key] = entry_detail
            else:
                entry = st.session_state[cache_key]
            
            # SHOW PROGRESS BAR IF RUNNING
            if status == "running":
                st.progress(progress, text=f"Processing {started}/{total_count} cases...")
                st.info("Results are loading in real-time. Click Refresh above to update table.")
            elif status in ("interrupted", "failed"):
                err_msg = entry.get('error_message') or "Job was interrupted unexpectedly."
                st.warning(f"⚠️ {err_msg}")
                if entry.get('case_ids'):
                    completed_n = entry.get('started_count', 0)
                    total_n = entry.get('total', 0)
                    remaining = total_n - completed_n if total_n > completed_n else 0
                    if remaining > 0:
                        st.info(f"已完成 {completed_n}/{total_n} 条，剩余 {remaining} 条可通过 Continue 续跑。")
                        st.caption("提示：并发执行时已完成的用例不一定按 ID 顺序排列，remaining 按集合差集计算。")
                else:
                    st.caption("此 Job 创建于功能上线前，无 case_ids 快照，仅支持 Rerun。")
            elif status == "cancelled":
                if entry.get('case_ids'):
                    completed_n = entry.get('started_count', 0)
                    total_n = entry.get('total', 0)
                    remaining = total_n - completed_n if total_n > completed_n else 0
                    if remaining > 0:
                        st.info(f"已取消。已完成 {completed_n}/{total_n}，剩余 {remaining} 条可通过 Continue 续跑。")
                        st.caption("提示：并发执行时已完成的用例不一定按 ID 顺序排列，remaining 按集合差集计算。")

            # --------------------------
            # Action Buttons Row 1: Report Management
            # --------------------------
            mgmt_col1, mgmt_col2, mgmt_col3, mgmt_col4 = st.columns([3.5, 1, 1.5, 1])
            
            with mgmt_col1:
                # API SELECTOR + 执行模式选择 + Thread并发数（Rerun/Continue 使用）
                api_col, mode_col, thread_col = st.columns([2.2, 1.3, 0.8])
                with api_col:
                    stored_api = entry.get("api_name", "Bundle API")
                    default_idx = 0
                    if stored_api in available_apis:
                        default_idx = available_apis.index(stored_api)
                    st.selectbox("API", options=available_apis, index=default_idx, key=f"api_sel_{entry_id}", label_visibility="collapsed")
                with mode_col:
                    mode_key = f"exec_mode_{entry_id}"
                    if mode_key not in st.session_state:
                        # 默认用上一次全局选择，否则用 full
                        st.session_state[mode_key] = st.session_state.get("execution_mode_select", "full (语义+断言)")
                    st.selectbox(
                        "执行模式",
                        ["full (语义+断言)", "semantic (仅语义)", "assertion (仅断言)"],
                        key=mode_key,
                        label_visibility="collapsed",
                    )
                with thread_col:
                    thread_key = f"max_workers_{entry_id}"
                    if thread_key not in st.session_state:
                        # 默认继承 testcases 页的全局设置
                        st.session_state[thread_key] = st.session_state.get("page_max_workers_input", "3")
                    st.text_input(
                        "Thread",
                        key=thread_key,
                        placeholder="1-10",
                        label_visibility="collapsed",
                        help="并发线程数（1-10，默认 3）。多轮对话仍串行执行。",
                    )

            with mgmt_col2:
                # DELETE BUTTON
                confirm_key = f"confirm_del_{entry_id}"
                if confirm_key not in st.session_state:
                    st.session_state[confirm_key] = False
                
                if not st.session_state[confirm_key]:
                    if st.button("🗑️ Delete", key=f"btn_del_{entry_id}", use_container_width=True):
                        st.session_state[confirm_key] = True
                        st.rerun()
                else:
                    col_confirm, col_cancel = st.columns([1, 1])
                    if col_confirm.button("✅", key=f"btn_conf_{entry_id}"):
                        if delete_reports([entry_id]):
                            st.success("Deleted.")
                            del st.session_state[confirm_key]
                            st.rerun()
                    if col_cancel.button("❌", key=f"btn_canc_{entry_id}"):
                         st.session_state[confirm_key] = False
                         st.rerun()

            with mgmt_col3:
                # RERUN / CONTINUE / STOP BUTTON
                if status == "running":
                    # STOP BUTTON
                    if st.button("🛑 Stop Job", key=f"btn_stop_{entry_id}", use_container_width=True):
                        from app.utils import get_job_manager
                        mgr = get_job_manager()
                        mgr.cancel_job(entry_id)
                        st.warning("Stopping job... please wait.")
                        time.sleep(1)
                        st.rerun()
                else:
                    # CONTINUE 按钮：仅当 status ∈ {cancelled, interrupted, failed} 且有 case_ids 时显示
                    can_continue = (
                        status in ("cancelled", "interrupted", "failed")
                        and bool(entry.get("case_ids"))
                        and (entry.get("total", 0) - entry.get("started_count", 0) > 0)
                    )
                    if can_continue:
                        btn_col_a, btn_col_b = st.columns([1, 1])
                        with btn_col_a:
                            if st.button("▶ Continue", key=f"btn_cont_{entry_id}", use_container_width=True, help="从断点续跑，结果合并到当前 report"):
                                from app.utils import get_job_manager
                                mgr = get_job_manager()
                                result = mgr.continue_job(entry_id, max_workers=_read_max_workers(entry_id))
                                if result.get("ok"):
                                    st.success(result.get("message", "Continue started"))
                                else:
                                    st.error(result.get("message", "Continue failed"))
                                time.sleep(1)
                                st.rerun()
                        with btn_col_b:
                            rerun_clicked = st.button("⟳ Rerun", key=f"btn_rerun_{entry_id}", use_container_width=True)
                    else:
                        rerun_clicked = st.button("▶ Rerun", key=f"btn_rerun_{entry_id}", use_container_width=True)
                    
                    if rerun_clicked:
                        # 延迟到 data_editor 渲染后再消费，读取用户勾选
                        st.session_state[f"pending_rerun_{entry_id}"] = True
            with mgmt_col4:
                # EXPORT TO FEISHU BUTTON
                if status != "running":
                    feishu_key = f"feishu_export_{entry_id}"
                    if st.button("📤 飞书", key=f"btn_feishu_{entry_id}", help="导出到飞书表格", use_container_width=True):
                        st.session_state[feishu_key] = True
                        st.rerun()
                    
                    if st.session_state.get(feishu_key):
                        with st.form(key=f"feishu_form_{entry_id}"):
                            feishu_url = st.text_input(
                                "飞书表格 URL",
                                value="https://dragonpass.feishu.cn/wiki/QKLQwwM0BixcMjkTZWVc4Wvmnoh?sheet=eRNryN",
                                help="粘贴飞书表格链接"
                            )
                            submitted = st.form_submit_button("确认导出")
                            if submitted:
                                try:
                                    from app.feishu_client import export_report_to_feishu, parse_feishu_url
                                    parsed = parse_feishu_url(feishu_url)
                                    results = entry.get('results', [])
                                    report_api_name = entry.get('api_name', 'Test')
                                    if results:
                                        est_batches = max(1, (len(results) + 19) // 20)
                                        est_sec = est_batches * 2  # 每批约含0.8s首延迟+0.3s间隔
                                        with st.spinner(f"正在导出 {len(results)} 条记录到飞书（约 {est_batches} 批，预计 {est_sec}-{est_sec+10} 秒）..."):
                                            export_result = export_report_to_feishu(
                                                results,
                                                spreadsheet_token=parsed.get("spreadsheet_token"),
                                                sheet_id=parsed.get("sheet_id"),
                                                wiki_token=parsed.get("wiki_token"),
                                                api_name=report_api_name,
                                                create_new_sheet=True
                                            )
                                        if export_result.get("success"):
                                            st.success(f"✅ {export_result.get('message')}")
                                        else:
                                            st.error(export_result.get("message"))
                                    else:
                                        st.warning("没有测试结果可导出")
                                    st.session_state[feishu_key] = False
                                except Exception as e:
                                    st.error(f"导出失败: {e}")
                        
                        if st.button("取消", key=f"btn_feishu_cancel_{entry_id}"):
                            st.session_state[feishu_key] = False
                            st.rerun()


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
                        # 多轮：继承外层 case 的整体 score/passed（ConversationalGEval 给的是整段对话的分，
                        # 每个 turn 没有单独评分，不能用 t.get("score",0) 兜底成 0，否则会误覆盖成 failed）
                        outer_score = float(row.get("score", 0)) if pd.notna(row.get("score")) else 0.0
                        outer_passed = bool(row.get("passed", False))
                        for idx, t in enumerate(row["turns"]):
                            new_row = row.copy().to_dict()
                            new_row["turn_index"] = t.get("turn", idx + 1)
                            new_row["input"] = t.get("user", "")
                            new_row["expected_output"] = t.get("expected", "")
                            new_row["actual_output"] = t.get("actual", "")
                            
                            is_manual = t.get("manual_review", False)
                            if is_manual:
                                new_row["passed"] = t.get("passed", outer_passed)
                                if t.get("score") is not None:
                                    new_row["score"] = t.get("score")
                            else:
                                # 1) turn 自己有 passed（未来扩展 turn 级评分/断言）→ 用 turn 的
                                if "passed" in t and t.get("passed") is not None:
                                    new_row["passed"] = bool(t["passed"])
                                    if t.get("score") is not None:
                                        new_row["score"] = float(t["score"])
                                else:
                                    # 2) turn 无 passed → 继承外层整体判定（不是 score>=0.5 重算，
                                    #    因为 full 模式下 passed 已经考虑了断言结果）
                                    new_row["passed"] = outer_passed
                                    t_score = t.get("score")
                                    if t_score is not None and not (isinstance(t_score, float) and pd.isna(t_score)):
                                        new_row["score"] = float(t_score)
                                    else:
                                        new_row["score"] = outer_score
                            
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
                            # 优先用执行层算好的 passed（full 模式下包含断言结果），
                            # 只有 passed 缺失（老数据）时才用 score>=0.5 兜底
                            if "passed" in row_dict and row_dict.get("passed") is not None:
                                row_dict["passed"] = bool(row_dict["passed"])
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

                # 将 assertion_detail 展开为可读的列
                if "assertion_detail" in display_res_df.columns:
                    def _format_assertion_detail(val):
                        if not val or (isinstance(val, float) and pd.isna(val)):
                            return ""
                        if isinstance(val, dict):
                            results = val.get("results", [])
                            if not results:
                                return "✅" if val.get("passed") else "❌"
                            parts = []
                            for r in results:
                                icon = "✅" if r.get("passed") else "❌"
                                parts.append(f"{icon} {r.get('component_name', '?')}: {r.get('message', '')}")
                            return " | ".join(parts)
                        return str(val) if val else ""
                    display_res_df["assertion_result"] = display_res_df["assertion_detail"].apply(_format_assertion_detail)
                else:
                    display_res_df["assertion_result"] = ""

                # Configure standard columns order
                target_cols = [
                    "Select", "case_id", "priority", "module", "turn_index", "input", "expected_output", "actual_output", "retrieval_context",
                    "score", "passed", "assertion_result", "ttft", "latency", "reason",
                    "review_comment", "thinking", "inform_base", "raw"
                ]
                # Ensure Select exists
                if "Select" not in display_res_df.columns:
                    display_res_df.insert(0, "Select", False)

                # Only keep columns that exist in the dataframe to prevent KeyError
                display_cols = [c for c in target_cols if c in display_res_df.columns]
                
                # 优化: 当 thinking / inform_base 列全为空时，自动隐藏整列
                def _col_all_empty(df, col):
                    if col not in df.columns:
                        return True
                    s = df[col]
                    # 视为空: NaN / None / 空字符串 / 仅空白
                    return s.fillna("").astype(str).str.strip().eq("").all()
                
                for _hide_col in ("thinking", "inform_base"):
                    if _hide_col in display_cols and _col_all_empty(display_res_df, _hide_col):
                        display_cols.remove(_hide_col)
                
                # Keep Select if we need it, but we don't use Select in history table right now.
                display_res_df = display_res_df[display_cols]
                
                # --------------------------
                # Table Fragment（隔离勾选/编辑导致的重绘，只刷新表格区域）
                # 注意：大文本列截断在 fragment 内部的 page_df 上做（仅显示用），
                # 返回的 full_display_df 保持原始完整文本，供 Rerun/Update 操作使用。
                # --------------------------
                tbl_key_suffix = st.session_state.get(f"tbl_ver_{entry_id}", 0)
                all_cols = display_res_df.columns.tolist()
                editable_cols = ["Select", "passed", "review_comment"]
                disabled_cols = [c for c in all_cols if c not in editable_cols]

                edited_df = _render_report_table_fragment(
                    entry_id, display_res_df, tbl_key_suffix, all_cols, disabled_cols
                )


                # --------------------------
                # Consume pending Rerun (must run AFTER data_editor so we can read Select column)
                # --------------------------
                # 弹窗确认后的 Rerun 执行（_rerun_confirm_dialog 设置）
                _confirmed_rerun = st.session_state.pop(f"confirmed_rerun_{entry_id}", None)
                if _confirmed_rerun:
                    try:
                        from app.utils import get_job_manager
                        mgr = get_job_manager()
                        target_api = st.session_state.get(f"api_sel_{entry_id}", "Bundle API")
                        _mode_raw = st.session_state.get(f"exec_mode_{entry_id}", "full (语义+断言)")
                        _mode_val = _mode_raw.split(" ")[0]  # "full" / "semantic" / "assertion"
                        job_id = mgr.run_background_job(
                            _confirmed_rerun['cases'],
                            api_name=target_api,
                            execution_mode=_mode_val,
                            max_workers=_read_max_workers(entry_id),
                            report_name=_confirmed_rerun.get('report_name'),
                        )
                        st.success(f"Rerun started for {len(_confirmed_rerun['cases'])} case(s)! Job ID: {job_id}")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Rerun failed: {e}")

                elif st.session_state.pop(f"pending_rerun_{entry_id}", False):
                    if edited_df is None or edited_df.empty:
                        st.warning("No results to rerun.")
                    else:
                        selected_rerun = edited_df[edited_df["Select"] == True]
                        if selected_rerun.empty:
                            st.warning("Please select at least one case to rerun (check the Select column).")
                        else:
                            from app.utils import load_data
                            main_df = load_data()

                            cases_to_rerun = []
                            for _, row in selected_rerun.iterrows():
                                cid = row.get("case_id")
                                mask = (main_df['id'] == cid)
                                if mask.any():
                                    live_rows = main_df[mask]
                                    if len(live_rows) > 1:
                                        for _, m_row in live_rows.iterrows():
                                            cases_to_rerun.append(m_row.to_dict())
                                    else:
                                        cases_to_rerun.append(live_rows.iloc[0].to_dict())
                                else:
                                    cases_to_rerun.append({
                                        "id": cid,
                                        "input": row.get("input", ""),
                                        "expected_output": row.get("expected_output", ""),
                                        "type": row.get("type", "single_turn"),
                                        "turns": row.get("turns", []),
                                        "priority": row.get("priority"),
                                        "module": row.get("module"),
                                        "category": row.get("category"),
                                    })

                            seen = set()
                            unique_cases_to_rerun = []
                            for c in cases_to_rerun:
                                t_idx = str(c.get("turn_index", "0"))
                                unique_key = f"{c.get('id')}_{t_idx}"
                                if unique_key not in seen:
                                    seen.add(unique_key)
                                    unique_cases_to_rerun.append(c)

                            # 弹出 Report Name 确认框（默认 endpoint_日期_时间戳，可编辑）
                            target_api = st.session_state.get(f"api_sel_{entry_id}", "Bundle API")
                            st.session_state.pop(f"rerun_report_name_{entry_id}", None)
                            _rerun_confirm_dialog(entry_id, unique_cases_to_rerun, target_api, len(unique_cases_to_rerun))


                # --------------------------
                # Action Row 3: Data Operations (below table)
                # --------------------------
                act_col1, act_col2, act_col3 = st.columns([2, 2, 2])
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
                            from app.utils import load_data, save_records
                            main_df = load_data()
                            
                            updated_cases = 0
                            total_rows = len(selected_rows)
                            progress_bar = st.progress(0, text=f"Updating 0/{total_rows}...")
                            
                            modified_records = []
                            for i, (_, sel_row) in enumerate(selected_rows.iterrows()):
                                cid = sel_row['case_id']
                                tidx = sel_row.get('turn_index')
                                new_val = sel_row['actual_output']
                                
                                if pd.isna(tidx) or tidx is None:
                                    mask = (main_df['id'] == cid)
                                else:
                                    mask = (main_df['id'] == cid) & (main_df['turn_index'] == int(tidx))
                                    
                                if mask.any():
                                    main_df.loc[mask, 'expected_output'] = new_val
                                    updated_cases += mask.sum()
                                    modified_records.extend(
                                        main_df.loc[mask].drop(columns=["Select"], errors='ignore').to_dict(orient="records")
                                    )
                                
                                progress_bar.progress((i + 1) / total_rows, text=f"Updating {i + 1}/{total_rows}...")
                            
                            progress_bar.progress(1.0, text="Saving...")
                            if updated_cases > 0:
                                # 增量写入测试用例 DB（只写变更行，避免全量 upsert 上万条记录导致保存缓慢）
                                saved_count = save_records(modified_records)

                                # 同步更新 history entry 中的 expected 值：
                                # 报告页表格数据来自 history，不同步的话刷新后仍显示旧值
                                current_results = entry.get('results', [])
                                selected_case_ids = set(selected_rows['case_id'])
                                for res in current_results:
                                    if res.get('case_id') not in selected_case_ids:
                                        continue
                                    case_sel_rows = selected_rows[selected_rows['case_id'] == res.get('case_id')]
                                    turns = res.get('turns')
                                    if isinstance(turns, list) and turns:
                                        # 多轮：更新对应 turn 的 expected
                                        for t in turns:
                                            for _, sel_row in case_sel_rows.iterrows():
                                                _ti = sel_row.get('turn_index')
                                                if _ti is not None and not pd.isna(_ti) and int(_ti) == t.get('turn'):
                                                    t['expected'] = sel_row['actual_output']
                                    else:
                                        # 单轮：直接更新 expected_output
                                        for _, sel_row in case_sel_rows.iterrows():
                                            _ti = sel_row.get('turn_index')
                                            if _ti is None or pd.isna(_ti):
                                                res['expected_output'] = sel_row['actual_output']
                                update_history_entry(entry_id, current_results)

                                # 让 Test Cases 页面下次进入时强制从 DB 重新加载
                                st.session_state["_force_reload"] = True

                                progress_bar.empty()
                                if saved_count < len(modified_records):
                                    st.warning(f"注意: {len(modified_records) - saved_count} 条写入 DB 失败，请查看服务端日志")
                                st.success(f"Successfully updated Expected Output for {updated_cases} rows.")
                                time.sleep(1)
                                st.rerun()
                            else:
                                progress_bar.empty()
                                st.warning("No matching test cases found in reality to update.")

                with act_col3:
                    if st.button("💾 Save Changes", key=f"btn_save_{entry_id}", use_container_width=True):
                        try:
                            current_results = entry.get('results', [])
                            updates = {}
                            if not edited_df.empty:
                                for _, row in edited_df.iterrows():
                                    updates[row['case_id']] = {
                                        'passed': row.get('passed'),
                                        'review_comment': row.get('review_comment')
                                    }
                            
                            updated_count = 0
                            for res in current_results:
                                cid = res.get('case_id')
                                if cid in updates:
                                    res['passed'] = bool(updates[cid].get('passed', False))
                                    res['review_comment'] = str(updates[cid].get('review_comment', ""))
                                    res['manual_review'] = True
                                    
                                    if "turns" in res and isinstance(res["turns"], list):
                                        for t in res["turns"]:
                                            t['passed'] = res['passed']
                                            t['manual_review'] = True
                                            
                                    updated_count += 1
                            
                            if update_history_entry(entry_id, current_results):
                                st.success(f"Saved {updated_count} cases!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Failed to save changes.")
                        except Exception as e:
                            st.error(f"Error saving: {e}")
            
            else:
                if status == "running":
                    st.info("Waiting for first result...")
                elif status == "failed":
                    error_msg = entry.get("error", "Unknown error")
                    st.error(f"❌ Job failed: {error_msg}")
                    st.caption("Check server terminal logs for full traceback. Common causes: deepeval not installed, missing .env variables, or API connection issues.")
                else:
                    st.text("No results data.")

    # --------------------------------------------------
    # Bottom Pagination Controls
    # --------------------------------------------------
    if total_pages > 1:
        st.divider()
        p_col1, p_col2, p_col3 = st.columns([1, 2, 1])
        with p_col1:
            if st.button("← Prev", disabled=(page <= 1), use_container_width=True):
                st.session_state.report_page -= 1
                st.rerun()
        with p_col2:
            st.markdown(
                f'<p style="text-align:center; margin-top:6px;">Page {page} of {total_pages}</p>',
                unsafe_allow_html=True
            )
        with p_col3:
            if st.button("Next →", disabled=(page >= total_pages), use_container_width=True):
                st.session_state.report_page += 1
                st.rerun()

