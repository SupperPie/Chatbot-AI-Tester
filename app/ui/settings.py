import streamlit as st
import pandas as pd
import json
from chat_client import load_api_configs, get_chat_response

def render_settings_page():
    st.title("⚙️ API Configuration")
    st.info("Manage the API endpoints used by TestMate.")
    
    # Load configs
    configs = load_api_configs()
    
    st.subheader("Endpoint List")
    
    # Convert dict to list for editor
    data_list = []
    for name, details in configs.items():
        data_list.append({
            "Name": name,
            "URL": details.get("url", ""),
            "Description": details.get("description", ""),
            "Type": details.get("type", "bundle"),
            "Token": details.get("token", "")
        })
    
    # If empty, provide empty row
    if not data_list:
         data_list = [{"Name": "", "URL": "", "Description": "", "Type": "bundle", "Token": ""}]
         
    df_config = pd.DataFrame(data_list)
    
    st.caption("💡 **Token** field is only needed for `dify` type APIs (Bearer app token, e.g. `app-xxxxx`).")
    
    edited_df = st.data_editor(
        df_config,
        num_rows="dynamic",
        column_config={
            "Name": st.column_config.TextColumn("API Name", required=True),
            "URL": st.column_config.TextColumn("Endpoint URL", required=True, width="large"),
            "Description": st.column_config.TextColumn("Description"),
            "Type": st.column_config.SelectboxColumn(
                "Type",
                options=["bundle", "skills", "flight", "limo", "dify", "dify_workflow", "agent_qa", "hotel", "ai_engineering", "translation"],
                default="bundle",
                help="dify = Dify /v1/chat-messages; dify_workflow = Dify Workflow API; ai_engineering = AI Engineering 流式接口; skills/bundle/limo/flight/agent_qa/hotel = internal APIs"
            ),
            "Token": st.column_config.TextColumn("Token (Dify/Workflow)", help="Dify: Bearer token (app-xxx); Workflow: x-app-code|x-app-passport"),
        },
        use_container_width=True,
        key="settings_api_editor"
    )
    
    if st.button("💾 Save Changes", type="primary", key="btn_save_config"):
        # Convert back to dict
        new_configs = {}
        for _, row in edited_df.iterrows():
             name = row.get("Name")
             if name and str(name).strip():
                 entry = {
                     "url": row.get("URL"),
                     "description": row.get("Description"),
                     "type": row.get("Type")
                 }
                 token = str(row.get("Token", "")).strip()
                 if token:
                     entry["token"] = token
                 new_configs[str(name).strip()] = entry
        
        # Save to file
        try:
            from chat_client import CONFIG_FILE
            config_path = CONFIG_FILE
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(new_configs, f, indent=4, ensure_ascii=False)
            st.success("Configuration saved successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save configuration: {e}")

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
