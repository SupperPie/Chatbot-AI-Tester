import streamlit as st


def apply_custom_styles():
    st.markdown("""
    <style>
        /* Reduce Top Margin for All Pages */
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 1.5rem !important;
        }

        /* Modern Table Styling */
        div[data-testid="stDataFrame"] > div {
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid #f0f0f0;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }
        
        /* Metric Cards */
        div[data-testid="stMetric"] {
            background: white;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            border: 1px solid #eee;
        }

        /* Buttons & Actions */
        .stButton button {
            border-radius: 8px;
            transition: all 0.2s;
        }
        
        /* GLOBAL: Primary Buttons */
        button[kind="primary"] {
            background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%) !important;
            color: #333 !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            box-shadow: 0 2px 8px rgba(255, 215, 0, 0.4) !important;
        }
        button[kind="primary"]:hover {
            background: linear-gradient(135deg, #FFA500 0%, #FFD700 100%) !important;
            color: #333 !important;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(255, 215, 0, 0.5) !important;
        }
        button[kind="primary"]:focus {
            background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%) !important;
            color: #333 !important;
            box-shadow: 0 0 0 3px rgba(255, 215, 0, 0.3) !important;
        }

        /* GLOBAL: Secondary Buttons */
        button[kind="secondary"] {
            background: linear-gradient(135deg, #DFF1FF 0%, #C5E3FF 100%) !important;
            color: #1F3B57 !important;
            border: 1px solid #A6CDEE !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            box-shadow: 0 2px 6px rgba(95, 150, 210, 0.25) !important;
        }
        button[kind="secondary"]:hover {
            background: linear-gradient(135deg, #CFE9FF 0%, #B5DAFF 100%) !important;
            color: #17314D !important;
            transform: translateY(-1px);
            box-shadow: 0 3px 10px rgba(95, 150, 210, 0.32) !important;
        }
        
        /* --- Sidebar Layout --- */
        section[data-testid="stSidebar"] {
            width: 250px !important;
            min-width: 250px !important;
            max-width: 250px !important;
        }

        /* --- Sidebar Navigation Buttons --- */
        section[data-testid="stSidebar"] button[kind="primary"] {
            background: linear-gradient(135deg, #FFF8E1 0%, #FFECB3 100%) !important;
            border: 1px solid #FFD54F !important;
            color: #5D4037 !important;
            font-weight: 700 !important;
            box-shadow: 0 2px 5px rgba(255, 213, 79, 0.3) !important;
            transition: all 0.2s ease !important;
        }
        section[data-testid="stSidebar"] button[kind="primary"]:hover {
            background: linear-gradient(135deg, #FFECB3 0%, #FFE082 100%) !important;
            transform: translateX(2px) !important;
            box-shadow: 0 3px 8px rgba(255, 213, 79, 0.4) !important;
        }
        section[data-testid="stSidebar"] button[kind="secondary"] {
            background: #FFFFFF !important;
            border: 1px solid #E0E0E0 !important;
            color: #555 !important;
            font-weight: 500 !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
        }
        section[data-testid="stSidebar"] button[kind="secondary"]:hover {
            background: #F5F5F5 !important;
            border-color: #BDBDBD !important;
            color: #333 !important;
            transform: translateX(2px) !important;
        }
        section[data-testid="stSidebar"] button {
             border-radius: 8px !important;
             height: 45px !important;
             margin-bottom: 5px !important;
             width: 100% !important;
             justify-content: flex-start !important;
             padding-left: 20px !important;
        }

        /* ====== 按钮渐变覆盖（通过 Streamlit st-key CSS class 精确定位） ====== */

        /* Delete 按钮 → 红色渐变 */
        .st-key-btn_delete_selected button {
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%) !important;
            color: #fff !important;
            border: 1px solid #e74c3c !important;
            box-shadow: 0 2px 6px rgba(231, 76, 60, 0.35) !important;
        }
        .st-key-btn_delete_selected button:hover {
            background: linear-gradient(135deg, #ee5a24 0%, #ff6b6b 100%) !important;
            color: #fff !important;
            transform: translateY(-1px);
            box-shadow: 0 4px 10px rgba(231, 76, 60, 0.45) !important;
        }

        /* Cancel All 按钮 → 紫色渐变 */
        .st-key-btn_deselect_all button {
            background: linear-gradient(135deg, #b388ff 0%, #7c4dff 100%) !important;
            color: #fff !important;
            border: 1px solid #9575cd !important;
            box-shadow: 0 2px 6px rgba(149, 117, 205, 0.35) !important;
        }
        .st-key-btn_deselect_all button:hover {
            background: linear-gradient(135deg, #7c4dff 0%, #b388ff 100%) !important;
            color: #fff !important;
            transform: translateY(-1px);
            box-shadow: 0 4px 10px rgba(149, 117, 205, 0.45) !important;
        }

        /* Import 按钮 → 绿色渐变（通过 anchor div 相邻兄弟选择器定位） */
        .import-popover-anchor ~ div [data-testid="stPopover"] > button {
            background: linear-gradient(135deg, #66bb6a 0%, #2e7d32 100%) !important;
            color: #fff !important;
            border: 1px solid #388e3c !important;
            box-shadow: 0 2px 6px rgba(56, 142, 60, 0.35) !important;
        }
        .import-popover-anchor ~ div [data-testid="stPopover"] > button:hover {
            background: linear-gradient(135deg, #2e7d32 0%, #66bb6a 100%) !important;
            color: #fff !important;
            transform: translateY(-1px);
            box-shadow: 0 4px 10px rgba(56, 142, 60, 0.45) !important;
        }

        /* ⚙ 齿轮按钮 → 透明无边框（通过 anchor div 相邻兄弟选择器定位） */
        .gear-popover-anchor ~ div [data-testid="stPopover"] > button {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 4px 8px !important;
            min-height: 0 !important;
        }
        .gear-popover-anchor ~ div [data-testid="stPopover"] > button:hover {
            background: rgba(0, 0, 0, 0.04) !important;
            border: none !important;
            box-shadow: none !important;
        }

        /* ⚙ 齿轮 popover 面板 → 紧凑 + 半透明 */
        .gear-popover-anchor ~ div [data-testid="stPopoverBody"] {
            min-width: 0 !important;
            width: auto !important;
            max-width: 130px !important;
            padding: 6px 8px !important;
            background: rgba(255, 255, 255, 0.5) !important;
            backdrop-filter: blur(4px) !important;
        }
        .gear-popover-anchor ~ div [data-testid="stPopoverBody"] button {
            width: 100% !important;
            margin-bottom: 2px !important;
            padding: 4px 10px !important;
            font-size: 13px !important;
        }
    </style>
    """, unsafe_allow_html=True)
