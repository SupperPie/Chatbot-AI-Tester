import streamlit as st
import streamlit_antd_components as sac

if 'selected_node' not in st.session_state:
    st.session_state.selected_node = 'A'

st.write("Current selected:", st.session_state.selected_node)

items = [
    sac.TreeItem('A'),
    sac.TreeItem('B'),
    sac.TreeItem('C')
]

idx_map = {0: 'A', 1: 'B', 2: 'C'}

selected_id = st.session_state.selected_node
default_index = [k for k, v in idx_map.items() if v == selected_id][0]

selected = sac.tree(items=items, index=default_index, key='my_tree')

if selected:
    new_id = idx_map.get(selected[0])
    if new_id != selected_id:
        st.session_state.selected_node = new_id
        st.rerun()
        
st.write("Returned:", new_id if selected else None)
