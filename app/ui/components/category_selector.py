"""目录选择组件 - 简化版（下拉框形式）"""
import streamlit as st
from app.database import SessionLocal, DATABASE_SCHEMA
from app.services.category_service import CategoryService
from sqlalchemy import text

def get_category_options():
    """获取目录选项列表，用于下拉框"""
    try:
        db = SessionLocal()
        db.execute(text(f"SET search_path TO {DATABASE_SCHEMA}, public"))
        service = CategoryService(db)
        tree = service.get_tree()
        
        options = []
        
        def flatten_tree(nodes, prefix=""):
            for node in nodes:
                indent = "　" * (node['level'] - 1)
                display_name = f"{indent}{node['name']}"
                options.append((node['id'], display_name))
                if node.get('children'):
                    flatten_tree(node['children'], prefix + "  ")

        flatten_tree(tree)
        db.close()
        return options
    except Exception as e:
        st.error(f"获取目录列表失败: {e}")
        print(f"[get_category_options] ERROR: {e}")
        return [('root', '全部用例')]

def get_category_ids_with_children(category_id: str) -> list:
    """获取目录 ID 列表

    用户选中某目录时，只显示该目录下的用例，不展开子目录。
    （目录统计数量逻辑在 category_widget.py 中独立维护）
    """
    if category_id == 'root':
        return ['root']

    # 只返回当前目录 ID，不展开子目录
    return [category_id]

def render_category_selector():
    """渲染目录选择下拉框，返回选中的目录 ID"""
    options = get_category_options()
    
    # 构建选项
    option_ids = [opt[0] for opt in options]
    option_names = [opt[1] for opt in options]
    
    # 获取当前选中的目录
    current_id = st.session_state.get('selected_category', 'root')
    current_index = option_ids.index(current_id) if current_id in option_ids else 0
    
    selected_name = st.selectbox(
        "📁 目录筛选",
        options=option_names,
        index=current_index,
        key="category_selector"
    )
    
    # 根据名称找到 ID
    selected_index = option_names.index(selected_name)
    selected_id = option_ids[selected_index]
    
    st.session_state.selected_category = selected_id
    return selected_id
