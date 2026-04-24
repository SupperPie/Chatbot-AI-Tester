import streamlit as st
from app.models.category import Category

@st.dialog("新建目录")
def create_category_dialog(service, parent_id=None):
    name = st.text_input("目录名称", max_chars=100)
    
    if parent_id:
        parent = service.db.query(Category).filter(Category.id == parent_id).first()
        st.info(f"将创建在: {parent.path}")
    else:
        st.info("将创建顶级目录")
        
    col1, col2 = st.columns(2)
    with col1:
        if st.button("取消", use_container_width=True):
            st.session_state.show_create_dialog = False
            st.rerun()
    with col2:
        if st.button("创建", type="primary", use_container_width=True):
            if name.strip():
                try:
                    service.create(name.strip(), parent_id)
                    st.toast(f"✅ 目录 '{name}' 创建成功!")
                    st.session_state.show_create_dialog = False
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
            else:
                st.warning("名称不能为空")

@st.dialog("确认删除")
def delete_category_dialog(service, cat_id):
    category = service.db.query(Category).filter(Category.id == cat_id).first()
    if not category:
        st.error("目录不存在")
        return
        
    count = service.get_case_count(cat_id)
    
    st.warning(f"确定要删除目录 **{category.name}** 吗？")
    if count > 0:
        st.error(f"⚠️ 这将同时删除该目录及子目录下的 **{count}** 个测试用例！此操作不可撤销！")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("取消", use_container_width=True):
            st.session_state.show_delete_dialog = False
            st.rerun()
    with col2:
        if st.button("🗑️ 确认删除", type="primary", use_container_width=True):
            try:
                affected = service.delete(cat_id)
                st.toast(f"✅ 已删除目录及 {affected} 个测试用例")
                st.session_state.selected_category = 'root'
                st.session_state.show_delete_dialog = False
                st.rerun()
            except Exception as e:
                st.error(f"删除失败: {str(e)}")

@st.dialog("重命名目录")
def rename_category_dialog(service, cat_id):
    category = service.db.query(Category).filter(Category.id == cat_id).first()
    if not category:
        st.error("目录不存在")
        return
        
    name = st.text_input("新名称", value=category.name, max_chars=100)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("取消", use_container_width=True):
            st.session_state.show_rename_dialog = False
            st.rerun()
    with col2:
        if st.button("保存", type="primary", use_container_width=True):
            if name.strip() and name.strip() != category.name:
                try:
                    service.update(cat_id, name.strip())
                    st.toast(f"✅ 目录已重命名为 '{name}'")
                    st.session_state.show_rename_dialog = False
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
            elif name.strip() == category.name:
                st.session_state.show_rename_dialog = False
                st.rerun()
            else:
                st.warning("名称不能为空")
