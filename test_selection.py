import streamlit as st
import pandas as pd

st.title("Selection Test")

df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})

try:
    # Try using on_select with data_editor
    # Note: st.data_editor returns the edited dataframe usually.
    # If on_select is present, does it change return?
    # Or do we access selection via session state?
    
    st.write("Attempting st.data_editor with on_select...")
    # We use a key to check session state
    result = st.data_editor(
        df, 
        key="editor_test",
        on_change=None,
        selection_mode="multi-row",
        on_select="rerun" 
    )
    
    st.write("Return Type:", type(result))
    st.write("Session State:", st.session_state.get("editor_test"))
    
    selection = st.session_state.get("editor_test", {}).get("selection", {})
    st.write("Selection:", selection)
    
except Exception as e:
    st.error(f"Error: {e}")
