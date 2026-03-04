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
            "Type": details.get("type", "bundle")
        })
    
    # If empty, provide empty row
    if not data_list:
         data_list = [{"Name": "", "URL": "", "Description": "", "Type": "bundle"}]
         
    df_config = pd.DataFrame(data_list)
    
    edited_df = st.data_editor(
        df_config,
        num_rows="dynamic",
        column_config={
            "Name": st.column_config.TextColumn("API Name", required=True),
            "URL": st.column_config.TextColumn("Endpoint URL", required=True, width="large"),
            "Description": st.column_config.TextColumn("Description"),
            "Type": st.column_config.SelectboxColumn("Type", options=["bundle", "airport", "skills", "flight", "limo"], default="bundle")
        },
        use_container_width=True,
        key="settings_api_editor"
    )
    
    if st.button("💾 Save Changes", type="primary", key="btn_save_config"):
        # Convert back to dict
        new_configs = {}
        for _, row in edited_df.iterrows():
             name = row.get("Name")
             if name and str(name).strip(): # Ensure valid name
                 new_configs[str(name).strip()] = {
                     "url": row.get("URL"),
                     "description": row.get("Description"),
                     "type": row.get("Type")
                 }
        
        # Save to file
        try:
            config_path = "data/api_config.json"
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
    
    with debug_col2:
        test_msg = st.text_input("Test Message", value="Hello, World!", key="debug_msg_input")
        
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
