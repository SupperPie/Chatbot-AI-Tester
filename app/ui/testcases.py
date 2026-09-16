import streamlit as st
import pandas as pd
import ast
import logging
from app.utils import load_data, save_data, save_records, run_tests_sync, save_history
from chat_client import get_available_apis

# 获取 logger（配置在 streamlit_app.py 入口统一处理）
logger = logging.getLogger(__name__)


@st.cache_data(ttl=120)
def _cached_available_apis():
    """缓存 API 列表，避免每次 rerun 都查 DB"""
    return get_available_apis() or ["Bundle API"]

# 目录功能开关（数据库迁移完成前可关闭）
ENABLE_CATEGORY_FEATURE = True

# 断言组件显示名称缓存（使用 st.cache_data 避免每次 rerun 查 DB）
@st.cache_data(ttl=60)
def _load_assertion_label_map() -> dict:
    """一次性加载所有断言组件的 ID→名称 映射"""
    try:
        from app.services.assertion_service import AssertionService
        service = AssertionService()
        components = service.get_all()
        return {c.id: c.name for c in components}
    except Exception:
        return {}


def _get_assertion_display_label(comp_id: str) -> str:
    """获取断言组件的可读标签"""
    label_map = _load_assertion_label_map()
    return label_map.get(comp_id, comp_id)

def render_category_widget_safe():
    """渲染目录 Widget（带错误处理），返回选中的目录 ID"""
    if not ENABLE_CATEGORY_FEATURE:
        return '__all__'
    try:
        from app.ui.components.category_widget import render_category_widget
        return render_category_widget()
    except Exception as e:
        logger.warning(f"目录功能加载失败: {e}")
        st.warning(f"目录功能暂不可用: {e}")
        return '__all__'

def _count_unique_case_ids(df: pd.DataFrame) -> int:
    """按 testcase id 统计唯一用例数（统一统计口径）。"""
    if df is None or df.empty or 'id' not in df.columns:
        return 0
    ids = df['id'].dropna().astype(str).str.strip()
    ids = ids[ids != ""]
    return int(ids.nunique())


def _count_unique_case_ids_in_records(records) -> int:
    """按 testcase id 统计记录列表中的唯一用例数。"""
    if not records:
        return 0
    ids = set()
    for r in records:
        cid = (r or {}).get('id')
        if cid is None:
            continue
        s = str(cid).strip()
        if s:
            ids.add(s)
    return len(ids)


def filter_test_cases(df, category_id=None, tags=None, id_from=None, id_to=None, keyword=None, priorities=None, modules=None):
    """多维度筛选测试用例

    Args:
        df: 原始 DataFrame
        category_id: 目录 ID（含子目录）
        tags: 标签列表（OR 逻辑）
        id_from: ID 起始范围
        id_to: ID 结束范围
        keyword: 关键词搜索（匹配 input 字段）
        priorities: Priority 过滤条件（支持 P0/P1/P2/(空)）
        modules: Module 过滤条件（自由文本，支持(空)）

    Returns:
        筛选后的 DataFrame
    """
    filtered = df.copy()
    
    # 目录筛选（含子目录）；'__all__' 表示不筛选
    if category_id and category_id not in ('__all__', 'all', '') and ENABLE_CATEGORY_FEATURE:
        if 'category_id' in filtered.columns:
            try:
                from app.ui.components.category_selector import get_category_ids_with_children
                category_ids = get_category_ids_with_children(category_id)
                logger.debug(f"filter_test_cases: category_id={category_id}, category_ids={category_ids}")
                logger.debug(f"filter_test_cases: df中的category_id唯一值: {filtered['category_id'].unique()}")
                if category_ids:
                    filtered = filtered[filtered['category_id'].isin(category_ids)]
                    logger.debug(f"filter_test_cases: 筛选后剩余 {len(filtered)} 行")
            except Exception as e:
                logger.warning(f"目录筛选失败，category_id={category_id}, error={e}")
    
    # 标签筛选（OR 逻辑：包含任一标签即可）
    if tags and len(tags) > 0:
        def _normalize_tags(row_tags):
            """将任意格式的 tags 值统一转换为 Python list"""
            if isinstance(row_tags, list):
                return row_tags
            if not row_tags or (isinstance(row_tags, float) and pd.isna(row_tags)):
                return []
            import ast
            s = str(row_tags).strip()
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
            # comma-separated plain string e.g. "guardrail, test"
            return [t.strip() for t in s.split(',') if t.strip()]

        def has_any_tag(row_tags):
            normalized = _normalize_tags(row_tags)
            return any(tag in normalized for tag in tags)

        filtered = filtered[filtered['tags'].apply(has_any_tag)]
    
    # ID 范围筛选（优先数值比较，回退字符串比较）
    if id_from and str(id_from).strip():
        val = str(id_from).strip()
        try:
            num_val = float(val)
            numeric_ids = pd.to_numeric(filtered['id'], errors='coerce')
            filtered = filtered[numeric_ids >= num_val]
        except ValueError:
            filtered = filtered[filtered['id'] >= val]
    if id_to and str(id_to).strip():
        val = str(id_to).strip()
        try:
            num_val = float(val)
            numeric_ids = pd.to_numeric(filtered['id'], errors='coerce')
            filtered = filtered[numeric_ids <= num_val]
        except ValueError:
            filtered = filtered[filtered['id'] <= val]
    
    # 关键词搜索（匹配 input / expected_output / retrieval_context 字段）
    if keyword and str(keyword).strip():
        keyword_lower = str(keyword).strip().lower()
        search_cols = [c for c in ['id', 'input', 'expected_output', 'retrieval_context'] if c in filtered.columns]
        mask = pd.Series(False, index=filtered.index)
        for col in search_cols:
            mask |= filtered[col].astype(str).str.lower().str.contains(keyword_lower, na=False, regex=False)
        filtered = filtered[mask]

    # Priority 筛选（支持 P0/P1/P2/(空)）
    if priorities and len(priorities) > 0:
        normalized = {str(p).strip().upper() for p in priorities if p is not None}

        def _norm_priority(v):
            if v is None:
                return ''
            s = str(v).strip().upper()
            return s if s in ('P0', 'P1', 'P2') else ''

        has_empty = '(空)' in priorities
        filtered_priority = filtered['priority'].apply(_norm_priority) if 'priority' in filtered.columns else pd.Series([''] * len(filtered), index=filtered.index)

        mask = filtered_priority.isin({'P0', 'P1', 'P2'} & normalized)
        if has_empty:
            mask = mask | (filtered_priority == '')
        filtered = filtered[mask]

    # Module 筛选（自由文本值，支持(空)）
    if modules and len(modules) > 0:
        normalized_mods = {str(m).strip() for m in modules if m is not None and str(m).strip()}

        def _norm_module(v):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return ''
            return str(v).strip()

        has_empty_mod = '(空)' in modules
        filtered_module = filtered['module'].apply(_norm_module) if 'module' in filtered.columns else pd.Series([''] * len(filtered), index=filtered.index)

        mask = filtered_module.isin(normalized_mods)
        if has_empty_mod:
            mask = mask | (filtered_module == '')
        filtered = filtered[mask]

    return filtered

def render_testcases_page():
    logger.debug("=== render_testcases_page() 开始 ===")
    title_col, manual_col, import_col = st.columns([5.8, 2.1, 2.1])
    with title_col:
        st.title("📋 Test Cases Management")

    manual_container = manual_col
    import_container = import_col

    def render_manual_content():
        st.markdown("""
### 📖 测评参数使用手册

#### 1. 字段说明
- **retrieval_context** (检索上下文): 
  提供给大模型评估时的背景事实或参考知识。主要用于验证 AI 回答有没有胡编乱造（幻觉检测）。填入具体的参考文本片段即可。
- **conversation** (多轮对话): 
  仅在多轮测试(`multi_turn`)时生效的 JSON 数组配置。**单轮测试时此列无用，保持空白即可。**

#### 2. Validation (验证规则配置)
用于控制具体某道题的评分标准，填写 JSON 格式。可用类型（`type`）：
- **`semantic` *(默认)***: 语义验证。通过大模型（GEval）比较意思是否一致，不拘泥于字眼。
  - **`threshold`** (通过阈值): 取值 0.0 ~ 1.0。`0.5` 为宽松模式（意思大概对就行），`0.8` 以上为严格模式（意思必须高度完全对应）。
  - *示例*: `{"type": "semantic", "threshold": 0.5}`
- **`contains`**: 包含验证。确保实际回答里必定包含某些指定词汇。
  - **`keywords`**: 必须包含的词组。
  - *示例*: `{"type": "contains", "keywords": ["不能退款", "违约金"]}`
- **`exact`**: 精确验证。大模型实际输出必须和预期输出一字不差。
  - *示例*: `{"type": "exact"}`

#### 3. Overall Criteria (多轮/全局评价标准)
主要用于多轮测试，约束整题成败的全局判断：
- **`must_complete_all_turns`** (bool): 如果设为 true，那么多轮对话中只要中间一轮 AI 答错了或提前结束了，就算这整道题 Fail。
- **`min_success_rate`** (float): 最低通过率。如 0.8 表示必须答对 80% 的轮次，这题才算总评 Pass。
- *示例*: `{"must_complete_all_turns": true, "min_success_rate": 1.0}`
            """)

    # 顶部右侧：参数说明手册（下移避免贴顶裁剪）
    with manual_container:
        st.markdown('<div style="height: 34px;"></div>', unsafe_allow_html=True)
        with st.popover("📖 参数说明手册", width="stretch"):
            # 使用一个宽 div 强行撑开手册的宽度（因为前面的全局样式限制了宽度，强制覆盖）
            st.markdown('<div style="width: 500px; max-width: 90vw;">', unsafe_allow_html=True)
            render_manual_content()
            st.markdown('</div>', unsafe_allow_html=True)
    
    # Initialize df in session state
    # 临时：强制重新加载以修复 category_id 问题
    if "df" not in st.session_state or st.session_state.get("_force_reload"):
        st.session_state.df = load_data()
        st.session_state.df_preprocessed = False
        st.session_state._force_reload = False
    
    # Ensure all required columns exist (reload from DB if missing due to cache)
    required_cols = ['category_id', 'retrieval_context', 'overall_criteria', 'validation']
    if not all(col in st.session_state.df.columns for col in required_cols):
        st.session_state.df = load_data()

    # priority 列允许为空；历史数据保持为空，不做自动回填
    if 'priority' not in st.session_state.df.columns:
        st.session_state.df['priority'] = None
    # module 列允许为空（自由文本）
    if 'module' not in st.session_state.df.columns:
        st.session_state.df['module'] = None

    # Internal row key (frontend only), do NOT persist to backend
    if '__row_key' not in st.session_state.df.columns:
        st.session_state.df['__row_key'] = [f"rk_{i}" for i in range(len(st.session_state.df))]
    
    # Layout: Top Section
    top_left_col, top_right_col = st.columns([1, 2.5])
    
    selected_category = '__all__'
    if ENABLE_CATEGORY_FEATURE:
        with top_left_col:
            selected_category = render_category_widget_safe()
    
    # Track content signature
    def get_content_signature(df):
        content_df = df.drop(columns=["Select", "__row_key"], errors='ignore')
        return content_df.to_json(orient='records', force_ascii=False)

    def prepare_df_for_persistence(df: pd.DataFrame) -> pd.DataFrame:
        """Prepare DataFrame for DB persistence by removing UI-only columns."""
        return df.drop(columns=['Select', '__row_key'], errors='ignore')

    def rebuild_internal_ids(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        if 'id' not in out.columns:
            out['id'] = ""
        out['__row_key'] = [f"rk_{i}" for i in range(len(out))]
        return out

    def invalidate_case_views(reset_page: bool = False):
        """统一失效目录计数与用例数据缓存，确保左右视图口径一致。"""
        st.session_state.pop('category_counts_cache', None)
        st.session_state['_force_reload'] = True
        st.session_state['df_preprocessed'] = False
        if reset_page:
            st.session_state['testcases_current_page'] = 1
    
    if "df_content_sig" not in st.session_state:
        st.session_state.df_content_sig = get_content_signature(st.session_state.df)

    @st.dialog("⚠️ Confirm Deletion")
    def confirm_delete_dialog(ids_to_delete):
        st.warning(f"Are you sure you want to permanently delete **{len(ids_to_delete)}** test cases? This action cannot be undone.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Cancel", width="stretch"):
                st.rerun()
        with col2:
            if st.button("🗑️ Yes, Delete", type="primary", width="stretch"):
                try:
                    # 1. 先从 DB 删除
                    try:
                        from app.services.test_case_service import TestCaseService
                        service = TestCaseService()
                        deleted_count = service.delete_by_ids(ids_to_delete)
                        logger.info(f"DB deleted {deleted_count} rows for ids={ids_to_delete}")
                    except Exception as e:
                        logger.error(f"DB delete failed: {e}", exc_info=True)
                        st.error(f"DB 删除失败: {e}")
                        return

                    # 2. 从 session state 移除（DB 已删除，无需 re-save 剩余记录）
                    current_df = st.session_state.df
                    new_df = current_df[~current_df['id'].isin(ids_to_delete)].reset_index(drop=True)

                    # Update session state
                    if "Select" not in new_df.columns:
                         new_df.insert(0, "Select", False)
                    new_df = rebuild_internal_ids(new_df)
                    st.session_state.df = new_df
                    st.session_state.df_content_sig = get_content_signature(new_df)
                    st.session_state.df_preprocessed = False
                    invalidate_case_views(reset_page=True)

                    st.toast(f"🗑️ Deleted {len(ids_to_delete)} cases successfully!")
                    st.rerun()
                except Exception as e:
                    logger.error(f"Delete dialog failed: {e}", exc_info=True)
                    st.error(f"删除失败: {e}")

    @st.dialog("📂 移动到目录")
    def move_to_category_dialog(ids_to_move):
        """移动选中的测试用例到指定目录"""
        st.info(f"将 **{len(ids_to_move)}** 个测试用例移动到目录：")
        
        try:
            from app.services.category_service import CategoryService
            from app.database import SessionLocal
            
            db = SessionLocal()
            service = CategoryService(db)
            tree = service.get_tree()
            db.close()
            
            # 构建目录选项列表 - 使用完整路径以区分同名目录
            category_options = []
            def build_options(nodes, prefix=""):
                for node in nodes:
                    # 使用完整路径而非仅名称，避免同名目录混淆
                    label = f"📁 {node['path']}"
                    category_options.append((node['id'], label))
                    if node.get('children'):
                        build_options(node['children'], prefix + "  ")
            build_options(tree)
            
            if not category_options:
                st.error("没有可用的目录")
                return
            
            # 目录选择
            selected = st.selectbox(
                "选择目标目录",
                options=[c[0] for c in category_options],
                format_func=lambda x: next((c[1] for c in category_options if c[0] == x), x),
                key="move_category_select"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("取消", width="stretch"):
                    st.rerun()
            with col2:
                if st.button("✅ 确认移动", type="primary", width="stretch"):
                    # 更新数据库中的 category_id
                    try:
                        from app.models.test_case import TestCase
                        db = SessionLocal()
                        updated = db.query(TestCase).filter(TestCase.id.in_(ids_to_move)).update(
                            {TestCase.category_id: selected},
                            synchronize_session=False
                        )
                        db.commit()
                        db.close()
                        
                        # 同时更新本地 DataFrame
                        if 'category_id' not in st.session_state.df.columns:
                            st.session_state.df['category_id'] = 'root'
                        st.session_state.df.loc[st.session_state.df['id'].isin(ids_to_move), 'category_id'] = selected
                        st.session_state.df['Select'] = False
                        invalidate_case_views(reset_page=True)

                        st.toast(f"✅ 已将 {len(ids_to_move)} 个用例移动到目录")
                        st.rerun()
                    except Exception as e:
                        st.error(f"移动失败: {e}")
        except Exception as e:
            st.error(f"加载目录失败: {e}")

    @st.dialog("🚩 批量设置 Priority")
    def batch_priority_dialog(ids_to_update):
        st.info(f"将 **{len(ids_to_update)}** 个测试用例的 Priority 批量更新为：")

        target_priority = st.selectbox(
            "选择目标 Priority",
            options=["P0", "P1", "P2", "(清空)"],
            key="batch_priority_target"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("取消", width="stretch"):
                st.rerun()
        with col2:
            if st.button("✅ 确认设置", type="primary", width="stretch"):
                try:
                    from app.services.test_case_service import TestCaseService

                    target = None if target_priority == "(清空)" else target_priority
                    updated_count = TestCaseService().update_priority_by_ids(ids_to_update, target)

                    if 'priority' not in st.session_state.df.columns:
                        st.session_state.df['priority'] = None
                    st.session_state.df.loc[st.session_state.df['id'].isin(ids_to_update), 'priority'] = target
                    st.session_state.df['Select'] = False
                    invalidate_case_views(reset_page=False)

                    st.toast(f"✅ 已更新 {updated_count} 条记录 Priority")
                    st.rerun()
                except Exception as e:
                    st.error(f"批量设置 Priority 失败: {e}")

    @st.dialog("📦 批量设置 Module")
    def batch_module_dialog(ids_to_update):
        st.info(f"将 **{len(ids_to_update)}** 个测试用例的 Module 批量更新为：")

        # 收集现有 module 值作为建议选项
        existing_modules = []
        if 'module' in st.session_state.df.columns:
            _vals = st.session_state.df['module'].dropna().astype(str).str.strip()
            existing_modules = sorted({v for v in _vals if v})

        target_module = st.selectbox(
            "选择或输入目标 Module",
            options=["(输入新值)", "(清空)"] + existing_modules,
            key="batch_module_target_select"
        )
        custom_module = None
        if target_module == "(输入新值)":
            custom_module = st.text_input("输入新 Module 名称", key="batch_module_custom_input")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("取消", width="stretch"):
                st.rerun()
        with col2:
            if st.button("✅ 确认设置", type="primary", width="stretch"):
                try:
                    if target_module == "(输入新值)":
                        if not custom_module or not custom_module.strip():
                            st.error("请输入新 Module 名称")
                            return
                        target = custom_module.strip()
                    elif target_module == "(清空)":
                        target = None
                    else:
                        target = target_module

                    from app.services.test_case_service import TestCaseService
                    updated_count = TestCaseService().update_module_by_ids(ids_to_update, target)

                    if 'module' not in st.session_state.df.columns:
                        st.session_state.df['module'] = None
                    st.session_state.df.loc[st.session_state.df['id'].isin(ids_to_update), 'module'] = target
                    st.session_state.df['Select'] = False
                    invalidate_case_views(reset_page=False)

                    st.toast(f"✅ 已更新 {updated_count} 条记录 Module")
                    st.rerun()
                except Exception as e:
                    st.error(f"批量设置 Module 失败: {e}")

    @st.dialog("🚀 开始测试 - Report Name")
    def run_confirm_dialog(cases, api_name, case_count):
        """运行测试前的确认弹窗：输入本次 Test Report 的名称。
        默认值：{endpoint}_{当天日期}_{时间戳}，用户可编辑。
        """
        from datetime import datetime as _dt
        default_name = f"{api_name}_{_dt.now().strftime('%Y%m%d')}_{_dt.now().strftime('%H%M%S')}"

        st.info(f"即将执行 **{case_count}** 个测试用例（API: **{api_name}**）")

        report_name = st.text_input(
            "本次 Test Report 名称",
            value=default_name,
            key="run_report_name_input",
            help="显示在 Test Report 页面的报告名称，可自定义编辑"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("取消", width="stretch"):
                st.session_state.pop('confirmed_run', None)
                st.session_state.pop('pending_run_dialog', None)
                st.session_state.pop('run_report_name_input', None)
                st.rerun()
        with col2:
            if st.button("▶ 开始执行", type="primary", width="stretch"):
                name = (report_name or "").strip() or default_name
                st.session_state['confirmed_run'] = {
                    'cases': cases,
                    'report_name': name,
                }
                st.session_state.pop('pending_run_dialog', None)
                st.session_state.pop('run_report_name_input', None)
                st.rerun()

    with top_right_col:
        # ------------------
        # Control Panel
        # ------------------
        def get_all_tags(df):
            import ast as _ast
            all_tags = set()
            if "tags" in df.columns:
                for tags_value in df["tags"]:
                    if isinstance(tags_value, list):
                        all_tags.update(tags_value)
                    elif tags_value and not (isinstance(tags_value, float) and pd.isna(tags_value)):
                        s = str(tags_value).strip()
                        try:
                            parsed = _ast.literal_eval(s)
                            if isinstance(parsed, list):
                                all_tags.update(parsed)
                                continue
                        except Exception:
                            pass
                        all_tags.update(t.strip() for t in s.split(',') if t.strip())
            return sorted(list(all_tags))
        
        available_tags = get_all_tags(st.session_state.df)

        priority_values = ["P0", "P1", "P2"]
        if 'priority' in st.session_state.df.columns:
            has_empty_priority = st.session_state.df['priority'].apply(
                lambda x: x is None or str(x).strip() == ''
            ).any()
            if has_empty_priority:
                priority_values.append("(空)")

        st.markdown("#### ⚙️ Management")
        # 第一行：API Endpoint + Thread 并发数
        api_col, thread_label_col, thread_input_col = st.columns([5, 0.8, 1])
        with api_col:
            available_apis = _cached_available_apis()
            selected_api = st.selectbox("⚙️ API Endpoint", options=available_apis, index=0, key="page_api_select", label_visibility="collapsed")
        with thread_label_col:
            st.markdown(
                "<div style='padding-top: 8px; text-align: right; font-weight: 500; white-space: nowrap;'>Thread</div>",
                unsafe_allow_html=True,
            )
        with thread_input_col:
            if "page_max_workers_input" not in st.session_state:
                st.session_state["page_max_workers_input"] = "3"
            st.text_input(
                "Thread",
                key="page_max_workers_input",
                placeholder="1-10, default 3",
                help="并发线程数（1-10，默认 3）。多轮对话仍串行执行。",
                label_visibility="collapsed",
            )

        def _get_max_workers() -> int:
            raw = st.session_state.get("page_max_workers_input", "3")
            try:
                v = int(str(raw).strip())
            except Exception:
                return 3
            if v < 1:
                return 1
            if v > 10:
                return 10
            return v

        # 第二行：批量操作按钮（Move / Priority / Module / Assert / Delete）
        btn_col1, btn_col2, btn_col2b, btn_col3, btn_col4, btn_col5 = st.columns(6)
        with btn_col1:
            move_to_category_clicked = st.button("📂 Move", width="stretch", key="btn_move_category") if ENABLE_CATEGORY_FEATURE else False
        with btn_col2:
            batch_priority_clicked = st.button("🚩 Priority", width="stretch", key="btn_batch_priority")
        with btn_col2b:
            batch_module_clicked = st.button("📦 Module", width="stretch", key="btn_batch_module")
        with btn_col3:
            bind_assertions_clicked = st.button("🧩 Assert", width="stretch", key="btn_bind_assertions")
        with btn_col4:
            refresh_dates_clicked = st.button("📅 Refresh Dates", width="stretch", key="btn_refresh_dates",
                                             help="将选中用例 input 中的过去日期替换为未来 1 个月内的日期，按原语言（中/英/葡）格式化")
        with btn_col5:
            delete_selected_clicked = st.button("🗑️ Delete", width="stretch", key="btn_delete_selected")

        # 顶部右侧：Import（与参数说明手册同一行，下移避免贴顶裁剪）
        with import_container:
            st.markdown('<div style="height: 34px;"></div><div class="import-popover-anchor"></div>', unsafe_allow_html=True)
            with st.popover("📤 Import", width="stretch"):
                 st.markdown('<div style="width: 400px; max-width: 90vw;">', unsafe_allow_html=True)
                 st.markdown("### Import Test Cases")
                 
                 # 目录选择
                 import_category = 'root'
                 if ENABLE_CATEGORY_FEATURE:
                     try:
                         from app.ui.components.category_selector import get_category_options
                         cat_opts = get_category_options()
                         # 默认选中目录树当前节点，减少导入到错误目录的情况
                         _opt_ids = [c[0] for c in cat_opts]
                         _default_idx = 0
                         _cur_cat = st.session_state.get('selected_category')
                         if _cur_cat in _opt_ids:
                             _default_idx = _opt_ids.index(_cur_cat)
                         import_category = st.selectbox(
                             "📂 目标目录",
                             options=_opt_ids,
                             index=_default_idx,
                             format_func=lambda x: next((c[1] for c in cat_opts if c[0] == x), x),
                             key="import_category_select"
                         )
                     except Exception:
                         st.text("目录加载失败，将导入到根目录")
                 # 目标目录显示名（导入结果提示用）
                 try:
                     _import_target_name = next(
                         (c[1].strip() for c in cat_opts if c[0] == import_category), import_category)
                 except Exception:
                     _import_target_name = import_category or 'root'
                 
                 st.divider()
                 
                 # Download Template
                 try:
                     with open("docs/import_template.csv", "rb") as f:
                         st.download_button("📄 Download Template", data=f, file_name="import_template.csv", mime="text/csv", help="Download CSV template")
                 except Exception as e:
                     st.error(f"Template not found: {e}")
             
                 st.info("Upload CSV/JSON. Required: `input`, `expected_output`. Optional: `id`, `input_cn`, `expected_output_cn`, `description`, `priority`, `module`, `tags`, `type`, `turn_index`, `validation`, `overall_criteria`, `retrieval_context`, `assertions`.")
                 uploaded_file = st.file_uploader("Upload File", type=["csv", "json"], key="popover_uploader")
             
                 if uploaded_file is not None:
                    try:
                        if uploaded_file.name.endswith('.csv'):
                             try:
                                 # utf-8-sig：兼容 Excel 导出的带 BOM 的 CSV
                                 import_df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
                             except UnicodeDecodeError:
                                 uploaded_file.seek(0)
                                 import_df = pd.read_csv(uploaded_file, encoding='gb18030')
                        else:
                            import_df = pd.read_json(uploaded_file)

                        # 列名规范化：去 BOM、去首尾空白（Excel 导出常见问题）
                        import_df.columns = [str(c).lstrip('\ufeff').strip() for c in import_df.columns]

                        # Validation
                        required_cols = ["input", "expected_output"]
                        if not all(col in import_df.columns for col in required_cols):
                            missing = [c for c in required_cols if c not in import_df.columns]
                            file_cols = ', '.join(str(c) for c in import_df.columns[:15])
                            st.error(f"文件缺少必需列: {', '.join(missing)}。必需列: input, expected_output。文件实际的列: {file_cols}")
                        else:
                            update_existing = st.checkbox("Update existing cases by ID (if ID matches)", value=False, key="chk_update_cases")
                        
                            if st.button(f"Confirm Import", type="primary", key="btn_confirm_import"):
                                # 过滤掉 input 为空的记录
                                original_count = len(import_df)
                                import_df = import_df[import_df['input'].notna() & (import_df['input'].astype(str).str.strip() != '')]
                                filtered_count = original_count - len(import_df)
                                if filtered_count > 0:
                                    st.warning(f"已跳过 {filtered_count} 条 input 为空的记录")
                                if import_df.empty:
                                    st.error("没有有效的测试用例可导入（所有记录的 input 都为空）")
                                    st.stop()
                                
                                # Prepare data
                                # Ensure tags are lists
                                if "tags" in import_df.columns:
                                    def normalize_tags(x):
                                        if isinstance(x, list): return x
                                        if pd.isna(x) or x == "": return []
                                        if isinstance(x, str):
                                            try:
                                                # Try to parse string representation of list like "['tag1', 'tag2']"
                                                import ast
                                                parsed = ast.literal_eval(x)
                                                if isinstance(parsed, list): return parsed
                                                return [x]
                                            except:
                                                # Treat string as single tag
                                                return [x] if x.strip() else []
                                        return []
                                    import_df["tags"] = import_df["tags"].apply(normalize_tags)
                                else:
                                    import_df["tags"] = [[] for _ in range(len(import_df))]

                                if "assertions" in import_df.columns:
                                    def normalize_assertions(x):
                                        if isinstance(x, list):
                                            return x
                                        if pd.isna(x) or x == "":
                                            return []
                                        if isinstance(x, str):
                                            try:
                                                import ast
                                                parsed = ast.literal_eval(x)
                                                if isinstance(parsed, list):
                                                    return parsed
                                            except Exception:
                                                pass
                                        return []
                                    import_df["assertions"] = import_df["assertions"].apply(normalize_assertions)
                                else:
                                    import_df["assertions"] = [[] for _ in range(len(import_df))]
                                
                                # 设置 category_id（导入到指定目录）
                                import_df["category_id"] = import_category

                                # 规范化 turn_index：NaN → 1
                                if "turn_index" in import_df.columns:
                                    def _safe_ti(v):
                                        try:
                                            if pd.isna(v): return 1
                                        except (TypeError, ValueError):
                                            return 1
                                        try: return int(v)
                                        except: return 1
                                    import_df["turn_index"] = import_df["turn_index"].apply(_safe_ti)
                                else:
                                    import_df["turn_index"] = 1
                                # 规范化 type：空值 → single
                                if "type" not in import_df.columns:
                                    import_df["type"] = "single"
                                else:
                                    import_df["type"] = import_df["type"].fillna("single").replace("", "single")

                                # 确保 import_df 有必要的列（对齐 current_df，避免 concat 后缺列）
                                current_df = st.session_state.df.drop(columns=["Select", "__row_key"], errors='ignore')
                                for col in current_df.columns:
                                    if col not in import_df.columns and col != "id":
                                        import_df[col] = None
                                # import_df 中不在 current_df 的新列也要补上
                                for col in import_df.columns:
                                    if col not in current_df.columns and col != "id":
                                        current_df[col] = None
                            
                                if update_existing:
                                    if "id" not in import_df.columns:
                                        st.error("Column 'id' is required for updating existing cases.")
                                        st.stop()
                                
                                    # Convert IDs to string for comparison
                                    current_df["id"] = current_df["id"].astype(str)
                                    import_df["id"] = import_df["id"].astype(str)
                                
                                    # Create a dict mapping ID to index in current_df for fast lookup
                                    # Multi-turn: key by (id, turn_index)
                                    def _row_key(r):
                                        ti = r.get("turn_index", 1)
                                        try:
                                            ti = 1 if ti is None or (isinstance(ti, float) and pd.isna(ti)) else int(ti)
                                        except (TypeError, ValueError):
                                            ti = 1
                                        return (str(r.get("id","")), ti)
                                    key_to_index = {}
                                    for idx, row in current_df.iterrows():
                                        key_to_index[_row_key(row)] = idx
                                
                                    updated_count = 0
                                    new_records = []
                                
                                    for _, row in import_df.iterrows():
                                        key = _row_key(row)
                                        if key in key_to_index:
                                            idx = key_to_index[key]
                                            for col in row.index:
                                                val = row[col]
                                                if col == "id": continue
                                                is_empty = False
                                                if isinstance(val, list):
                                                    if not val: is_empty = True
                                                elif pd.isna(val):
                                                    is_empty = True
                                                elif isinstance(val, str) and not val.strip():
                                                    is_empty = True
                                                if not is_empty:
                                                    current_df.at[idx, col] = val
                                            updated_count += 1
                                        else:
                                            new_records.append(row.to_dict())
                                
                                    new_count = len(new_records)
                                    # 给新记录分配 ID 并增量写入 DB
                                    if new_records:
                                        # 计算当前最大 ID：取 DB 与内存中较大值，避免并发/不同步导致冲突
                                        from app.services.test_case_service import TestCaseService
                                        _id_svc = TestCaseService()
                                        db_max = _id_svc.get_max_tc_id_num()
                                        mem_max = 0
                                        for eid in current_df["id"].dropna():
                                            if str(eid).startswith("TC"):
                                                try:
                                                    mem_max = max(mem_max, int(str(eid)[2:]))
                                                except:
                                                    pass
                                        existing_max = max(db_max, mem_max)
                                        _id_svc.db.close()
                                        last_id = None
                                        for d in new_records:
                                            d.pop("id", None)
                                            ti = d.get("turn_index", 1)
                                            try:
                                                ti = 1 if ti is None or (isinstance(ti, float) and pd.isna(ti)) else int(ti)
                                            except (TypeError, ValueError):
                                                ti = 1
                                            rtype = d.get("type", "single") or "single"
                                            if rtype == "multi_turn" and ti > 1 and last_id is not None:
                                                d["id"] = last_id
                                            else:
                                                existing_max += 1
                                                new_id = f"TC{existing_max:04d}"
                                                d["id"] = new_id
                                                last_id = new_id
                                            d["turn_index"] = ti
                                        save_records(new_records)
                                        new_rows_df = pd.DataFrame(new_records)
                                        for col in current_df.columns:
                                            if col not in new_rows_df.columns:
                                                new_rows_df[col] = None
                                        new_rows_df = new_rows_df[current_df.columns]
                                        final_df = pd.concat([current_df, new_rows_df], ignore_index=True)
                                    else:
                                        final_df = current_df
                                    
                                    # 增量保存更新过的记录
                                    updated_records = []
                                    for _, row in import_df.iterrows():
                                        key = _row_key(row)
                                        if key in key_to_index:
                                            idx = key_to_index[key]
                                            updated_records.append(current_df.loc[idx].to_dict())
                                    if updated_records:
                                        save_records(updated_records)
                                
                                    st.toast(f"已更新 {updated_count} 条，新增 {new_count} 条 →【{_import_target_name}】")
                                
                                else:
                                    # Standard Append Mode: 增量写入，不做全量 upsert
                                    if "id" in import_df.columns:
                                        del import_df["id"]
                                    # 为新记录分配 ID：取 DB 与内存中较大值，避免并发/不同步导致冲突
                                    from app.services.test_case_service import TestCaseService
                                    _id_svc = TestCaseService()
                                    db_max = _id_svc.get_max_tc_id_num()
                                    mem_max = 0
                                    for eid in current_df["id"].dropna():
                                        if str(eid).startswith("TC"):
                                            try:
                                                mem_max = max(mem_max, int(str(eid)[2:]))
                                            except:
                                                pass
                                    existing_max = max(db_max, mem_max)
                                    _id_svc.db.close()
                                    
                                    last_id = None
                                    new_rows = []
                                    for _, row in import_df.iterrows():
                                        d = row.to_dict()
                                        ti = d.get("turn_index", 1)
                                        try:
                                            ti = 1 if ti is None or (isinstance(ti, float) and pd.isna(ti)) else int(ti)
                                        except (TypeError, ValueError):
                                            ti = 1
                                        rtype = d.get("type", "single") or "single"
                                        if rtype == "multi_turn" and ti > 1 and last_id is not None:
                                            d["id"] = last_id
                                        else:
                                            existing_max += 1
                                            new_id = f"TC{existing_max:04d}"
                                            d["id"] = new_id
                                            last_id = new_id
                                        d["turn_index"] = ti
                                        new_rows.append(d)
                                    
                                    # 增量写入 DB（只写新记录）
                                    save_records(new_rows)
                                    
                                    # 拼接到 current_df
                                    new_rows_df = pd.DataFrame(new_rows)
                                    # 确保列对齐
                                    for col in current_df.columns:
                                        if col not in new_rows_df.columns:
                                            new_rows_df[col] = None
                                    new_rows_df = new_rows_df[current_df.columns]
                                    final_df = pd.concat([current_df, new_rows_df], ignore_index=True)
                                    st.toast(f"已导入 {len(new_rows)} 条新用例 →【{_import_target_name}】")

                                # Update State
                                if "Select" not in final_df.columns:
                                     final_df.insert(0, "Select", False)
                                final_df = rebuild_internal_ids(final_df)
                                st.session_state.df = final_df
                                st.session_state.df_content_sig = get_content_signature(final_df)
                                st.session_state.df_preprocessed = False
                                invalidate_case_views(reset_page=True)

                                # 导入成功后自动切换到目标目录，让用户立即看到新导入的用例
                                # （避免停留在原目录视图，误以为导入失败而反复上传造成重复）
                                # 注意：不能在组件已实例化后直接写 st.session_state.sac_category_tree，
                                # Streamlit 会报错。这里只改自己的状态位 selected_category，
                                # 下一次 rerun 时 category_widget 会读到新值，default_index 自动正确。
                                if import_category and import_category != st.session_state.get('selected_category'):
                                    st.session_state.selected_category = import_category
                                    # 清除组件的"上次返回值"缓存，避免组件用旧返回值覆盖 selected_category
                                    st.session_state.pop('_sac_category_tree_last_raw', None)

                                st.rerun()
                            
                    except Exception as e:
                        st.error(f"Error: {e}")
                 st.markdown('</div>', unsafe_allow_html=True)
    
    with top_right_col:
        st.markdown('<div style="height: 10px"></div>', unsafe_allow_html=True)
        # ------------------
        # Filter & Run Section
        # ------------------
        st.markdown("#### 🔍 Filter")
        filter_col1, filter_col2, filter_col3, filter_col4, filter_col4b, filter_col5 = st.columns([2.2, 0.9, 0.9, 1.3, 1.3, 1.6])

        with filter_col1:
            filter_tags = st.multiselect(
                "标签",
                options=available_tags,
                default=[],
                key="filter_tags",
                label_visibility="collapsed",
                placeholder="🏷️ 选择标签..."
            ) if available_tags else []

        with filter_col2:
            filter_id_from = st.text_input("From ID", value="", key="filter_id_from", label_visibility="collapsed", placeholder="From ID")

        with filter_col3:
            filter_id_to = st.text_input("To ID", value="", key="filter_id_to", label_visibility="collapsed", placeholder="To ID")

        with filter_col4:
            filter_priority = st.multiselect(
                "Priority",
                options=priority_values,
                default=[],
                key="filter_priority",
                label_visibility="collapsed",
                placeholder="🚩 Priority"
            )

        with filter_col4b:
            # Module 筛选选项：从当前数据收集唯一值
            module_values = []
            if 'module' in st.session_state.df.columns:
                _mv = st.session_state.df['module'].apply(
                    lambda x: '' if x is None or (isinstance(x, float) and pd.isna(x)) else str(x).strip()
                )
                _uniq = sorted({v for v in _mv if v})
                if _mv.eq('').any():
                    module_values = _uniq + ["(空)"]
                else:
                    module_values = _uniq
            filter_module = st.multiselect(
                "Module",
                options=module_values,
                default=[],
                key="filter_module",
                label_visibility="collapsed",
                placeholder="📦 Module"
            )

        with filter_col5:
            filter_keyword = st.text_input("关键词", value="", key="filter_keyword", label_visibility="collapsed", placeholder="🔎 搜索关键词...")

        # Run按钮放在标签下方
        run_col0, run_col1, run_col2, run_col3 = st.columns([2, 1, 1, 1])
        with run_col0:
            execution_mode = st.selectbox(
                "执行模式", ["full (语义+断言)", "semantic (仅语义)", "assertion (仅断言)"],
                key="execution_mode_select", label_visibility="collapsed"
            )
            # 提取模式值
            execution_mode_val = execution_mode.split(" ")[0]
        with run_col1:
            run_selected_clicked = st.button("▶ Run Selected", width="stretch", type="primary", key="btn_run_selected")
        with run_col2:
            run_range_clicked = st.button("▶ Run Range", width="stretch", type="primary", key="btn_run_range", help="执行 From ID 到 To ID 范围内的用例")
        with run_col3:
            run_tags_clicked = st.button("▶ Run by Tags", width="stretch", type="primary", key="btn_run_tags") if filter_tags else False

        # 为执行状态留一个占位符，位于运行按钮的正下方
        execution_placeholder = st.empty()

    # 使用左侧目录树的选择作为目录筛选条件
    filter_category = selected_category

    # 节点切换时重置到第一页，避免页码越界导致空表/残留
    if st.session_state.get('last_selected_category') != filter_category:
        logger.debug(f"Category changed: {st.session_state.get('last_selected_category')} -> {filter_category}")
        st.session_state.testcases_current_page = 1
        st.session_state.last_selected_category = filter_category
        # 清除目录统计缓存，强制重新加载
        st.session_state.pop('category_counts_cache', None)

    # 任意筛选条件（标签/ID范围/Priority/Module/关键词）变化时重置到第一页
    _filter_sig = repr((filter_tags, filter_id_from, filter_id_to, tuple(filter_priority or ()), tuple(filter_module or ()), filter_keyword))
    if st.session_state.get('_last_filter_sig') != _filter_sig:
        st.session_state.testcases_current_page = 1
        st.session_state['_last_filter_sig'] = _filter_sig

    # ------------------
    # Data Editor
    # ------------------
    # Data preprocessing - only run once when data is first loaded
    logger.debug(f">>> df_preprocessed = {st.session_state.get('df_preprocessed', False)}")
    if not st.session_state.get("df_preprocessed", False):
        logger.debug(">>> 开始数据预处理...")
        # pyarrow schema safety: format retrieval_context to string to prevent list/string mixing crashes
        if "retrieval_context" in st.session_state.df.columns:
            st.session_state.df["retrieval_context"] = st.session_state.df["retrieval_context"].apply(
                lambda x: ", ".join(x) if isinstance(x, list) else str(x)
            )
        
        # Fix: Convert expected_output to string to prevent float/text type conflicts
        if "expected_output" in st.session_state.df.columns:
            st.session_state.df["expected_output"] = st.session_state.df["expected_output"].apply(
                lambda x: "" if pd.isna(x) else str(x)
            )
            
        if "conversation" in st.session_state.df.columns:
            st.session_state.df.drop(columns=["conversation"], inplace=True)
        
        # Sort data once during preprocessing
        if "turn_index" in st.session_state.df.columns:
            st.session_state.df = st.session_state.df.sort_values(by=["id", "turn_index"], na_position="first").reset_index(drop=True)
        elif "id" in st.session_state.df.columns:
            st.session_state.df = st.session_state.df.sort_values(by="id").reset_index(drop=True)
        
        st.session_state.df_preprocessed = True
        logger.debug(">>> 数据预处理完成")

    # 应用筛选条件
    filtered_df = filter_test_cases(
        st.session_state.df,
        category_id=filter_category,
        tags=filter_tags,
        id_from=filter_id_from,
        id_to=filter_id_to,
        keyword=filter_keyword,
        priorities=filter_priority,
        modules=filter_module
    )
    
    # Debug: 输出筛选结果
    if filter_category and filter_category not in ('__all__', ''):
        logger.debug(f"Category filter: {filter_category}")
        logger.debug(f"Filter chain => tags={filter_tags}, id_from={filter_id_from}, id_to={filter_id_to}, priority={filter_priority}, keyword={filter_keyword}")
        logger.debug(f"Total rows in df: {len(st.session_state.df)}")
        logger.debug(f"Filtered rows: {len(filtered_df)}")
        if len(filtered_df) == 0 and len(st.session_state.df) > 0:
            # 显示有哪些 category_id
            unique_cats = st.session_state.df['category_id'].unique() if 'category_id' in st.session_state.df.columns else []
            logger.warning(f"筛选结果为空！现有 category_id: {unique_cats}")
    
    # 统计信息（统一按 testcase id 口径）
    total_count = _count_unique_case_ids(st.session_state.df)
    filtered_count = _count_unique_case_ids(filtered_df)

    @st.fragment
    def render_paginated_table(display_df):
        logger.debug(">>> render_paginated_table() fragment 开始")

        if "testcases_page_size" not in st.session_state:
            st.session_state.testcases_page_size = 20

        total_items = len(display_df)

        # 选择控制 + 统计 + 每页 + 分页（同一行）
        ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4, ctrl_col5, ctrl_col6 = st.columns([1.35, 1.35, 1.15, 2.7, 1.0, 4.45])

        with ctrl_col1:
            # 全表（跨页）全选：以当前表格数据（display_df）为准
            if st.button("☑️ Select All", key="btn_select_all_global", width="stretch", type="primary"):
                if '__row_key' in display_df.columns:
                    target_keys = display_df['__row_key'].tolist()
                    st.session_state.df.loc[st.session_state.df['__row_key'].isin(target_keys), 'Select'] = True
                else:
                    st.session_state.df['Select'] = True
                st.rerun()

        with ctrl_col2:
            # 当前页全选（按 testcase id 选择：同一 case 的所有 turn 一并勾选）
            if st.button("☑️ Select page", key="btn_select_current_page", width="stretch"):
                start_idx = (st.session_state.testcases_current_page - 1) * st.session_state.testcases_page_size
                end_idx = start_idx + st.session_state.testcases_page_size
                page_df_for_select = display_df.iloc[start_idx:end_idx]
                if 'id' in page_df_for_select.columns:
                    page_case_ids = page_df_for_select['id'].dropna().astype(str).str.strip()
                    page_case_ids = page_case_ids[page_case_ids != ""].unique().tolist()
                    if page_case_ids:
                        st.session_state.df.loc[
                            st.session_state.df['id'].astype(str).isin(page_case_ids),
                            'Select'
                        ] = True
                elif '__row_key' in page_df_for_select.columns:
                    page_keys = page_df_for_select['__row_key'].tolist()
                    st.session_state.df.loc[st.session_state.df['__row_key'].isin(page_keys), 'Select'] = True
                st.rerun()

        with ctrl_col3:
            # Cancel All（紫色背景，与 Select Page 交换位置）
            if st.button("Cancel All", key="btn_deselect_all", width="stretch"):
                st.session_state.df['Select'] = False
                st.rerun()

        with ctrl_col4:
            selected_rows = st.session_state.df[st.session_state.df.get('Select', False) == True] if 'Select' in st.session_state.df.columns else pd.DataFrame()
            selected_count = _count_unique_case_ids(selected_rows)
            filter_info = f"筛选: {filtered_count}/{total_count}" if filtered_count < total_count else f"共 {total_count} 个用例"
            st.markdown('<div style="padding-top: 8px; white-space: nowrap;">📊 {} | ✅ 已选: <b>{}</b> 个用例</div>'.format(filter_info, selected_count), unsafe_allow_html=True)

        with ctrl_col5:
            page_opts = [20, 30, 50, 100]
            if st.session_state.testcases_page_size not in page_opts:
                page_opts.append(st.session_state.testcases_page_size)
                page_opts.sort()

            selected_page_size = st.selectbox(
                "每页显示",
                options=page_opts,
                index=page_opts.index(st.session_state.testcases_page_size),
                label_visibility="collapsed",
                key="page_size_selector"
            )

            if selected_page_size != st.session_state.testcases_page_size:
                st.session_state.testcases_page_size = selected_page_size
                st.session_state.testcases_current_page = 1
                st.rerun()

        items_per_page = st.session_state.testcases_page_size
        total_pages = max(1, (total_items - 1) // items_per_page + 1)

        if "testcases_current_page" not in st.session_state:
            st.session_state.testcases_current_page = 1
        st.session_state.testcases_current_page = max(1, min(st.session_state.testcases_current_page, total_pages))

        with ctrl_col6:
            import streamlit_antd_components as sac
            current_page_idx = sac.pagination(
                total=total_items,
                index=st.session_state.testcases_current_page,
                page_size=items_per_page,
                align='start',
                show_total=True,
                jump=True,
                key="sac_testcases_pagination"
            )

            # 去抖：仅当组件返回值相对上次真正改变时才更新，避免和 index 参数
            # 之间的不一致造成每次 rerender 都触发 st.rerun 的死循环。
            _last_page = st.session_state.get('_sac_pagination_last_raw')
            if current_page_idx != _last_page:
                st.session_state['_sac_pagination_last_raw'] = current_page_idx
                if current_page_idx != st.session_state.testcases_current_page:
                    st.session_state.testcases_current_page = current_page_idx

        start_idx = (st.session_state.testcases_current_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_df = display_df.iloc[start_idx:end_idx].copy()

        # 将 assertions 列转为可读文本显示（组件名称而非 ID）
        if 'assertions' in page_df.columns:
            def _format_assertions(val):
                if val is None:
                    return ""
                if isinstance(val, str):
                    if not val.strip():
                        return ""
                    try:
                        import json as _json
                        val = _json.loads(val)
                    except Exception:
                        return val
                if isinstance(val, list):
                    labels = []
                    for item in val:
                        if not isinstance(item, dict):
                            continue
                        comp_id = item.get('ref', '?')
                        # 尝试从缓存获取组件名
                        label = _get_assertion_display_label(comp_id)
                        labels.append(label)
                    return " | ".join(labels) if labels else ""
                return str(val) if val else ""
            page_df['assertions'] = page_df['assertions'].apply(_format_assertions)

        if 'priority' not in page_df.columns:
            page_df['priority'] = None
        if 'module' not in page_df.columns:
            page_df['module'] = None
        if 'input_cn' not in page_df.columns:
            page_df['input_cn'] = ""
        if 'expected_output_cn' not in page_df.columns:
            page_df['expected_output_cn'] = ""

        edited_page_df = st.data_editor(
            page_df,
            column_config={
                "Select": st.column_config.CheckboxColumn("✓", width="small", default=False),
                "id": st.column_config.TextColumn("ID", width="small", disabled=False),
                "input": st.column_config.TextColumn("Input", width="medium"),
                "input_cn": st.column_config.TextColumn("Input_CN", width="medium", help="Input 的中文翻译"),
                "expected_output": st.column_config.TextColumn("Expected Output", width="medium"),
                "expected_output_cn": st.column_config.TextColumn("Expected_Output_CN", width="medium", help="Expected Output 的中文翻译"),
                "description": st.column_config.TextColumn("Description", width="medium", help="描述测试用例的目的，对应产品需求中的验收标准(AC)"),
                "priority": st.column_config.SelectboxColumn("Priority", options=["", "P0", "P1", "P2"], width="small"),
                "module": st.column_config.TextColumn("Module", width="small", help="模块/功能域标签（自由文本）"),
                "tags": st.column_config.ListColumn("Tags"),
                "retrieval_context": st.column_config.Column("Retrieval Context", help="为大模型提供的参考上下文文件。用于验证模型的回答是否基于给定的知识库 (Faithfulness)。"),
                "overall_criteria": st.column_config.Column("Overall_Criteria", help="用于评估打分的特殊判定要求或全局自定义标准。"),
                "validation": st.column_config.Column("Validation", help="验证规则 (JSON格式)。例: {\"type\": \"contains\", \"keywords\": [\"正确\"]} 或 {\"type\": \"semantic\"}。"),
                "turn_index": st.column_config.NumberColumn("Turn_Index", width="small", help="多轮对话的顺序编号"),
                "assertions": st.column_config.TextColumn("Assertions", help="已绑定的断言组件", width="small", disabled=True),
                "category_id": None,
                "__row_key": None,
            },
            num_rows="dynamic",
            width="content",
            height=(len(page_df) + 1) * 35 + 40,
            key=f"main_data_editor_{filter_category}_{st.session_state.testcases_current_page}_{st.session_state.testcases_page_size}"
        )

        # 同步选择状态（按 testcase id：同一 case 的所有 turn 一并勾选/取消）
        if 'Select' in edited_page_df.columns and '__row_key' in edited_page_df.columns:
            for i in range(len(edited_page_df)):
                row = edited_page_df.iloc[i]
                selected_val = bool(row.get('Select', False))
                case_id = str(row.get('id', '')).strip()
                if case_id:
                    st.session_state.df.loc[
                        st.session_state.df['id'].astype(str) == case_id,
                        'Select'
                    ] = selected_val
                else:
                    rk = row['__row_key']
                    st.session_state.df.loc[st.session_state.df['__row_key'] == rk, 'Select'] = selected_val

        # 检测 data_editor 中被用户直接删除的行，同步到 DB 和 session state
        if '__row_key' in edited_page_df.columns and len(edited_page_df) < len(page_df):
            edited_keys = set(edited_page_df['__row_key'].tolist())
            original_keys = set(page_df['__row_key'].tolist())
            deleted_keys = original_keys - edited_keys
            if deleted_keys:
                # 获取被删行的 id 用于 DB 删除
                deleted_ids = st.session_state.df[
                    st.session_state.df['__row_key'].isin(deleted_keys)
                ]['id'].tolist()
                try:
                    from app.services.test_case_service import TestCaseService
                    TestCaseService().delete_by_ids(deleted_ids)
                except Exception as e:
                    logger.warning(f"DB delete (data_editor) failed: {e}")
                # 从 session state 移除
                st.session_state.df = st.session_state.df[
                    ~st.session_state.df['__row_key'].isin(deleted_keys)
                ].reset_index(drop=True)
                st.session_state.df_content_sig = get_content_signature(st.session_state.df)
                invalidate_case_views(reset_page=False)
                st.toast(f"🗑️ Deleted {len(deleted_keys)} row(s)", icon="🗑️")
                st.rerun()

        # 检测新增行（用户通过 data_editor 底部 "+" 按钮添加的行）
        if '__row_key' in page_df.columns and len(edited_page_df) > len(page_df):
            original_keys = set(page_df['__row_key'].tolist())
            new_rows = []
            for i in range(len(edited_page_df)):
                rk = edited_page_df.iloc[i].get('__row_key')
                if pd.isna(rk) or rk == '' or rk not in original_keys:
                    new_rows.append(edited_page_df.iloc[i])
            if new_rows:
                max_rk = max(
                    (int(k.split('_')[1]) for k in st.session_state.df['__row_key']
                     if isinstance(k, str) and k.startswith('rk_')),
                    default=-1
                )
                for row in new_rows:
                    max_rk += 1
                    new_row_dict = row.to_dict()
                    new_row_dict['__row_key'] = f'rk_{max_rk}'
                    new_row_dict.setdefault('category_id', filter_category if filter_category not in ('__all__', '') else 'root')
                    new_row_dict.setdefault('type', 'single')
                    new_row_dict.setdefault('priority', None)
                    new_row_dict.setdefault('module', None)
                    new_row_dict['Select'] = False
                    st.session_state.df = pd.concat(
                        [st.session_state.df, pd.DataFrame([new_row_dict])], ignore_index=True
                    )
                save_df = prepare_df_for_persistence(st.session_state.df)
                saved_df_clean = save_data(save_df)
                if "Select" not in saved_df_clean.columns:
                    saved_df_clean.insert(0, "Select", False)
                saved_df_clean = rebuild_internal_ids(saved_df_clean)
                st.session_state.df = saved_df_clean
                st.session_state.df_content_sig = get_content_signature(st.session_state.df)
                invalidate_case_views(reset_page=False)
                st.toast(f"New row(s) added and saved!", icon="➕")
                st.rerun()

        # 自动保存：仅当内容列被修改时（排除 Select 列，避免勾选触发保存并丢失选中状态）
        _content_cols = [c for c in page_df.columns if c not in ('Select', '__row_key')]
        page_edited = not edited_page_df[_content_cols].reset_index(drop=True).equals(
            page_df[_content_cols].reset_index(drop=True)
        )
        if page_edited:
            # 1. 通过 __row_key 逐行对比，找出真正被修改的行
            page_indexed = page_df.set_index('__row_key')
            edited_indexed = edited_page_df.set_index('__row_key')
            common_keys = [k for k in edited_indexed.index if k in page_indexed.index]

            def _row_changed(rk):
                for col in _content_cols:
                    if col not in page_indexed.columns or col not in edited_indexed.columns:
                        continue
                    a = page_indexed.at[rk, col]
                    b = edited_indexed.at[rk, col]
                    if isinstance(a, (list, dict)) or isinstance(b, (list, dict)):
                        if a != b:
                            return True
                    else:
                        try:
                            if pd.isna(a) and pd.isna(b):
                                continue
                        except (TypeError, ValueError):
                            pass
                        if a != b:
                            return True
                return False

            changed_keys = [rk for rk in common_keys if _row_changed(rk)]

            # 2. 就地把改动写回 st.session_state.df（不替换 DF 对象，保持 __row_key 稳定）
            for rk in changed_keys:
                edited_row = edited_indexed.loc[rk]
                main_idx = st.session_state.df.index[st.session_state.df['__row_key'] == rk]
                for col in _content_cols:
                    if col not in st.session_state.df.columns:
                        continue
                    val = edited_row[col]
                    if isinstance(val, (list, dict)):
                        for idx in main_idx:
                            st.session_state.df.at[idx, col] = val
                    else:
                        st.session_state.df.loc[main_idx, col] = val

            # 3. 增量 upsert：只把改动的行写 DB（不调用 save_data，不做 ID 再生成）
            if changed_keys:
                try:
                    changed_rows_df = st.session_state.df[
                        st.session_state.df['__row_key'].isin(changed_keys)
                    ].drop(columns=['Select', '__row_key'], errors='ignore')
                    save_records(changed_rows_df.to_dict(orient='records'))
                    st.session_state.df_content_sig = get_content_signature(st.session_state.df)
                    st.toast(f"✅ 已保存 {len(changed_keys)} 条修改", icon="💾")
                except Exception as e:
                    logger.error(f"增量保存失败: {e}", exc_info=True)
                    st.error(f"保存失败：{e}")

        logger.debug(">>> render_paginated_table() fragment 结束")
        return display_df

    # Render table
    logger.debug(">>> 准备调用 render_paginated_table()...")
    render_paginated_table(filtered_df)
    logger.debug(">>> render_paginated_table() 返回完成")

    # 重新从主数据集计算当前筛选视图，确保执行逻辑拿到最新选择状态
    edited_df = filter_test_cases(
        st.session_state.df,
        category_id=filter_category,
        tags=filter_tags,
        id_from=filter_id_from,
        id_to=filter_id_to,
        keyword=filter_keyword,
        priorities=filter_priority,
        modules=filter_module
    )

    # 全量选中行（跨所有目录/筛选条件），用于 Run/Delete/Move/Priority/Assert 操作
    all_selected = st.session_state.df[st.session_state.df.get("Select", False) == True]


    # ------------------
    # Execution Logic
    # ------------------
    cases_to_run = []
    run_report_name = None

    # 弹窗确认后的执行请求（Run 确认弹窗设置）
    # 三步rerun机制：
    #   帧1（dialog内）: 点"开始执行" → set confirmed_run + pop pending → rerun
    #   帧2: pop confirmed_run → set _executing_run → rerun（dialog 已不被调用，但需要一帧让DOM关闭）
    #   帧3: pop _executing_run → set _run_starting → rerun（再给一帧，彻底让dialog关闭flush到前端）
    #   帧4: pop _run_starting → 进入polling（此时dialog已完全关闭，不会出现截图里的半透明遮挡）
    _confirmed = st.session_state.pop('confirmed_run', None)
    if _confirmed:
        st.session_state['_executing_run'] = _confirmed
        st.rerun()

    _executing = st.session_state.pop('_executing_run', None)
    if _executing:
        st.session_state['_run_starting'] = _executing
        st.rerun()

    _starting = st.session_state.pop('_run_starting', None)
    if _starting:
        cases_to_run = _starting.get('cases') or []
        run_report_name = _starting.get('report_name')

    # 对话框待处理请求（单次消费，避免确认后反复命中 dialog）
    _pending_run_dialog = st.session_state.get('pending_run_dialog')
    if _pending_run_dialog and not _executing and not _starting:
        run_confirm_dialog(
            _pending_run_dialog.get('cases') or [],
            _pending_run_dialog.get('api_name') or selected_api,
            _pending_run_dialog.get('case_count') or 0,
        )

    if run_selected_clicked:
        selected_rows = all_selected
        if selected_rows.empty:
            execution_placeholder.warning("Please select cases to run.")
        else:
             _pending = selected_rows.drop(columns=["Select", "__row_key"], errors='ignore').to_dict(orient="records")
             _pending_case_count = _count_unique_case_ids_in_records(_pending)
             # 清除上次弹窗的输入状态，确保默认名带最新时间戳
             st.session_state.pop("run_report_name_input", None)
             st.session_state['pending_run_dialog'] = {
                 'cases': _pending,
                 'api_name': selected_api,
                 'case_count': _pending_case_count,
             }
             st.rerun()
             
    elif delete_selected_clicked:
        selected_rows = all_selected
        if selected_rows.empty:
            execution_placeholder.warning("Please select cases to delete.")
        else:
            ids_to_delete = selected_rows['id'].tolist()
            confirm_delete_dialog(ids_to_delete)
    
    elif move_to_category_clicked:
        selected_rows = all_selected

        if not selected_rows.empty:
            ids_to_move = selected_rows['id'].tolist()
            move_to_category_dialog(ids_to_move)
        else:
            execution_placeholder.warning("请先选择要移动的测试用例")

    elif batch_priority_clicked:
        selected_rows = all_selected
        if selected_rows.empty:
            execution_placeholder.warning("请先选择要设置 Priority 的测试用例")
        else:
            ids_to_update = selected_rows['id'].tolist()
            batch_priority_dialog(ids_to_update)

    elif batch_module_clicked:
        selected_rows = all_selected
        if selected_rows.empty:
            execution_placeholder.warning("请先选择要设置 Module 的测试用例")
        else:
            ids_to_update = selected_rows['id'].tolist()
            batch_module_dialog(ids_to_update)

    elif bind_assertions_clicked:
        selected_rows = all_selected
        if selected_rows.empty:
            execution_placeholder.warning("请先选择要绑定断言的测试用例")
        else:
            _assertion_binding_dialog(selected_rows['id'].tolist())

    elif refresh_dates_clicked:
        selected_rows = all_selected
        if selected_rows.empty:
            execution_placeholder.warning("请先选择要刷新日期的测试用例")
        else:
            from app.utils import refresh_dates_for_records
            records = selected_rows.drop(columns=["Select", "__row_key"], errors='ignore').to_dict(orient="records")
            try:
                updated_records, total_replaced = refresh_dates_for_records(records)
                if total_replaced == 0:
                    execution_placeholder.info("选中用例中没有需要刷新的过去日期（或日期已是未来 90 天内）")
                else:
                    # 持久化到 DB
                    save_records(updated_records)

                    # 同步更新内存 st.session_state.df，避免用户看不到变化
                    df = st.session_state.df
                    # 多轮用例相同 id 会有多条，用 (id, turn_index) 做 key
                    updated_map_multi = {}
                    for r in updated_records:
                        ti = r.get('turn_index', 1)
                        try:
                            ti = int(ti) if ti is not None else 1
                        except (TypeError, ValueError):
                            ti = 1
                        updated_map_multi[(r['id'], ti)] = r

                    # 日期刷新涉及的所有字段（原文 + 中文翻译 + retrieval）
                    _date_fields = ('input', 'input_cn', 'expected_output',
                                    'expected_output_cn', 'retrieval_context')
                    changed_cases = 0
                    for idx, row in df.iterrows():
                        rid = row.get('id')
                        rti = row.get('turn_index', 1)
                        try:
                            rti = int(rti) if not pd.isna(rti) else 1
                        except (TypeError, ValueError):
                            rti = 1
                        new_r = updated_map_multi.get((rid, rti))
                        if not new_r:
                            continue
                        row_changed = False
                        for fld in _date_fields:
                            new_val = new_r.get(fld)
                            if new_val is not None and new_val != row.get(fld):
                                df.at[idx, fld] = new_val
                                row_changed = True
                        if row_changed:
                            changed_cases += 1

                    # 清掉预处理标记，下次 render 重新做 schema 安全处理
                    st.session_state["df_preprocessed"] = False
                    st.session_state["edited_df_cached"] = None
                    st.success(f"✅ 已刷新 {changed_cases} 条用例中的 {total_replaced} 个日期（未来 90 天内，保持多日期先后顺序）")
                    st.rerun()
            except Exception as e:
                execution_placeholder.error(f"刷新日期失败: {e}")
    
    elif run_range_clicked:
        start_id = st.session_state.get('filter_id_from', '').strip()
        end_id = st.session_state.get('filter_id_to', '').strip()
        if not start_id and not end_id:
            execution_placeholder.warning("请在筛选条件中填写 From ID 或 To ID")
        else:
            # edited_df 已经根据 ID 范围筛选过了，直接使用
            if edited_df.empty:
                execution_placeholder.warning(f"No cases found in range {start_id or '*'} to {end_id or '*'}")
            else:
                _pending = edited_df.drop(columns=["Select", "__row_key"], errors='ignore').to_dict(orient="records")
                _pending_case_count = _count_unique_case_ids_in_records(_pending)
                st.session_state.pop("run_report_name_input", None)
                st.session_state['pending_run_dialog'] = {
                    'cases': _pending,
                    'api_name': selected_api,
                    'case_count': _pending_case_count,
                }
                st.rerun()
            
    elif run_tags_clicked:
        if not filter_tags:
            execution_placeholder.warning("请在筛选条件中选择标签")
        else:
            # Filter by tags
            def row_has_tag(row_tags):
                if not isinstance(row_tags, list): return False
                return any(tag in row_tags for tag in filter_tags)
            
            mask = edited_df['tags'].apply(row_has_tag)
            tags_rows = edited_df[mask]
            
            if tags_rows.empty:
                execution_placeholder.warning("No cases found with selected tags.")
            else:
                 _pending = tags_rows.drop(columns=["Select", "__row_key"], errors='ignore').to_dict(orient="records")
                 _pending_case_count = _count_unique_case_ids_in_records(_pending)
                 st.session_state.pop("run_report_name_input", None)
                 st.session_state['pending_run_dialog'] = {
                     'cases': _pending,
                     'api_name': selected_api,
                     'case_count': _pending_case_count,
                 }
                 st.rerun()
                 
    if cases_to_run:
        try:
             # Use JobManager (Async) but simulate sync experience with progress bar
            from app.job_manager import get_job_manager
            mgr = get_job_manager()
            
            # Start Job
            job_id = mgr.run_background_job(
                cases_to_run,
                api_name=selected_api,
                execution_mode=execution_mode_val,
                max_workers=_get_max_workers(),
                report_name=run_report_name,
            )
            
            with execution_placeholder.container():
                # Progress UI
                progress_bar = st.progress(0, text="Initializing...")
                status_text = st.empty()
                
                import time
                
                # Poll for completion from DB (with timeout)
                MAX_POLL_SECONDS = 30 * 60  # 30 minutes timeout
                elapsed = 0
                
                while elapsed < MAX_POLL_SECONDS:
                    time.sleep(1)
                    elapsed += 1
                    
                    try:
                        from app.services.history_service import HistoryService
                        svc = HistoryService()
                        job_data = svc.get_by_id(job_id)
                    except Exception:
                        continue
                    
                    if job_data:
                        status = job_data.get("status", "running")
                        
                        started = job_data.get("started_count", 0)
                        total = job_data.get("total", 1)
                        if total == 0: total = 1
                        
                        pct = min(started / total, 1.0)
                        progress_bar.progress(pct, text=f"Running... {started}/{total}")
                        
                        if status in ["completed", "failed", "cancelled", "interrupted"]:
                            if status == "completed":
                                progress_bar.progress(1.0, text=f"Finished: {status}")
                            elif status == "interrupted":
                                progress_bar.progress(pct, text=f"⚠️ Job interrupted ({started}/{total})")
                            elif status == "cancelled":
                                progress_bar.progress(pct, text=f"⏸ Cancelled ({started}/{total})")
                            else:
                                progress_bar.progress(pct, text=f"❌ Failed ({started}/{total})")
                            break
                    else:
                        status_text.warning("Job data not found...")
                        break
                else:
                    # Timeout reached
                    progress_bar.progress(pct if 'pct' in dir() else 0, text="⏱ Timeout")
                    status_text.warning("Job 仍在后台执行中（已超过 30 分钟），请到 **Test Report** 页查看进度。可在 Report 页使用 Continue 续跑功能。")
                    job_data = None  # Prevent results display below
                
                # Show results if completed
                if job_data and job_data.get("status") == "completed":
                    _ran_case_count = _count_unique_case_ids_in_records(cases_to_run)
                    st.toast(f"Completed! Ran {_ran_case_count} test cases.", icon="🏃")
                    st.success(f"✅ Successfully ran {_ran_case_count} test cases. View details in **Test Report**.")
                    
                elif job_data and job_data.get("status") == "failed":
                    err_msg = job_data.get('error_message') or job_data.get('error') or 'Unknown error'
                    st.error(f"Job failed: {err_msg}")
                elif job_data and job_data.get("status") == "interrupted":
                    st.warning("Job 已中断。已完成的结果已保存，请到 **Test Report** 页使用 Continue 按钮续跑。")
                elif job_data and job_data.get("status") == "cancelled":
                    st.info("Job 已被取消。已完成的结果已保存，可到 **Test Report** 页使用 Continue 续跑。")
            
        except Exception as e:
            execution_placeholder.error(f"Failed to run tests: {e}")

    # ─── 断言绑定弹窗通过按钮点击直接调用，无需 session_state flag ───
    logger.debug("=== render_testcases_page() 结束 ===")


@st.dialog("🧩 断言组件绑定", width="small")
def _assertion_binding_dialog(ids):
    """断言组件绑定弹窗 - 为选中的测试用例关联断言组件"""
    import json as _json
    from app.services.assertion_service import AssertionService

    if not ids:
        return

    st.caption(f"选中 {len(ids)} 个用例: {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}")

    service = AssertionService()
    all_components = service.get_all()

    if not all_components:
        st.info("组件库为空，请先在 Assertions 页面创建组件。")
        return

    # 组件 ID → 组件对象 映射（用于显示名称）
    comp_map = {c.id: c for c in all_components}

    # 当前已绑定的断言（取第一个选中用例的 assertions 展示）
    df = st.session_state.df
    first_case = df[df['id'] == ids[0]].iloc[0] if not df[df['id'] == ids[0]].empty else None
    current_assertions = []
    if first_case is not None:
        raw = first_case.get('assertions')
        if isinstance(raw, list):
            current_assertions = raw
        elif isinstance(raw, str) and raw.strip():
            try:
                current_assertions = _json.loads(raw)
            except:
                current_assertions = []

    # 展示当前已绑定的组件
    if current_assertions:
        st.markdown("**当前已绑定:**")
        for i, ref in enumerate(current_assertions):
            comp_id = ref.get('ref', '?')
            comp_obj = comp_map.get(comp_id)
            if comp_obj:
                display_name = f"{comp_obj.name}"
            else:
                display_name = comp_id

            col_a, col_b = st.columns([5, 1])
            with col_a:
                st.markdown(f"**{i+1}.** {display_name}")
            with col_b:
                if st.button("✕", key=f"unbind_{i}_{comp_id}"):
                    current_assertions.pop(i)
                    _apply_assertions_to_cases(ids, current_assertions)
                    st.rerun()
    else:
        st.caption("尚未绑定任何断言组件")

    # 添加新组件
    st.markdown("---")
    comp_options = {f"{c.name} ({c.category}/{c.condition})": c for c in all_components}
    selected_comp_key = st.selectbox("选择组件", options=[""] + list(comp_options.keys()), key="bind_comp_select", label_visibility="collapsed")

    if selected_comp_key and selected_comp_key in comp_options:
        comp = comp_options[selected_comp_key]
        config = comp.config or {}
        deferred = config.get("deferred_params", [])

        # 如果有活参数，让用户填写
        override_params = {}
        if deferred:
            st.caption("填写活参数:")
            for param_name in deferred:
                val = st.text_input(f"{param_name} =", key=f"bind_param_{param_name}")
                if val:
                    try:
                        override_params[param_name] = _json.loads(val)
                    except (ValueError, _json.JSONDecodeError):
                        override_params[param_name] = val

        if st.button("➕ 添加", key="btn_add_assertion", width="stretch"):
            new_ref = {"ref": comp.id, "params": override_params}
            current_assertions.append(new_ref)
            _apply_assertions_to_cases(ids, current_assertions)
            st.rerun()

    # 完成按钮 - 关闭弹窗
    st.markdown("---")
    if st.button("✔ 完成", key="btn_finish_binding", type="primary", use_container_width=True):
        st.rerun()


def _apply_assertions_to_cases(case_ids: list, assertions: list):
    """将 assertions 写入选中的测试用例"""
    import json as _json
    from app.services.test_case_service import TestCaseService

    # 更新 session state
    df = st.session_state.df
    for case_id in case_ids:
        mask = df['id'] == case_id
        df.loc[mask, 'assertions'] = df.loc[mask, 'assertions'].apply(lambda _: assertions)
    st.session_state.df = df

    # 持久化到 DB
    service = TestCaseService()
    from app.models.test_case import TestCase
    from datetime import datetime
    for case_id in case_ids:
        cases = service.db.query(TestCase).filter(TestCase.id == case_id).all()
        for tc in cases:
            tc.assertions = assertions
            tc.updated_at = datetime.utcnow()
    service.db.commit()
