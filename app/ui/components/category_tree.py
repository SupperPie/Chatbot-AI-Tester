import streamlit as st
from app.services.category_service import CategoryService

def render_category_tree(db_session):
    """渲染目录树组件，返回选中的目录 ID"""
    service = CategoryService(db_session)
    tree = service.get_tree()
    
    # 获取当前选中的目录
    if 'selected_category' not in st.session_state:
        st.session_state.selected_category = 'root'
    selected_id = st.session_state.selected_category
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("### 📂 测试目录")
    with col2:
        if st.button("➕", help="新建顶级目录", key="btn_create_root_cat"):
            st.session_state.show_create_dialog = True
            st.session_state.create_parent_id = None
            st.rerun()
            
    st.divider()

    # 自定义样式让按钮左对齐
    st.markdown(
        """
        <style>
        div[data-testid="stVerticalBlock"] > div > div > div > div > button {
            justify-content: flex-start !important;
            padding-left: 10px !important;
        }
        </style>
        """, 
        unsafe_allow_html=True
    )
    
    def render_node(node, indent=0):
        # 实时获取最新用例数
        count = service.get_case_count(node['id'])
        
        icon = "📁" if node['children'] else "📄"
        if node['id'] == 'root':
            icon = "🏠"
            
        prefix = "　" * indent
        btn_label = f"{prefix}{icon} {node['name']} ({count})"
        button_type = "primary" if node['id'] == selected_id else "secondary"
        
        col_btn, col_menu = st.columns([5, 1])
        with col_btn:
            if st.button(btn_label, key=f"cat_btn_{node['id']}", use_container_width=True, type=button_type):
                st.session_state.selected_category = node['id']
                st.rerun()
                
        with col_menu:
            if node['id'] != 'root':
                with st.popover("⋮"):
                    if st.button("✏️ 重命名", key=f"rename_{node['id']}", use_container_width=True):
                        st.session_state.show_rename_dialog = True
                        st.session_state.rename_category_id = node['id']
                        st.rerun()
                        
                    if node['level'] < 3:
                        if st.button("➕ 添加子目录", key=f"addchild_{node['id']}", use_container_width=True):
                            st.session_state.show_create_dialog = True
                            st.session_state.create_parent_id = node['id']
                            st.rerun()
                            
                    if st.button("🗑️ 删除", key=f"delete_{node['id']}", use_container_width=True):
                        st.session_state.show_delete_dialog = True
                        st.session_state.delete_category_id = node['id']
                        st.rerun()
        
        # 递归渲染子节点
        if node.get('children'):
            for child in node['children']:
                render_node(child, indent + 1)
                
    # 渲染根目录及其子节点
    for node in tree:
        if node['level'] == 1:
            render_node(node)
            
    return selected_id
