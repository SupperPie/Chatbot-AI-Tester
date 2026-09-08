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


def _load_all_counts(service: CategoryService) -> dict:
    """一次性加载所有目录的 case count，返回 {cat_id: count, '__total__': total}"""
    from app.models.test_case import TestCase
    from sqlalchemy import func

    # 按 category_id 分组统计（包括多轮对话的每个 turn）
    rows = service.db.query(
        TestCase.category_id, func.count(TestCase.id)
    ).group_by(TestCase.category_id).all()

    counts = {}
    total = 0
    for cat_id, cnt in rows:
        counts[cat_id or 'root'] = cnt
        total += cnt
    counts['__total__'] = total
    return counts

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
                    selected_cat_id = st.session_state.get('selected_category')
                    selected_cat_obj = service.db.query(Category).filter(Category.id == selected_cat_id).first() if selected_cat_id not in (None, '__all__', 'root') else None

                    if st.button("➕ 新建", key="btn_add_cat", use_container_width=True):
                        st.session_state.show_add_category_dialog = True
                        st.session_state.add_category_parent_id = None if st.session_state.get('selected_category') == 'root' else st.session_state.get('selected_category')
                        st.rerun()

                    if st.button("✏️ 重命名", disabled=(selected_cat_obj is None), key="btn_rename_cat", use_container_width=True):
                        st.session_state.show_rename_dialog = True
                        st.session_state.rename_category_id = selected_cat_id
                        st.session_state.rename_category_name = selected_cat_obj.name if selected_cat_obj else ""
                        st.rerun()

                    if st.button("⬆️ 上移", disabled=(selected_cat_obj is None), key="btn_move_up_cat", use_container_width=True):
                        try:
                            siblings = service.db.query(Category).filter(Category.parent_id == selected_cat_obj.parent_id).order_by(Category.sort_order, Category.id).all()
                            ids = [c.id for c in siblings]
                            idx = ids.index(selected_cat_obj.id)
                            if idx > 0:
                                ids[idx - 1], ids[idx] = ids[idx], ids[idx - 1]
                                service.reorder_siblings(selected_cat_obj.parent_id, ids)
                                st.session_state.pop('category_counts_cache', None)
                                st.toast("✅ 已上移")
                                st.rerun()
                        except Exception as e:
                            st.error(f"上移失败: {e}")

                    if st.button("⬇️ 下移", disabled=(selected_cat_obj is None), key="btn_move_down_cat", use_container_width=True):
                        try:
                            siblings = service.db.query(Category).filter(Category.parent_id == selected_cat_obj.parent_id).order_by(Category.sort_order, Category.id).all()
                            ids = [c.id for c in siblings]
                            idx = ids.index(selected_cat_obj.id)
                            if idx < len(ids) - 1:
                                ids[idx], ids[idx + 1] = ids[idx + 1], ids[idx]
                                service.reorder_siblings(selected_cat_obj.parent_id, ids)
                                st.session_state.pop('category_counts_cache', None)
                                st.toast("✅ 已下移")
                                st.rerun()
                        except Exception as e:
                            st.error(f"下移失败: {e}")

                    if st.button("↪️ 换父目录", disabled=(selected_cat_obj is None), key="btn_reparent_cat", use_container_width=True):
                        st.session_state.show_reparent_dialog = True
                        st.session_state.reparent_category_id = selected_cat_id
                        st.rerun()

                    if st.button("🗑️ 删除", disabled=(selected_cat_obj is None), key="btn_del_cat", use_container_width=True):
                        st.session_state.show_delete_dialog = True
                        st.session_state.delete_category_id = selected_cat_id
                        st.session_state.delete_category_name = selected_cat_obj.name if selected_cat_obj else ""
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

    # 一次性加载所有目录 case count（避免 N+1 查询）
    if 'category_counts_cache' not in st.session_state:
        st.session_state.category_counts_cache = _load_all_counts(service)
    counts_cache = st.session_state.category_counts_cache

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
            case_count = counts_cache.get(node['id'], 0)
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
    total_count = counts_cache.get('__total__', 0)
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

    # 使用"上次返回值"作为去抖基准，避免 sac.tree 每次 rerender 返回相同值
    # 却因为解析出的 index 与 current_selected_id 不一致而反复 rerun。
    last_raw = st.session_state.get('_sac_category_tree_last_raw')
    raw_signature = repr(selected_index_list)

    def _flat_index_to_id(value):
        """将 sac.tree 返回值解析为目录 ID。

        sac.tree(return_index=True) 返回的节点 key 是深度优先的扁平唯一索引，
        与上方 index_map 的编号规则完全一致：
        - 点击节点标题(onSelect) → 单个索引值
        - 点击展开/折叠箭头(onExpand) → 当前选中索引组成的数组
        不存在"路径索引"语义，直接按扁平索引映射即可。
        """
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, list):
            if not value:
                return None
            value = value[-1]
        try:
            idx = int(value)
        except (TypeError, ValueError):
            return None
        return index_map.get(idx)

    new_selected_id = _flat_index_to_id(selected_index_list)
    if new_selected_id is None:
        new_selected_id = current_selected_id

    # 仅当组件返回值相对上次真正发生变化时，才更新 session_state 并触发 rerun；
    # Streamlit 遇到 widget 交互会自然 rerun，无需我们再手动调用 st.rerun()。
    if raw_signature != last_raw:
        st.session_state['_sac_category_tree_last_raw'] = raw_signature
        if new_selected_id != current_selected_id:
            st.session_state.selected_category = new_selected_id

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

    # 换父对话框
    if st.session_state.get('show_reparent_dialog', False):
        _reparent_category_dialog(service)

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
                    st.session_state.pop('category_counts_cache', None)
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
                # 如果删除的是当前选中的目录，切换到全部用例
                if st.session_state.get('selected_category') == cat_id:
                    st.session_state.selected_category = '__all__'
                    # 不能直接写 st.session_state.sac_category_tree（组件已实例化），
                    # 清掉 last_raw 缓存让下次 rerun 时 default_index 生效
                    st.session_state.pop('_sac_category_tree_last_raw', None)
                st.session_state.show_delete_dialog = False
                st.session_state.pop('category_counts_cache', None)
                st.rerun()
            except ValueError as e:
                st.error(str(e))

@st.dialog("移动目录")
def _reparent_category_dialog(service: CategoryService):
    cat_id = st.session_state.get('reparent_category_id')
    cat = service.db.query(Category).filter(Category.id == cat_id).first()

    if not cat:
        st.error("目录不存在")
        if st.button("关闭", use_container_width=True):
            st.session_state.show_reparent_dialog = False
            st.rerun()
        return

    st.info(f"当前目录: {cat.path}")

    all_categories = service.db.query(Category).order_by(Category.level, Category.sort_order, Category.path).all()
    descendants = service.db.query(Category.id).filter(Category.path.like(f"{cat.path}/%")).all()
    forbidden_ids = {cat.id}
    forbidden_ids.update([row[0] for row in descendants])

    options = [(None, '顶级目录')]
    for node in all_categories:
        if node.id in forbidden_ids:
            continue
        indent = '　' * (node.level - 1)
        options.append((node.id, f"{indent}{node.path}"))

    selected_parent = st.selectbox(
        "选择新父目录",
        options=[opt[0] for opt in options],
        format_func=lambda x: next((label for cid, label in options if cid == x), '顶级目录'),
        key='reparent_target_parent'
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("取消", use_container_width=True):
            st.session_state.show_reparent_dialog = False
            st.rerun()
    with col2:
        if st.button("✅ 确认移动", type="primary", use_container_width=True):
            try:
                service.move_node(cat_id, selected_parent)
                st.session_state.show_reparent_dialog = False
                st.session_state.pop('category_counts_cache', None)
                st.toast("✅ 目录移动成功")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
