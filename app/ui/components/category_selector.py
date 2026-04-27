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
        return [('root', '全部用例')]

def get_category_ids_with_children(category_id: str) -> list:
    """获取目录及其所有子目录的 ID 列表
    
    对于 'root'（顶层全部用例节点），只返回 ['root']，
    仅显示直接归属 root 的用例，不递归展开所有子目录。
    """
    if category_id == 'root':
        return ['root']

    try:
        db = SessionLocal()
        db.execute(text(f"SET search_path TO {DATABASE_SCHEMA}, public"))
        service = CategoryService(db)
        
        # 获取当前目录
        from app.models.category import Category
        category = db.query(Category).filter(Category.id == category_id).first()
        if not category:
            db.close()
            return [category_id]
        
        # 获取当前目录 + 所有子目录
        children = db.query(Category.id).filter(
            (Category.id == category_id) | (Category.path.like(f"{category.path}/%"))
        ).all()
        
        result = [c[0] for c in children]
        db.close()
        return result
    except Exception as e:
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
