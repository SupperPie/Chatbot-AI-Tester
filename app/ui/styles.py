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
