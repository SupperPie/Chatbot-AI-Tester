import streamlit as st
import nest_asyncio
import logging
from pathlib import Path

# 统一配置日志（只在入口配置一次）
# 第三方库用 WARNING 级别，避免 watchdog 等库产生大量 DEBUG 日志
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# 只对本项目的模块启用 DEBUG
for module in ['app', 'chat_client', '__main__']:
    logging.getLogger(module).setLevel(logging.DEBUG)

# Apply Layout immediately
_ICON_PATH = Path(__file__).resolve().parent / "app" / "ui" / "icon.jpeg"
_PAGE_ICON = str(_ICON_PATH) if _ICON_PATH.exists() else "🤖"
st.set_page_config(layout="wide", page_title="AI Test Manager", page_icon=_PAGE_ICON)

# Apply nest_asyncio
nest_asyncio.apply()

# Import UI Modules
from app.ui.styles import apply_custom_styles
from app.ui.sidebar import render_sidebar
from app.ui.tester import render_tester_page
from app.ui.testcases import render_testcases_page
from app.ui.report import render_report_page
from app.ui.settings import render_settings_page

# Main Entry Point
def main():
    # 1. Apply Styles
    apply_custom_styles()
    
    # 2. Render Sidebar (handles navigation state)
    render_sidebar()
    
    # 3. Routing
    if "current_page" not in st.session_state:
        st.session_state.current_page = "Tester"
        
    page = st.session_state.current_page
    
    if page == "Tester":
        render_tester_page()
    elif page == "Testcases":
        render_testcases_page()
    elif page == "Test Report":
        render_report_page()
    elif page == "Assertions":
        from app.ui.assertions import render_assertions_page
        render_assertions_page()
    elif page == "Settings":
        render_settings_page()
    elif page == "Blind Review":
        from app.ui.blind_review import render_blind_review_page
        render_blind_review_page()

if __name__ == "__main__":
    main()
