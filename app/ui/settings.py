import streamlit as st
import pandas as pd
import json
import time
from chat_client import load_api_configs, get_chat_response

def render_settings_page():
    st.title("⚙️ API Configuration")
    st.info("Manage the API endpoints used by TestMate.")
    
    # Load configs (DB first, JSON fallback)
    configs = load_api_configs()
    
    # 显示上次保存的结果消息（与标题同行）
    title_col, msg_col = st.columns([1, 3])
    with title_col:
        st.subheader("Endpoint List")
    with msg_col:
        if "settings_save_msg" in st.session_state:
            msg_type, msg_text = st.session_state.settings_save_msg
            if msg_type == "success":
                st.success(msg_text)
            elif msg_type == "warning":
                st.warning(msg_text)
            elif msg_type == "error":
                st.error(msg_text)
            # 显示后清除，避免下次刷新时还显示
            del st.session_state.settings_save_msg
    
    # Convert dict to list for editor
    data_list = []
    for name, details in configs.items():
        rp = details.get("request_params") or {}
        rp_str = json.dumps(rp, ensure_ascii=False) if rp else ""
        token = details.get("token") or ""
        if token == "None":
            token = ""
        data_list.append({
            "Name": name,
            "URL": details.get("url", ""),
            "Description": details.get("description", ""),
            "Type": details.get("type", "bundle"),
            "Token": token,
            "Request Params": rp_str,
        })
    
    # If empty, provide empty row
    if not data_list:
         data_list = [{"Name": "", "URL": "", "Description": "", "Type": "bundle", "Token": "", "Request Params": ""}]
         
    df_config = pd.DataFrame(data_list)
    
    st.caption("💡 **Token**: `dify` 类型填 Bearer token (app-xxx)；`dify_workflow` 填 x-app-code|x-app-passport。**Request Params**: JSON 格式自定义请求参数，留空使用 Type 默认值。")
    
    edited_df = st.data_editor(
        df_config,
        num_rows="dynamic",
        column_config={
            "Name": st.column_config.TextColumn("API Name", required=True),
            "URL": st.column_config.TextColumn("Endpoint URL", required=True, width="large"),
            "Description": st.column_config.TextColumn("Description"),
            "Type": st.column_config.SelectboxColumn(
                "Type",
                options=["bundle", "skills", "flight", "flight_agent", "esim_agent", "faq_zzairport", "dc_qa", "limo", "dify", "dify_workflow", "agent_qa", "hotel", "fitness", "ai_engineering", "entitlements", "translation", "trip_planner", "portal_im"],
                default="bundle",
                help="portal_im = 公网 IM 门户接口 (conversation/init + sendStreamMsg，Supervisor 自动路由所有 agent，token 为用户登录 JWT); dify = Dify /v1/chat-messages; dify_workflow = Dify Workflow API; ai_engineering = AI Engineering 流式接口; entitlements = 权益查询; trip_planner = 行程规划 (data.summary_state.details); fitness = 健身场馆查询; esim_agent = eSIM Agent 查询; faq_zzairport = FAQ郑州机场; dc_qa = DC问答; flight_agent = Flight Agent 航班查询; skills/bundle/limo/flight/agent_qa/hotel = internal APIs"
            ),
            "Token": st.column_config.TextColumn("Token (Dify/Workflow/Portal)", help="Dify: Bearer token (app-xxx); Workflow: x-app-code|x-app-passport; portal_im: JWT token（header: token，有效期短需定期更新）"),
            "Request Params": st.column_config.TextColumn("Request Params (JSON)", help="自定义请求参数，JSON 格式。留空则使用 Type 默认值。", width="large"),
        },
        use_container_width=True,
        key="settings_api_editor"
    )
    
    if st.button("💾 Save Changes", type="primary", key="btn_save_config"):
        # Convert back to dict
        new_configs = {}
        has_error = False
        error_messages = []  # 收集所有错误消息
        
        for _, row in edited_df.iterrows():
             name = row.get("Name")
             if name and str(name).strip():
                 # 清理 pandas NaN 占位符
                 def _clean(v):
                     if v is None:
                         return ""
                     s = str(v).strip()
                     if s.lower() in ("none", "nan", "null"):
                         return ""
                     return s
                 entry = {
                     "url": _clean(row.get("URL", "")),
                     "description": _clean(row.get("Description", "")),
                     "type": _clean(row.get("Type", "")) or "bundle",
                 }
                 token = _clean(row.get("Token", ""))
                 entry["token"] = token
                 # Parse request_params JSON
                 rp_raw = row.get("Request Params", "")
                 rp_str = "" if rp_raw is None else str(rp_raw).strip()
                 # 过滤无效占位符（pandas NaN -> 'nan', 空值 -> 'none' 等）
                 if rp_str and rp_str.lower() not in ("none", "nan", "null"):
                     try:
                         rp = json.loads(rp_str)
                         if not isinstance(rp, dict):
                             error_messages.append(f"❌ '{name}' 的 Request Params 必须是 JSON 对象（dict），当前类型: {type(rp).__name__}")
                             has_error = True
                             continue
                         entry["request_params"] = rp
                     except json.JSONDecodeError as e:
                         error_messages.append(f"❌ '{name}' 的 Request Params JSON 解析失败: {e}")
                         has_error = True
                         continue
                 else:
                     entry["request_params"] = {}
                 new_configs[str(name).strip()] = entry
        
        if has_error:
            error_summary = "⚠️ 保存失败，请修正以下错误：\n" + "\n".join(error_messages)
            st.session_state.settings_save_msg = ("error", error_summary)
            st.rerun()

        # 保存到 DB + JSON 双写
        db_success = False
        json_success = False
        
        try:
            from app.services.api_config_service import ApiConfigService
            service = ApiConfigService()
            service.save_all(new_configs)
            db_success = True
        except Exception as e:
            pass  # 在最后统一反馈

        try:
            from chat_client import CONFIG_FILE
            # JSON 备份：去掉 request_params 为空 dict 的字段以保持兼容
            json_configs = {}
            for k, v in new_configs.items():
                entry = {kk: vv for kk, vv in v.items()}
                if not entry.get("request_params"):
                    entry.pop("request_params", None)
                if not entry.get("token"):
                    entry.pop("token", None)
                json_configs[k] = entry
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(json_configs, f, indent=4, ensure_ascii=False)
            json_success = True
        except Exception as e:
            pass  # 在最后统一反馈
        
        # 根据保存结果设置消息到 session_state，rerun 后在标题旁显示
        if db_success and json_success:
            st.session_state.settings_save_msg = ("success", "✅ Configuration saved successfully! (DB + JSON)")
        elif db_success:
            st.session_state.settings_save_msg = ("success", "✅ Saved to DB (JSON failed, but configs work)")
        elif json_success:
            st.session_state.settings_save_msg = ("warning", "⚠️ Saved to JSON only (DB save failed)")
        else:
            st.session_state.settings_save_msg = ("error", "❌ Failed to save to both DB and JSON. Check logs.")
        
        st.rerun()

    st.divider()
    
    # Debug Section
    st.subheader("🛠️ Debug / Test Connectivity")
    
    debug_col1, debug_col2 = st.columns([1, 3])
    with debug_col1:
        test_api_name = st.selectbox("Select API to Test", options=list(configs.keys()), key="debug_api_select")
    
    # 根据API类型提供不同的默认测试消息
    default_messages = {
        "hotel": "帮我预定广州酒店",
        "flight": "查询北京到上海的航班",
        "limo": "我需要接机服务",
        "skills": "机场贵宾厅服务",
        "ai_engineering": "你好，这是一条测试消息",
        "translation": "OK, the order has been placed for you.",
    }
    api_type = configs.get(test_api_name, {}).get("type", "bundle") if test_api_name else "bundle"
    default_msg = default_messages.get(api_type, "Hello, World!")
    
    # 初始化或检测API切换时更新测试消息
    if "last_debug_api" not in st.session_state:
        st.session_state.last_debug_api = test_api_name
        st.session_state.debug_msg_input = default_msg
    elif st.session_state.last_debug_api != test_api_name:
        st.session_state.last_debug_api = test_api_name
        st.session_state.debug_msg_input = default_msg
        
    with debug_col2:
        test_msg = st.text_input("Test Message", key="debug_msg_input")
        
    if st.button("🚀 Send Request", key="btn_debug_send"):
        if not test_api_name:
            st.warning("Please select an API.")
        else:
            with st.spinner(f"Sending request to {test_api_name}..."):
                try:
                    # Force reload to pick up any changes in chat_client.py
                    import importlib
                    import chat_client
                    importlib.reload(chat_client)
                    
                    response = chat_client.get_chat_response(test_msg, api_name=test_api_name)
                    st.markdown("### Response:")
                    st.info(response)
                except Exception as e:
                    st.error(f"Request Failed: {e}")
