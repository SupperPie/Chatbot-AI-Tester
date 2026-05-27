import streamlit as st
import pandas as pd
import ast
import logging
from app.utils import load_data, save_data, run_tests_sync, save_history
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

def filter_test_cases(df, category_id=None, tags=None, id_from=None, id_to=None, keyword=None):
    """多维度筛选测试用例
    
    Args:
        df: 原始 DataFrame
        category_id: 目录 ID（含子目录）
        tags: 标签列表（OR 逻辑）
        id_from: ID 起始范围
        id_to: ID 结束范围
        keyword: 关键词搜索（匹配 input 字段）
    
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
        search_cols = [c for c in ['input', 'expected_output', 'retrieval_context'] if c in filtered.columns]
        mask = pd.Series(False, index=filtered.index)
        for col in search_cols:
            mask |= filtered[col].astype(str).str.lower().str.contains(keyword_lower, na=False)
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
        with st.popover("📖 参数说明手册", use_container_width=True):
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
    
    if "df_content_sig" not in st.session_state:
        st.session_state.df_content_sig = get_content_signature(st.session_state.df)

    @st.dialog("⚠️ Confirm Deletion")
    def confirm_delete_dialog(ids_to_delete):
        st.warning(f"Are you sure you want to permanently delete **{len(ids_to_delete)}** test cases? This action cannot be undone.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Cancel", use_container_width=True):
                st.rerun()
        with col2:
            if st.button("🗑️ Yes, Delete", type="primary", use_container_width=True):
                # 1. 先从 DB 删除
                try:
                    from app.services.test_case_service import TestCaseService
                    service = TestCaseService()
                    service.delete_by_ids(ids_to_delete)
                except Exception as e:
                    logger.warning(f"DB delete failed: {e}")

                # 2. 从 session state 移除并保存（JSON backup）
                current_df = st.session_state.df
                new_df = current_df[~current_df['id'].isin(ids_to_delete)]
                
                final_df = save_data(prepare_df_for_persistence(new_df))

                # Update session state
                if "Select" not in final_df.columns:
                     final_df.insert(0, "Select", False)
                final_df = rebuild_internal_ids(final_df)
                st.session_state.df = final_df
                st.session_state.df_content_sig = get_content_signature(final_df)
                st.session_state.df_preprocessed = False
                
                st.toast(f"🗑️ Deleted {len(ids_to_delete)} cases successfully!")
                st.rerun()

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
                if st.button("取消", use_container_width=True):
                    st.rerun()
            with col2:
                if st.button("✅ 确认移动", type="primary", use_container_width=True):
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
                        
                        st.toast(f"✅ 已将 {len(ids_to_move)} 个用例移动到目录")
                        st.rerun()
                    except Exception as e:
                        st.error(f"移动失败: {e}")
        except Exception as e:
            st.error(f"加载目录失败: {e}")

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

        st.markdown("#### ⚙️ Management")
        top_col1, top_col2, top_col3, top_col4 = st.columns([3, 1, 1, 1])
        with top_col1:
            available_apis = _cached_available_apis()
            selected_api = st.selectbox("⚙️ API Endpoint", options=available_apis, index=0, key="page_api_select", label_visibility="collapsed")
        with top_col2:
            move_to_category_clicked = st.button("📂 Move", use_container_width=True, key="btn_move_category") if ENABLE_CATEGORY_FEATURE else False
        with top_col3:
            bind_assertions_clicked = st.button("🧩 Assert", use_container_width=True, key="btn_bind_assertions")
        with top_col4:
            delete_selected_clicked = st.button("🗑️ Delete", use_container_width=True, key="btn_delete_selected")

        # 顶部右侧：Import（与参数说明手册同一行，下移避免贴顶裁剪）
        with import_container:
            st.markdown('<div style="height: 34px;"></div><div class="import-popover-anchor"></div>', unsafe_allow_html=True)
            with st.popover("📤 Import", use_container_width=True):
                 st.markdown('<div style="width: 400px; max-width: 90vw;">', unsafe_allow_html=True)
                 st.markdown("### Import Test Cases")
                 
                 # 目录选择
                 import_category = 'root'
                 if ENABLE_CATEGORY_FEATURE:
                     try:
                         from app.ui.components.category_selector import get_category_options
                         cat_opts = get_category_options()
                         import_category = st.selectbox(
                             "📂 目标目录",
                             options=[c[0] for c in cat_opts],
                             format_func=lambda x: next((c[1] for c in cat_opts if c[0] == x), x),
                             key="import_category_select"
                         )
                     except Exception:
                         st.text("目录加载失败，将导入到根目录")
                 
                 st.divider()
                 
                 # Download Template
                 try:
                     with open("docs/import_template.csv", "rb") as f:
                         st.download_button("📄 Download Template", data=f, file_name="import_template.csv", mime="text/csv", help="Download CSV template")
                 except Exception as e:
                     st.error(f"Template not found: {e}")
             
                 st.info("Upload CSV/JSON with `input`, `expected_output`.")
                 uploaded_file = st.file_uploader("Upload File", type=["csv", "json"], key="popover_uploader")
             
                 if uploaded_file is not None:
                    try:
                        if uploaded_file.name.endswith('.csv'):
                             try:
                                 import_df = pd.read_csv(uploaded_file, encoding='utf-8')
                             except UnicodeDecodeError:
                                 uploaded_file.seek(0)
                                 import_df = pd.read_csv(uploaded_file, encoding='gb18030')
                        else:
                            import_df = pd.read_json(uploaded_file)
                    
                        # Validation
                        required_cols = ["input", "expected_output"]
                        if not all(col in import_df.columns for col in required_cols):
                            st.error(f"Missing columns: {', '.join(required_cols)}")
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
                                
                                # 设置 category_id（导入到指定目录）
                                import_df["category_id"] = import_category

                                current_df = st.session_state.df.drop(columns=["Select"], errors='ignore')
                            
                                if update_existing:
                                    if "id" not in import_df.columns:
                                        st.error("Column 'id' is required for updating existing cases.")
                                        st.stop()
                                
                                    # Convert IDs to string for comparison
                                    current_df["id"] = current_df["id"].astype(str)
                                    import_df["id"] = import_df["id"].astype(str)
                                
                                    # Create a dict mapping ID to index in current_df for fast lookup
                                    id_to_index = {row_id: idx for idx, row_id in current_df["id"].items()}
                                
                                    updated_count = 0
                                    new_count = 0
                                
                                    for _, row in import_df.iterrows():
                                        row_id = row.get("id")
                                        if row_id in id_to_index:
                                            # Update existing
                                            idx = id_to_index[row_id]
                                            for col in row.index:
                                                val = row[col]
                                                # Only update if value is not empty/NaN
                                                # Skip ID update itself
                                                if col == "id": continue
                                            
                                                # Check empty/NaN
                                                # Using pd.isna(list) returns array of bools which fails if check
                                                is_empty = False
                                            
                                                if isinstance(val, list):
                                                    if not val: is_empty = True
                                                elif pd.isna(val):
                                                    is_empty = True
                                                elif isinstance(val, str) and not val.strip():
                                                    is_empty = True
                                            
                                                if not is_empty:
                                                    # Special handling for tags: merge or overwrite?
                                                    # Request said "update", usually implies overwrite or list-merge
                                                    # Let's overwrite for simplicity unless user asks otherwise, 
                                                    # or maybe merge unique?
                                                    # "Update non-empty fields" -> Overwrite existing field with new non-empty value
                                                    if col == "tags":
                                                        # Fix: Ensure logic handles list properly
                                                        current_df.at[idx, col] = val
                                                    else:
                                                        current_df.at[idx, col] = val
                                            updated_count += 1
                                        else:
                                            # It's a new ID or ID not present -> Append
                                            # We can just append to a list and concat later or append to DF
                                            # Appending to DF row by row is slow, but consistent here.
                                            # Better: Collect new rows
                                            pass 
                                
                                    # Filter import_df for ONLY new rows to concat
                                    existing_ids = set(current_df["id"])
                                    new_rows_df = import_df[~import_df["id"].isin(existing_ids)]
                                    new_count = len(new_rows_df)
                                
                                    combined_df = pd.concat([current_df, new_rows_df], ignore_index=True)
                                    st.toast(f"Updated {updated_count} cases, Added {new_count} new cases.")
                                
                                else:
                                    # Standard Append Mode (Drop ID to regenerate)
                                    if "id" in import_df.columns:
                                        del import_df["id"]
                                
                                    combined_df = pd.concat([current_df, import_df], ignore_index=True)
                                    st.toast(f"Imported {len(import_df)} new cases.")
                            
                                # Save to JSON using raw unique IDs
                                final_df = save_data(prepare_df_for_persistence(combined_df))
                                
                                # 同步写入数据库（新增的用例）
                                if ENABLE_CATEGORY_FEATURE and not update_existing:
                                    try:
                                        from app.database import SessionLocal
                                        from app.models.test_case import TestCase
                                        from datetime import datetime
                                        
                                        db = SessionLocal()
                                        for _, row in import_df.iterrows():
                                            # 查找最终分配的 ID
                                            final_row = final_df[final_df['input'] == row['input']]
                                            if not final_row.empty:
                                                case_id = final_row.iloc[0]['id']
                                                # 检查是否已存在
                                                ti = int(row.get('turn_index') or 1)
                                                existing = db.query(TestCase).filter(
                                                    TestCase.id == case_id,
                                                    TestCase.turn_index == ti
                                                ).first()
                                                if not existing:
                                                    test_case = TestCase(
                                                        id=case_id,
                                                        type=row.get('type', 'single'),
                                                        input=row.get('input', ''),
                                                        expected_output=row.get('expected_output', ''),
                                                        retrieval_context=row.get('retrieval_context'),
                                                        description=row.get('description'),
                                                        turn_index=ti,
                                                        tags=row.get('tags', []),
                                                        category_id=import_category,
                                                        created_at=datetime.utcnow()
                                                    )
                                                    db.add(test_case)
                                        db.commit()
                                        db.close()
                                    except Exception as e:
                                        logger.warning(f"数据库同步失败: {e}")
                            
                                # Update State
                                if "Select" not in final_df.columns:
                                     final_df.insert(0, "Select", False)
                                final_df = rebuild_internal_ids(final_df)
                                st.session_state.df = final_df
                                st.session_state.df_content_sig = get_content_signature(final_df)
                                st.session_state.df_preprocessed = False
                            
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
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([2.8, 1.2, 1.2, 2.3])

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
            run_selected_clicked = st.button("▶ Run Selected", use_container_width=True, type="primary", key="btn_run_selected")
        with run_col2:
            run_range_clicked = st.button("▶ Run Range", use_container_width=True, type="primary", key="btn_run_range", help="执行 From ID 到 To ID 范围内的用例")
        with run_col3:
            run_tags_clicked = st.button("▶ Run by Tags", use_container_width=True, type="primary", key="btn_run_tags") if filter_tags else False

        # 为执行状态留一个占位符，位于运行按钮的正下方
        execution_placeholder = st.empty()

    # 使用左侧目录树的选择作为目录筛选条件
    filter_category = selected_category

    # 节点切换时重置到第一页，避免页码越界导致空表/残留
    if st.session_state.get('last_selected_category') != filter_category:
        st.session_state.testcases_current_page = 1
        st.session_state.last_selected_category = filter_category
        # 清除目录统计缓存，强制重新加载
        st.session_state.pop('category_counts_cache', None)

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
        keyword=filter_keyword
    )
    
    # Debug: 输出筛选结果
    if filter_category and filter_category not in ('__all__', ''):
        logger.debug(f"Category filter: {filter_category}")
        logger.debug(f"Total rows in df: {len(st.session_state.df)}")
        logger.debug(f"Filtered rows: {len(filtered_df)}")
        if len(filtered_df) == 0 and len(st.session_state.df) > 0:
            # 显示有哪些 category_id
            unique_cats = st.session_state.df['category_id'].unique() if 'category_id' in st.session_state.df.columns else []
            logger.warning(f"筛选结果为空！现有 category_id: {unique_cats}")
    
    # 统计信息（选择控制与分页将在同一行渲染）
    total_count = len(st.session_state.df)
    filtered_count = len(filtered_df)

    @st.fragment
    def render_paginated_table(display_df):
        logger.debug(">>> render_paginated_table() fragment 开始")

        if "testcases_page_size" not in st.session_state:
            st.session_state.testcases_page_size = 20

        total_items = len(display_df)

        # 选择控制 + 统计 + 每页 + 分页（同一行）
        ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4, ctrl_col5, ctrl_col6 = st.columns([1.35, 1.35, 1.15, 1.95, 1.0, 5.2])

        with ctrl_col1:
            # 全表（跨页）全选：以当前表格数据（display_df）为准
            if st.button("☑️ Select All", key="btn_select_all_global", use_container_width=True, type="primary"):
                if '__row_key' in display_df.columns:
                    target_keys = display_df['__row_key'].tolist()
                    st.session_state.df.loc[st.session_state.df['__row_key'].isin(target_keys), 'Select'] = True
                else:
                    st.session_state.df['Select'] = True
                st.rerun()

        with ctrl_col2:
            # 当前页全选（与 Cancel All 交换位置）
            if st.button("☑️ Select page", key="btn_select_current_page", use_container_width=True):
                if '__row_key' in display_df.columns:
                    start_idx = (st.session_state.testcases_current_page - 1) * st.session_state.testcases_page_size
                    end_idx = start_idx + st.session_state.testcases_page_size
                    page_keys = display_df.iloc[start_idx:end_idx]['__row_key'].tolist()
                    st.session_state.df.loc[st.session_state.df['__row_key'].isin(page_keys), 'Select'] = True
                st.rerun()

        with ctrl_col3:
            # Cancel All（紫色背景，与 Select Page 交换位置）
            if st.button("Cancel All", key="btn_deselect_all", use_container_width=True):
                st.session_state.df['Select'] = False
                st.rerun()

        with ctrl_col4:
            selected_count = st.session_state.df[st.session_state.df.get('Select', False) == True].shape[0] if 'Select' in st.session_state.df.columns else 0
            filter_info = f"筛选: {filtered_count}/{total_count}" if filtered_count < total_count else f"共 {total_count} 条"
            st.markdown('<div style="padding-top: 8px;">📊 {} | ✅ 已选: <b>{}</b> 条</div>'.format(filter_info, selected_count), unsafe_allow_html=True)

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
                key=f"sac_testcases_pagination_{filter_category}"
            )

            if current_page_idx != st.session_state.testcases_current_page:
                st.session_state.testcases_current_page = current_page_idx
                st.rerun()

        start_idx = (st.session_state.testcases_current_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_df = display_df.iloc[start_idx:end_idx].copy()

        # 将 assertions 列转为可读文本显示（组件名称而非 ID）
        if 'assertions' in page_df.columns:
            def _format_assertions(val):
                if not val or val == '[]':
                    return ""
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

        edited_page_df = st.data_editor(
            page_df,
            column_config={
                "Select": st.column_config.CheckboxColumn("✓", width="small", default=False),
                "id": st.column_config.TextColumn("ID", width="small", disabled=False),
                "input": st.column_config.TextColumn("Input Question", width="medium"),
                "expected_output": st.column_config.TextColumn("Expected Output", width="medium"),
                "tags": st.column_config.ListColumn("Tags"),
                "retrieval_context": st.column_config.Column("Retrieval Context", help="为大模型提供的参考上下文文件。用于验证模型的回答是否基于给定的知识库 (Faithfulness)。"),
                "overall_criteria": st.column_config.Column("Overall Criteria", help="用于评估打分的特殊判定要求或全局自定义标准。"),
                "validation": st.column_config.Column("Validation", help="验证规则 (JSON格式)。例: {\"type\": \"contains\", \"keywords\": [\"正确\"]} 或 {\"type\": \"semantic\"}。"),
                "turn_index": st.column_config.NumberColumn("Turn", width="small", help="多轮对话的顺序编号"),
                "assertions": st.column_config.TextColumn("Assertions", help="已绑定的断言组件", width="small", disabled=True),
                "category_id": None,
                "__row_key": None,
            },
            num_rows="dynamic",
            use_container_width=False,
            height=(len(page_df) + 1) * 35 + 40,
            key=f"main_data_editor_{filter_category}_{st.session_state.testcases_current_page}_{st.session_state.testcases_page_size}"
        )

        # 同步选择状态（按 __row_key）
        if 'Select' in edited_page_df.columns and '__row_key' in edited_page_df.columns:
            for i in range(len(edited_page_df)):
                rk = edited_page_df.iloc[i]['__row_key']
                st.session_state.df.loc[st.session_state.df['__row_key'] == rk, 'Select'] = edited_page_df.iloc[i]['Select']

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
                st.toast(f"New row(s) added and saved!", icon="➕")
                st.rerun()

        # 自动保存：仅当内容列被修改时（排除 Select 列，避免勾选触发保存并丢失选中状态）
        _content_cols = [c for c in page_df.columns if c != 'Select']
        page_edited = not edited_page_df[_content_cols].reset_index(drop=True).equals(
            page_df[_content_cols].reset_index(drop=True)
        )
        if page_edited:
            for _, row in edited_page_df.iterrows():
                rk = row['__row_key']
                main_idx = st.session_state.df.index[st.session_state.df['__row_key'] == rk]
                for col in edited_page_df.columns:
                    if col in st.session_state.df.columns and col != 'Select':
                        val = row[col]
                        # 对 list/dict 等可迭代值，需逐行用 at 赋值避免 pandas 展开
                        if isinstance(val, (list, dict)):
                            for idx in main_idx:
                                st.session_state.df.at[idx, col] = val
                        else:
                            st.session_state.df.loc[main_idx, col] = val

            # 保存前记住当前选中状态
            select_backup = st.session_state.df[['__row_key', 'Select']].copy()

            # 保存时恢复原始唯一ID，并剔除内部列
            save_df = prepare_df_for_persistence(st.session_state.df)
            saved_df_clean = save_data(save_df)

            if "Select" not in saved_df_clean.columns:
                saved_df_clean.insert(0, "Select", False)

            # 重新补回内部键并恢复规范化展示ID
            saved_df_clean = rebuild_internal_ids(saved_df_clean)

            # 恢复选中状态
            for _, bk_row in select_backup.iterrows():
                mask = saved_df_clean['__row_key'] == bk_row['__row_key']
                if mask.any():
                    saved_df_clean.loc[mask, 'Select'] = bk_row['Select']

            st.session_state.df = saved_df_clean
            st.session_state.df_content_sig = get_content_signature(st.session_state.df)
            st.toast("✅ Changes saved automatically!", icon="💾")

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
        keyword=filter_keyword
    )


    # ------------------
    # Execution Logic
    # ------------------
    cases_to_run = []
    
    if run_selected_clicked:
        selected_rows = edited_df[edited_df["Select"] == True]
        if selected_rows.empty:
            execution_placeholder.warning("Please select cases to run.")
        else:
             cases_to_run = selected_rows.drop(columns=["Select", "__row_key"], errors='ignore').to_dict(orient="records")
             
    elif delete_selected_clicked:
        selected_rows = edited_df[edited_df["Select"] == True]
        if selected_rows.empty:
            execution_placeholder.warning("Please select cases to delete.")
        else:
            ids_to_delete = selected_rows['id'].tolist()
            confirm_delete_dialog(ids_to_delete)
    
    elif move_to_category_clicked:
        selected_rows = edited_df[edited_df["Select"] == True]
        start_id = st.session_state.get('filter_id_from', '').strip()
        end_id = st.session_state.get('filter_id_to', '').strip()
        
        if not selected_rows.empty:
            ids_to_move = selected_rows['id'].tolist()
            move_to_category_dialog(ids_to_move)
        elif start_id or end_id:
            if edited_df.empty:
                execution_placeholder.warning(f"No cases found in range {start_id or '*'} to {end_id or '*'}")
            else:
                ids_to_move = edited_df['id'].tolist()
                move_to_category_dialog(ids_to_move)
        else:
            execution_placeholder.warning("请先选择要移动的测试用例")

    elif bind_assertions_clicked:
        selected_rows = edited_df[edited_df["Select"] == True]
        if selected_rows.empty:
            execution_placeholder.warning("请先选择要绑定断言的测试用例")
        else:
            st.session_state["show_assertion_binding"] = True
            st.session_state["assertion_binding_ids"] = selected_rows['id'].tolist()
            st.rerun()
    
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
                cases_to_run = edited_df.drop(columns=["Select", "__row_key"], errors='ignore').to_dict(orient="records")
            
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
                 cases_to_run = tags_rows.drop(columns=["Select", "__row_key"], errors='ignore').to_dict(orient="records")
                 
    if cases_to_run:
        try:
             # Use JobManager (Async) but simulate sync experience with progress bar
            from app.job_manager import get_job_manager
            mgr = get_job_manager()
            
            # Start Job
            job_id = mgr.run_background_job(cases_to_run, api_name=selected_api, execution_mode=execution_mode_val)
            
            with execution_placeholder.container():
                # Progress UI
                progress_bar = st.progress(0, text="Initializing...")
                status_text = st.empty()
                
                import time
                
                # Poll for completion from DB
                while True:
                    time.sleep(1)
                    
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
                        
                        if status in ["completed", "failed", "cancelled"]:
                            progress_bar.progress(1.0, text=f"Finished: {status}")
                            break
                    else:
                        status_text.warning("Job data not found...")
                        break
                
                # Show results if completed
                if job_data and job_data.get("status") == "completed":
                    st.toast(f"Completed! Ran {len(cases_to_run)} tests.", icon="🏃")
                    st.success(f"Successfully ran {len(cases_to_run)} tests. View details in **Test Report**.")
                    
                    # Show simplified results result
                    results = job_data.get("results", [])
                    res_df = pd.DataFrame(results)
                    cols = ["id", "input", "passed", "score", "reason"]
                    cols = [c for c in cols if c in res_df.columns]
                    st.dataframe(res_df[cols].style.format({"score": "{:.2f}"}), use_container_width=True)
                    
                elif job_data and job_data.get("status") == "failed":
                    st.error(f"Job failed: {job_data.get('error')}")
            
        except Exception as e:
            execution_placeholder.error(f"Failed to run tests: {e}")

    # ─── 断言绑定弹窗 ───
    if st.session_state.get("show_assertion_binding", False):
        _assertion_binding_dialog()

    logger.debug("=== render_testcases_page() 结束 ===")


@st.dialog("🧩 断言组件绑定", width="small")
def _assertion_binding_dialog():
    """断言组件绑定弹窗 - 为选中的测试用例关联断言组件"""
    import json as _json
    from app.services.assertion_service import AssertionService

    ids = st.session_state.get("assertion_binding_ids", [])
    if not ids:
        st.session_state["show_assertion_binding"] = False
        st.rerun()
        return

    st.caption(f"选中 {len(ids)} 个用例: {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}")

    service = AssertionService()
    all_components = service.get_all()

    if not all_components:
        st.info("组件库为空，请先在 Assertions 页面创建组件。")
        if st.button("关闭"):
            st.session_state["show_assertion_binding"] = False
            st.rerun()
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

        if st.button("➕ 添加", key="btn_add_assertion", use_container_width=True):
            new_ref = {"ref": comp.id, "params": override_params}
            current_assertions.append(new_ref)
            _apply_assertions_to_cases(ids, current_assertions)
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
