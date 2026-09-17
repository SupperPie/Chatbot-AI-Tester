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
        
        def flatten_tree(nodes):
            for node in nodes:
                # 用完整 path 显示，避免同名不同父节点（如 subagent/Q&A 与 中信/Q&A）
                # 在下拉框中显示完全相同、无法区分导致选错目录
                display_name = f"📁 {node['path']}"
                options.append((node['id'], display_name))
                if node.get('children'):
                    flatten_tree(node['children'])

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

    # 直接以 ID 作为 options，通过 format_func 显示名称。
    # 避免通过 label 反查 index（同名 label 时 .index() 只会命中第一个，导致选错）
    option_ids = [opt[0] for opt in options]
    id_to_label = {opt[0]: opt[1] for opt in options}

    # 获取当前选中的目录
    current_id = st.session_state.get('selected_category', 'root')
    current_index = option_ids.index(current_id) if current_id in option_ids else 0

    selected_id = st.selectbox(
        "📁 目录筛选",
        options=option_ids,
        index=current_index,
        format_func=lambda x: id_to_label.get(x, x),
        key="category_selector"
    )

    st.session_state.selected_category = selected_id
    return selected_id
