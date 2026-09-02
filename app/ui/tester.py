import streamlit as st
import pandas as pd
import json
import os
import re
from app.utils import load_data, save_data
from app.ui.prompts.intent_prompts import (
    INTENT_OPTIONS,
    INTENT_DEFAULT,
    build_prompt,
    get_requirement_template,
    get_tags_for_intent,
)

def render_tester_page():
    st.title("🔧 Tester - AI Test Case Generator")
    st.markdown("Generate test cases automatically using AI based on your requirements and knowledge base.")
    
    # Initialize session state for generated cases
    if "generated_cases" not in st.session_state:
        st.session_state.generated_cases = pd.DataFrame(columns=["id", "input", "expected_output", "retrieval_context", "description", "tags", "conversation", "priority"])
        
    if "saved_req" not in st.session_state:
        st.session_state.saved_req = ""
    if "saved_kb" not in st.session_state:
        st.session_state.saved_kb = ""
    if "selected_intent" not in st.session_state:
        st.session_state.selected_intent = INTENT_DEFAULT
        
    def sync_req():
        st.session_state.saved_req = st.session_state.tester_requirements
    def sync_kb():
        st.session_state.saved_kb = st.session_state.tester_knowledge

    def on_intent_change():
        intent = st.session_state.tester_intent
        st.session_state.selected_intent = intent
        template = get_requirement_template(intent)
        # 仅当模板非空时填充（默认意图为空字符串，不覆盖用户已有输入）
        if template:
            st.session_state.saved_req = template
            # 同步 text_area widget 的值，确保下次 rerun 时 text_area 显示新内容
            st.session_state.tester_requirements = template

    # 意图选择下拉（固定宽度，不充满整行）
    intent_col, _ = st.columns([1, 3])
    with intent_col:
        st.selectbox(
            "🎯 测试用例模板",
            options=INTENT_OPTIONS,
            index=INTENT_OPTIONS.index(st.session_state.selected_intent),
            key="tester_intent",
            on_change=on_intent_change,
            help="选择不同模板会切换 Prompt 策略并自动填充测试需求模板（默认选项不改动现有行为）",
        )

    # Two-column layout for inputs
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📝 Test Requirements")
        requirements = st.text_area(
            "Describe what test cases you want to generate",
            value=st.session_state.saved_req,
            height=200,
            placeholder="Example:\n- Generate 5 test cases about user login\n- Include edge cases for invalid passwords\n- Test both Chinese and English inputs",
            key="tester_requirements",
            on_change=sync_req
        )
    
    with col2:
        st.subheader("📚 Knowledge Base")
        knowledge_base = st.text_area(
            "Paste your knowledge, documentation, or facts",
            value=st.session_state.saved_kb,
            height=200,
            placeholder="Paste relevant information here:\n\nExample:\n- Users can login with email or phone number\n- Password must be 8-20 characters\n- System supports Chinese and English",
            key="tester_knowledge",
            on_change=sync_kb
        )
    
    # Generator button
    gen_col1, gen_col2, gen_col3 = st.columns([1, 1, 2])
    with gen_col1:
        generate_clicked = st.button(
            "⚡ Generate Test Cases",
            type="primary",
            use_container_width=True,
            key="btn_generate_cases"
        )
    
    # Handle generation
    if generate_clicked:
        if not requirements.strip():
            st.warning("Please enter test requirements first.")
        else:
            with st.spinner("🤖 AI is generating test cases..."):
                try:
                    prompt = build_prompt(
                        intent=st.session_state.selected_intent,
                        requirements=requirements,
                        knowledge_base=knowledge_base,
                    )
                    try:
                        from openai import OpenAI
                        
                        api_key = os.getenv("COMPATIBLE_API_KEY")
                        base_url = os.getenv("COMPATIBLE_BASE_URL")
                        model_name = os.getenv("COMPATIBLE_MODEL", "qwen3-max")
                        
                        if not api_key:
                            st.warning("⚠️ 缺省 COMPATIBLE_API_KEY 环境变量，本次自动生成可能会失败。")
                        
                        client = OpenAI(
                            api_key=api_key,
                            base_url=base_url
                        )
                        completion = client.chat.completions.create(
                            model=model_name, 
                            messages=[
                                {"role": "system", "content": "You are a helpful QA assistant."},
                                {"role": "user", "content": prompt}
                            ]
                        )
                        response = completion.choices[0].message.content
                    except Exception as e:
                        st.error(f"⚠️ 大模型调用失败 (请检查 .env 中的 API_KEY / BASE_URL 配置):\n\n{e}")
                        response = ""
                    
                    # Parse the response
                    # Try to extract JSON array from response
                    json_match = re.search(r'\[[\s\S]*\]', response)
                    if json_match:
                        cases_json = json.loads(json_match.group())
                        
                        # Create DataFrame with generated cases
                        if cases_json:
                            # We flatten it for the UI editor, distributing IDs correctly
                            flat_cases = []
                            current_id_counter = 0
                            last_description = None
                            current_id = None
                            intent_tags = get_tags_for_intent(st.session_state.selected_intent)
                            
                            for case in cases_json:
                                case_type = case.get("type", "single")
                                turn_idx = case.get("turn_index", 1)

                                # Assign new ID if it's a single turn OR the first turn of a multi-turn
                                if case_type != "multi_turn" or turn_idx == 1:
                                    current_id_counter += 1
                                    current_id = f"GEN_{str(current_id_counter).zfill(3)}"

                                flat_cases.append({
                                    "id": current_id,
                                    "type": case.get("type", "single"),
                                    "turn_index": case.get("turn_index", 1),
                                    "input": case.get("input", "N/A"),
                                    "expected_output": "",
                                    "retrieval_context": case.get("expected_output", "N/A"),
                                    "description": "",
                                    "tags": list(intent_tags),
                                    "overall_criteria": json.dumps(case.get("overall_criteria", {"must_complete_all_turns": True, "min_success_rate": 0.8}), ensure_ascii=False),
                                    "priority": "P2",
                                })

                            generated_df = pd.DataFrame(flat_cases)

                            # Priority 分配：同次 PRD 生成结果按 P1:P2 = 1:3（跨 AC 汇总）
                            n = len(generated_df)
                            if n > 0:
                                p1_count = max(1, round(n * 0.25))
                                generated_df.loc[:, "priority"] = "P2"
                                generated_df.iloc[:p1_count, generated_df.columns.get_loc("priority")] = "P1"

                            st.session_state.generated_cases = generated_df
                            p1_total = int((generated_df["priority"] == "P1").sum()) if not generated_df.empty else 0
                            p2_total = int((generated_df["priority"] == "P2").sum()) if not generated_df.empty else 0
                            st.success(f"✅ Generated {len(generated_df)} test cases! Priority 分配：P1={p1_total}, P2={p2_total}")
                    else:
                        st.error("Failed to parse AI response. Please try again.")
                        st.text("AI Response:")
                        st.code(response)
                        
                except Exception as e:
                    st.error(f"Generation failed: {e}")
    
    st.divider()
    
    # Show generated cases in editable table
    st.subheader("📋 Generated Test Cases")
    
    if not st.session_state.generated_cases.empty:
        edited_generated = st.data_editor(
            st.session_state.generated_cases,
            column_config={
                "id": st.column_config.TextColumn("ID", width="small", disabled=True),
                "type": st.column_config.TextColumn("Type", disabled=True),
                "turn_index": st.column_config.NumberColumn("Turn", width="small", disabled=True),
                "input": st.column_config.TextColumn("Input Goal", width="medium"),
                "expected_output": st.column_config.TextColumn("Expected Goal", width="medium"),
                "retrieval_context": st.column_config.TextColumn("Retrieval Context", width="large"),
                "description": st.column_config.TextColumn("Description", width="medium"),
                "tags": st.column_config.ListColumn("Tags"),
                "overall_criteria": st.column_config.TextColumn("Criteria", disabled=True),
                "priority": st.column_config.SelectboxColumn("Priority", options=["P0", "P1", "P2"], width="small")
            },
            num_rows="dynamic",
            key="editor_generated",
            use_container_width=True
        )
        
        # 目录选择（必须在 save_clicked 判断之前获取）
        save_category = None
        save_clicked = False
        
        try:
            from app.ui.components.category_selector import get_category_options
            cat_opts = get_category_options()
            if cat_opts:
                save_col1, save_col2 = st.columns([2, 1])
                with save_col1:
                    save_category = st.selectbox(
                        "📂 保存到目录",
                        options=[c[0] for c in cat_opts],
                        format_func=lambda x: next((c[1] for c in cat_opts if c[0] == x), x),
                        key="tester_save_category"
                    )
                with save_col2:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    save_clicked = st.button("💾 Save to Library", type="primary", use_container_width=True)
            else:
                save_category = None  # 无目录时设为 None
                save_clicked = st.button("💾 Save to Library", type="primary")
        except Exception as e:
            save_category = None
            save_clicked = st.button("💾 Save to Library", type="primary")
            st.warning(f"目录加载失败: {e}")
        
        # Save to Library
        if save_clicked:
            # 确保 save_category 有值
            if save_category is None:
                st.warning("⚠️ 未选择目录，将保存到根目录")
                save_category = None  # 明确设为 None，让数据库处理
            new_cases = edited_generated.to_dict(orient="records")
            
            # Format back to real JSON from string for criteria
            clean_new_cases = []
            # ========================================================================
            # 【重要】多轮对话ID共享逻辑 - 请勿随意修改！
            # ========================================================================
            # 设计说明：
            # - 一个ID代表一个会话，同一多轮对话的所有turn共享同一个ID
            # - 数据库使用复合主键 (id, turn_index)，允许同ID多条记录
            # - 生成时：同一会话的多个turn共享 GEN_xxx ID
            # - 保存时：需要把 GEN_xxx 映射到 TCxxxx，同组turn必须映射到同一个TC ID
            # 
            # 实现方式：
            # 1. 用 _original_gen_id 临时字段保存原始 GEN_xxx ID
            # 2. 用 gen_id_to_tc_id 字典跟踪已分配的映射
            # 3. 同一 GEN_xxx 的记录复用已分配的 TC ID
            # ========================================================================
            gen_id_mapping = {}  # GEN_xxx -> TC新ID 的映射，确保同一会话共享ID
            
            for case in new_cases:
                try:
                    case["overall_criteria"] = json.loads(case["overall_criteria"]) if isinstance(case["overall_criteria"], str) else case.get("overall_criteria", {})
                except Exception:
                    pass # Keep as string if parsing fails
                    
                # 记录原始 GEN_ ID，用于后续映射
                case_id = str(case.get("id", ""))
                if case_id.startswith("GEN_"):
                    case["_original_gen_id"] = case_id  # 保存原始ID用于后续分组
                    case["id"] = ""
                
                # 设置目录
                case["category_id"] = save_category
                    
                clean_new_cases.append(case)
            
            # 调试信息：显示将要保存的目录
            if save_category:
                st.info(f"📂 将保存到目录: {save_category} (共 {len(clean_new_cases)} 条用例)")
            else:
                st.info(f"📂 将保存到根目录 (共 {len(clean_new_cases)} 条用例)")

            # 只插入新记录到数据库（不做全量同步）
            try:
                existing_df = load_data()
                print(f"[save] load_data 完成，共 {len(existing_df)} 条现有记录")
            except Exception as e:
                import traceback
                st.error(f"❌ 加载现有用例失败: {e}")
                st.code(traceback.format_exc())
                return

            try:
                if "Select" in existing_df.columns:
                     existing_df = existing_df.drop(columns=["Select"])

                new_df = pd.DataFrame(clean_new_cases)
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)

                from app.services.test_case_service import TestCaseService
                from app.utils import generate_tc_id

                service = TestCaseService()
                print("[save] TestCaseService 初始化 OK")

                # 获取当前最大 ID 用于生成新 ID
                all_ids = existing_df['id'].dropna().tolist() if 'id' in existing_df.columns else []
                max_num = 0
                for tid in all_ids:
                    if tid.startswith('TC') and tid[2:].isdigit():
                        max_num = max(max_num, int(tid[2:]))
                print(f"[save] 当前最大 TC 编号: {max_num}")

                # 为新记录分配 ID 并插入（同一多轮会话共享同一个ID）
                gen_id_to_tc_id = {}  # GEN_xxx -> TCxxxx 映射
                for case in clean_new_cases:
                    if not case.get('id'):
                        original_gen_id = case.pop('_original_gen_id', None)
                        if original_gen_id and original_gen_id in gen_id_to_tc_id:
                            # 同一个多轮会话，复用已分配的 TC ID
                            case['id'] = gen_id_to_tc_id[original_gen_id]
                        else:
                            # 新的会话，分配新 ID
                            max_num += 1
                            new_tc_id = generate_tc_id(max_num - 1)
                            case['id'] = new_tc_id
                            if original_gen_id:
                                gen_id_to_tc_id[original_gen_id] = new_tc_id
                    else:
                        # 清理可能遗留的临时字段
                        case.pop('_original_gen_id', None)
                    case['category_id'] = save_category

                print(f"[save] ID 分配完成，准备写入 {len(clean_new_cases)} 条")

                # 写入前确认目录存在，否则降级到 root（避免外键约束静默拒绝写入）
                if save_category and save_category != 'root':
                    from app.services.category_service import CategoryService
                    cat_svc = CategoryService()
                    if not cat_svc.get_by_id(save_category):
                        print(f"[save] 目录 {save_category} 不存在，降级到 root")
                        save_category = 'root'
                        for case in clean_new_cases:
                            case['category_id'] = 'root'

                inserted = service.insert_many(clean_new_cases)
                print(f"[save] insert_many 返回 {inserted} 条")

                # 更新 combined_df 中的新记录 ID
                for i, case in enumerate(clean_new_cases):
                    idx = len(existing_df) + i
                    if idx < len(combined_df):
                        combined_df.at[idx, 'id'] = case['id']

            except Exception as e:
                import traceback
                st.error(f"❌ 保存失败: {e}")
                st.code(traceback.format_exc())
                return  # 失败时不清空、不 rerun
            
            final_df = combined_df
            
            # 保存成功后的处理
            saved_count = inserted
            
            # Clear generated cases
            st.session_state.generated_cases = pd.DataFrame(columns=["id", "type", "turn_index", "input", "expected_output", "retrieval_context", "description", "tags", "priority"])
            
            # Update main df in session state
            if "df" in st.session_state:
                # Re-add select column for UI
                if "Select" not in final_df.columns:
                     final_df.insert(0, "Select", False)
                st.session_state.df = final_df
                # Update signature
                content_df = final_df.drop(columns=["Select"], errors='ignore')
                st.session_state.df_content_sig = content_df.to_json(orient='records', force_ascii=False)
            
            st.success(f"✅ 成功保存 {saved_count} 条测试用例到用例库！")
            st.info("💡 生成区已清空。如需继续生成，请重新填写需求后点击 Generate。已保存的用例可在 **Test Cases** 页面查看和管理。")
            # 不再立即 rerun，让用户看到成功消息
            # st.rerun()
