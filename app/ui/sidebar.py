import streamlit as st

def render_sidebar():
    with st.sidebar:
        # Beautified Title with robot avatar (Eva-style)
        st.markdown("""
        <div style="text-align: center; padding: 20px 0;">
            <h1 style="
                background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-size: 2.5rem;
                font-weight: 800;
                margin: 0;
                letter-spacing: -1px;
            ">🤖 TestMate</h1>
            <p style="color: #888; font-size: 0.85rem; margin-top: 5px;">AI Testing Platform</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.divider()
        
        # Initialize page state
        if "current_page" not in st.session_state:
            st.session_state.current_page = "Tester"
        
        # Tester button (first option)
        if st.button(
            "🔧 Tester", 
            use_container_width=True, 
            type="primary" if st.session_state.current_page == "Tester" else "secondary",
            key="nav_tester"
        ):
            st.session_state.current_page = "Tester"
            st.rerun()
        
        # Testcases button
        if st.button(
            "📋 Testcases", 
            use_container_width=True, 
            type="primary" if st.session_state.current_page == "Testcases" else "secondary",
            key="nav_testcases"
        ):
            st.session_state.current_page = "Testcases"
            st.rerun()
        
        # Test Report button
        if st.button(
            "📊 Test Report", 
            use_container_width=True,
            type="primary" if st.session_state.current_page == "Test Report" else "secondary",
            key="nav_report"
        ):
            st.session_state.current_page = "Test Report"
            st.rerun()
        
        # Assertions button
        if st.button(
            "🧩 Assertions",
            use_container_width=True,
            type="primary" if st.session_state.current_page == "Assertions" else "secondary",
            key="nav_assertions"
        ):
            st.session_state.current_page = "Assertions"
            st.rerun()

        # Settings button
        if st.button(
            "⚙️ Settings", 
            use_container_width=True,
            type="primary" if st.session_state.current_page == "Settings" else "secondary",
            key="nav_settings"
        ):
            st.session_state.current_page = "Settings"
            st.rerun()

        # Blind Review button
        if st.button(
            "🙈 Blind Review", 
            use_container_width=True,
            type="primary" if st.session_state.current_page == "Blind Review" else "secondary",
            key="nav_blind_review"
        ):
            st.session_state.current_page = "Blind Review"
            st.rerun()
        
        # Footer
        st.markdown("<br>" * 5, unsafe_allow_html=True)
        st.caption("© 2026 DragonPass AI Team")
