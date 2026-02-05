import streamlit as st

def apply_custom_styles():
    st.markdown("""
    <style>
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
        
        /* GLOBAL: Primary Buttons - Yellow Gradient (Eva Theme) */
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
        
        /* Yellow/Gold gradient for ALL sidebar buttons - using more specific selectors */
        section[data-testid="stSidebar"] button,
        section[data-testid="stSidebar"] .stButton > button,
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button,
        [data-testid="stSidebar"] button[kind="secondary"],
        [data-testid="stSidebar"] button[kind="primary"] {
            background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%) !important;
            background-color: #FFD700 !important;
            color: #333 !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            height: 42px !important;
            transition: all 0.2s !important;
            box-shadow: 0 2px 8px rgba(255, 215, 0, 0.4) !important;
        }
        section[data-testid="stSidebar"] button:hover,
        section[data-testid="stSidebar"] .stButton > button:hover,
        [data-testid="stSidebar"] button[kind="secondary"]:hover,
        [data-testid="stSidebar"] button[kind="primary"]:hover {
            background: linear-gradient(135deg, #FFC300 0%, #FF8C00 100%) !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 12px rgba(255, 195, 0, 0.6) !important;
        }
        /* Focus state */
        section[data-testid="stSidebar"] button:focus {
            background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%) !important;
            box-shadow: 0 0 0 3px rgba(255, 215, 0, 0.3) !important;
        }

        /* --- Custom Button Colors for Testcases Actions --- */
        
        /* Run Range Button (Column 4) -> Green */
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(4) button {
            background: linear-gradient(135deg, #42e695 0%, #3bb2b8 100%) !important;
            color: white !important;
            border: none !important;
            box-shadow: 0 2px 6px rgba(66, 230, 149, 0.3) !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(4) button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(66, 230, 149, 0.5) !important;
        }

        /* Run Selected Button (Column 5) -> Purple */
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(5) button {
            background: linear-gradient(135deg, #c471ed 0%, #f64f59 100%) !important; /* Berry gradient */
            background: linear-gradient(135deg, #8E2DE2 0%, #4A00E0 100%) !important; /* Deep Purple */
            color: white !important;
            border: none !important;
            box-shadow: 0 2px 6px rgba(138, 43, 226, 0.3) !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(5) button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(138, 43, 226, 0.5) !important;
        }
    </style>
    """, unsafe_allow_html=True)
