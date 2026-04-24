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

        /* 'Run by Tags' button special styling */
        /* Use nth-child selector to target the button in the specific column if possible, 
           or rely on global primary styling */
        
        /* GLOBAL: Primary Buttons - 恢复原有亮色调 */
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

        /* GLOBAL: Secondary Buttons - 增强色彩但保持柔和 */
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
        
        /* ACTIVE State (Primary) - Pale Yellow/Creamy Gold */
        section[data-testid="stSidebar"] button[kind="primary"] {
            background: linear-gradient(135deg, #FFF8E1 0%, #FFECB3 100%) !important;
            border: 1px solid #FFD54F !important;
            color: #5D4037 !important; /* Brownish text for contrast */
            font-weight: 700 !important;
            box-shadow: 0 2px 5px rgba(255, 213, 79, 0.3) !important;
            transition: all 0.2s ease !important;
        }
        
        section[data-testid="stSidebar"] button[kind="primary"]:hover {
            background: linear-gradient(135deg, #FFECB3 0%, #FFE082 100%) !important;
            transform: translateX(2px) !important;
            box-shadow: 0 3px 8px rgba(255, 213, 79, 0.4) !important;
        }

        /* INACTIVE State (Secondary) - White with visible border */
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
        
        /* Common button properties */
        section[data-testid="stSidebar"] button {
             border-radius: 8px !important;
             height: 45px !important;
             margin-bottom: 5px !important;
             width: 100% !important;
             justify-content: flex-start !important; /* Left align text */
             padding-left: 20px !important;
        }

        /* Delete 按钮单独红色强调 */
        button[aria-label="🗑️ Delete"],
        button[aria-label="Delete"] {
            background: linear-gradient(135deg, #F7C1C1 0%, #EE9A9A 100%) !important;
            color: #5F1F1F !important;
            border: 1px solid #E28787 !important;
            box-shadow: 0 2px 6px rgba(180, 80, 80, 0.28) !important;
        }
        button[aria-label="🗑️ Delete"]:hover,
        button[aria-label="Delete"]:hover {
            background: linear-gradient(135deg, #F2A9A9 0%, #E98383 100%) !important;
            color: #4E1414 !important;
            box-shadow: 0 3px 10px rgba(180, 80, 80, 0.35) !important;
        }

        /* --- Custom Color Accent for Testcases Action Row (丰富页面色彩) --- */
        /* 说明：仅对主内容区横向按钮组生效，侧边栏按钮已在上方单独覆盖 */

        /* 绿色系强调按钮（例如 Move / 当前页选择等位置） */
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(2) button {
            background: linear-gradient(135deg, #9BE7C4 0%, #6FD6A8 100%) !important;
            color: #173F33 !important;
            border: 1px solid #63C79B !important;
        }

        /* 紫蓝系强调按钮（例如 Import / 部分操作按钮位置） */
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(5) button {
            background: linear-gradient(135deg, #D8CCFF 0%, #BDA9FF 100%) !important;
            color: #2F2556 !important;
            border: 1px solid #A894EF !important;
        }
    </style>
    """, unsafe_allow_html=True)
