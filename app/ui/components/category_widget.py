"""目录管理 Widget - 支持增删改操作"""
import streamlit as st
from app.database import SessionLocal, DATABASE_SCHEMA
from app.services.category_service import CategoryService
from app.models.category import Category
from sqlalchemy import text

def get_db_session():
    """获取数据库会话"""
    db = SessionLocal()
    db.execute(text(f"SET search_path TO {DATABASE_SCHEMA}, public"))
    return db

import streamlit_antd_components as sac

def render_category_widget():
    """
    渲染目录管理 Widget
    返回当前选中的目录 ID
    """
    try:
        db = get_db_session()
        service = CategoryService(db)
        tree = service.get_tree()

        if 'selected_category' not in st.session_state:
            st.session_state.selected_category = '__all__'

        with st.container():
            # 自定义样式：
            # 1. 隐藏 popover 默认的下箭头符号
            # 2. 改变 popover 展开后的气泡宽度，让其变窄
            # 3. 设置树形目录容器的固定高度和滚动条
            st.markdown("""
            <style>
            /* 隐藏 popover button 里面的下箭头图标 (svg) */
            button[data-testid="stPopoverButton"] svg {
                display: none !important;
            }
            
            /* 当 popover 展开时，改变 button 的背景色和颜色 */
            button[data-testid="stPopoverButton"][aria-expanded="true"] {
                background-color: #E6F4EA !important;
                border-color: #1890FF !important;
                color: #1890FF !important;
            }

            /* 修改 popover 弹出框的最小宽度和 padding，只对当前组件内的生效 */
            .gear-popover-container div[data-testid="stPopoverBody"] {
                min-width: 120px !important;
                width: 140px !important;
                padding: 10px !important;
            }
            
            /* 树形容器：隐藏默认滚动条，使用细滚动条更美观 */
            div[data-testid="stVerticalBlock"] > div.element-container > div.stHtml {
                /* Optional custom styling for the container */
            }
            </style>
            """, unsafe_allow_html=True)

            # 调整标题和设置按钮的布局：2 列，标题 + 齿轮按钮同行
            col_title, col_action = st.columns([5, 1])
            with col_title:
                st.markdown('<h3 style="white-space: nowrap; margin: 0; padding: 0; line-height: 2;">📂 Category</h3>', unsafe_allow_html=True)

            with col_action:
                st.markdown('<div class="gear-popover-container">', unsafe_allow_html=True)
                with st.popover("⚙️", use_container_width=True):
                    if st.button("➕ 新建", key="btn_add_cat", use_container_width=True):
                        st.session_state.show_add_category_dialog = True
                        st.session_state.add_category_parent_id = None if st.session_state.get('selected_category') == 'root' else st.session_state.get('selected_category')
                        st.rerun()
                    if st.button("✏️ 重命名", disabled=(st.session_state.get('selected_category') == 'root'), key="btn_rename_cat", use_container_width=True):
                        st.session_state.show_rename_dialog = True
                        st.session_state.rename_category_id = st.session_state.get('selected_category')
                        cat_obj = service.db.query(Category).filter(Category.id == st.session_state.rename_category_id).first()
                        st.session_state.rename_category_name = cat_obj.name if cat_obj else ""
                        st.rerun()
                    if st.button("🗑️ 删除", disabled=(st.session_state.get('selected_category') == 'root'), key="btn_del_cat", use_container_width=True):
                        st.session_state.show_delete_dialog = True
                        st.session_state.delete_category_id = st.session_state.get('selected_category')
                        cat_obj = service.db.query(Category).filter(Category.id == st.session_state.delete_category_id).first()
                        st.session_state.delete_category_name = cat_obj.name if cat_obj else ""
                        st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            # 渲染树（包裹在一个固定高度可滚动的 container 里，高度与右侧 Filter 区域底部近似对齐）
            with st.container(height=260, border=False):
                selected_id = _render_tree(tree, service)

            _handle_dialogs(service)

        db.close()
        return st.session_state.get('selected_category', selected_id)

    except Exception as e:
        st.error(f"目录加载失败: {e}")
        return '__all__'


def _render_tree(tree: list, service: CategoryService):
    """渲染目录树 (sac.tree)"""
    current_selected_id = st.session_state.get('selected_category', '__all__')

    index_map = {}
    id_to_index = {}
    current_index = 0

    # 顶层"全部用例"包装节点，表示不筛选
    index_map[current_index] = '__all__'
    id_to_index['__all__'] = current_index
    current_index += 1

    def build_sac_tree(nodes):
        nonlocal current_index
        items = []
        for node in nodes:
            case_count = service.get_case_count(node['id'])
            icon = "folder-fill" if node.get('children') else "folder"
            label = f"{node['name']} ({case_count})"

            index_map[current_index] = node['id']
            id_to_index[node['id']] = current_index
            current_index += 1

            children_items = build_sac_tree(node.get('children', []))
            items.append(
                sac.TreeItem(
                    label=label,
                    icon=icon,
                    children=children_items if children_items else None
                )
            )
        return items

    children_items = build_sac_tree(tree)
    total_count = service.get_total_case_count()
    sac_items = [
        sac.TreeItem(
            label=f"全部用例 ({total_count})",
            icon="house-fill",
            children=children_items if children_items else None
        )
    ]

    default_index = id_to_index.get(current_selected_id, 0)

    selected_index_list = sac.tree(
        items=sac_items,
        index=default_index,
        format_func='title',
        size='sm',
        show_line=True,
        open_all=True,
        return_index=True,
        color='blue',
        key="sac_category_tree"
    )

    new_selected_id = current_selected_id
    if isinstance(selected_index_list, list) and len(selected_index_list) > 0:
        try:
            # sac.tree 在层级节点上可能返回路径索引列表，最后一个才是当前叶子/目标节点
            sel_idx = int(selected_index_list[-1])
            new_selected_id = index_map.get(sel_idx, current_selected_id)
        except (ValueError, TypeError):
            new_selected_id = current_selected_id
    elif isinstance(selected_index_list, int):
        new_selected_id = index_map.get(selected_index_list, current_selected_id)

    if new_selected_id != current_selected_id:
        st.session_state.selected_category = new_selected_id
        st.rerun()

    return st.session_state.get('selected_category', current_selected_id)

def _handle_dialogs(service: CategoryService):
    """处理各种对话框"""
    
    # 新建目录对话框
    if st.session_state.get('show_add_category_dialog', False):
        _add_category_dialog(service)
    
    # 重命名对话框
    if st.session_state.get('show_rename_dialog', False):
        _rename_category_dialog(service)
    
    # 删除对话框
    if st.session_state.get('show_delete_dialog', False):
        _delete_category_dialog(service)

@st.dialog("新建目录")
def _add_category_dialog(service: CategoryService):
    parent_id = st.session_state.get('add_category_parent_id')
    
    if parent_id:
        parent = service.db.query(Category).filter(Category.id == parent_id).first()
        if parent:
            st.info(f"父目录: {parent.path}")
            if parent.level >= 3:
                st.error("已达到最大层级（3级），无法创建子目录")
                if st.button("关闭", use_container_width=True):
                    st.session_state.show_add_category_dialog = False
                    st.rerun()
                return
    else:
        st.info("将创建顶级目录")
    
    name = st.text_input("目录名称", max_chars=100, key="new_category_name")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("取消", use_container_width=True):
            st.session_state.show_add_category_dialog = False
            st.rerun()
    with col2:
        if st.button("创建", type="primary", use_container_width=True):
            if name and name.strip():
                try:
                    service.create(name.strip(), parent_id)
                    st.toast(f"✅ 目录 '{name}' 创建成功！")
                    st.session_state.show_add_category_dialog = False
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
            else:
                st.warning("请输入目录名称")

@st.dialog("重命名目录")
def _rename_category_dialog(service: CategoryService):
    cat_id = st.session_state.get('rename_category_id')
    old_name = st.session_state.get('rename_category_name', '')
    
    new_name = st.text_input("新名称", value=old_name, max_chars=100, key="rename_input")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("取消", use_container_width=True):
            st.session_state.show_rename_dialog = False
            st.rerun()
    with col2:
        if st.button("保存", type="primary", use_container_width=True):
            if new_name and new_name.strip():
                if new_name.strip() != old_name:
                    try:
                        service.update(cat_id, new_name.strip())
                        st.toast(f"✅ 已重命名为 '{new_name}'")
                        st.session_state.show_rename_dialog = False
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                else:
                    st.session_state.show_rename_dialog = False
                    st.rerun()
            else:
                st.warning("名称不能为空")

@st.dialog("确认删除")
def _delete_category_dialog(service: CategoryService):
    cat_id = st.session_state.get('delete_category_id')
    cat_name = st.session_state.get('delete_category_name', '')
    
    # 检查用例数量
    case_count = service.get_case_count(cat_id)
    
    st.warning(f"确定要删除目录 **{cat_name}** 吗？")
    
    if case_count > 0:
        st.error(f"⚠️ 该目录下有 **{case_count}** 个测试用例，无法删除！请先移除或转移用例。")
        if st.button("关闭", use_container_width=True):
            st.session_state.show_delete_dialog = False
            st.rerun()
        return
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("取消", use_container_width=True):
            st.session_state.show_delete_dialog = False
            st.rerun()
    with col2:
        if st.button("🗑️ 确认删除", type="primary", use_container_width=True):
            try:
                service.delete(cat_id)
                st.toast(f"✅ 目录 '{cat_name}' 已删除")
                # 如果删除的是当前选中的目录，切换到 root
                if st.session_state.get('selected_category') == cat_id:
                    st.session_state.selected_category = '__all__'
                    st.session_state.sac_category_tree = [0]
                st.session_state.show_delete_dialog = False
                st.rerun()
            except ValueError as e:
                st.error(str(e))
