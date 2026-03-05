import streamlit as st
import pandas as pd
import json
import os
import re
from app.utils import load_data, save_data

def render_tester_page():
    st.title("🔧 Tester - AI Test Case Generator")
    st.markdown("Generate test cases automatically using AI based on your requirements and knowledge base.")
    
    # Initialize session state for generated cases
    if "generated_cases" not in st.session_state:
        st.session_state.generated_cases = pd.DataFrame(columns=["id", "input", "expected_output", "retrieval_context", "description", "tags", "conversation"])
        
    if "saved_req" not in st.session_state:
        st.session_state.saved_req = ""
    if "saved_kb" not in st.session_state:
        st.session_state.saved_kb = ""
        
    def sync_req():
        st.session_state.saved_req = st.session_state.tester_requirements
    def sync_kb():
        st.session_state.saved_kb = st.session_state.tester_knowledge
    
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
                    prompt = f"""You are a testcase generator. Generate test cases based on the requirements and knowledge.
CRITICAL: You MUST output ONLY a valid JSON array of test case objects. Unless requested otherwise, all "input", "expected_output", and messages MUST be generated in Chinese (中文).

Requirements:
{requirements}

Knowledge Base:
{knowledge_base if knowledge_base.strip() else "No additional knowledge provided."}

The JSON format MUST strictly follow this flat schema. If generating a multi-turn conversation, DO NOT use a nested "conversation" array. Instead, output one distinct object per turn. Each turn object for the same conversation MUST have the exact same "description" and "type", but an incrementing "turn_index" starting at 1.

[
  {{
    "type": "multi_turn", // Use "multi_turn" if testing a sequence, else "single"
    "turn_index": 1, // Only use turn_index if multi_turn. 1 for first turn, 2 for second, etc.
    "tags": [], // CRITICAL: This MUST ALWAYS be an empty list []. Do not generate tags.
    "description": "Short description of the test case",
    "input": "User's message or goal for this specific turn (in Chinese)",
    "expected_output": "The detailed context, knowledge reference, or expected AI response for this turn (in Chinese)",
    "overall_criteria": {{"must_complete_all_turns": true, "min_success_rate": 0.8}} // Omit if not multi_turn
  }},
  {{
    "type": "multi_turn",
    "turn_index": 2, // Second turn continues the same conversation
    "tags": [],
    "description": "Short description of the test case", // Must be IDENTICAL to turn 1's description
    "input": "User's follow up message (in Chinese)",
    "expected_output": "Expected follow up response (in Chinese)"
  }}
]

ONLY return the highly-structured JSON array. Do not include markdown blocks like ```json or trailing text."""
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
                            
                            for case in cases_json:
                                desc = case.get("description", "Generated Test")
                                
                                # Assign new ID if description changes or it's turn 1 of single/new multi
                                if desc != last_description or case.get("turn_index", 1) == 1 or case.get("type", "single") == "single":
                                    current_id_counter += 1
                                    current_id = f"GEN_{str(current_id_counter).zfill(3)}"
                                    last_description = desc
                                    
                                flat_cases.append({
                                    "id": current_id,
                                    "type": case.get("type", "single"),
                                    "turn_index": case.get("turn_index", 1),
                                    "input": case.get("input", "N/A"),
                                    "expected_output": "",
                                    "retrieval_context": case.get("expected_output", "N/A"),
                                    "description": desc,
                                    "tags": [],
                                    "overall_criteria": json.dumps(case.get("overall_criteria", {"must_complete_all_turns": True, "min_success_rate": 0.8}), ensure_ascii=False)
                                })
                            
                            generated_df = pd.DataFrame(flat_cases)
                            
                            st.session_state.generated_cases = generated_df
                            st.success(f"✅ Generated {len(generated_df)} multi-turn test cases!")
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
                "overall_criteria": st.column_config.TextColumn("Criteria", disabled=True)
            },
            num_rows="dynamic",
            key="editor_generated",
            use_container_width=True
        )
        
        # Save to Library
        if st.button("💾 Save to Library", type="primary"):
            new_cases = edited_generated.to_dict(orient="records")
            
            # Format back to real JSON from string for criteria
            clean_new_cases = []
            for case in new_cases:
                try:
                    case["overall_criteria"] = json.loads(case["overall_criteria"]) if isinstance(case["overall_criteria"], str) else case.get("overall_criteria", {})
                except Exception:
                    pass # Keep as string if parsing fails
                
                # Delete generated ID to let system assign real one
                if "id" in case:
                    del case["id"]
                    
                clean_new_cases.append(case)

            # Load existing
            existing_df = load_data()
            if "Select" in existing_df.columns:
                 existing_df = existing_df.drop(columns=["Select"])
                 
            new_df = pd.DataFrame(clean_new_cases)
                
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            
            # Save
            final_df = save_data(combined_df)
            
            # Clear generated cases
            st.session_state.generated_cases = pd.DataFrame(columns=["id", "type", "turn_index", "input", "expected_output", "retrieval_context", "description", "tags"])
            
            # Update main df in session state
            if "df" in st.session_state:
                # Re-add select column for UI
                if "Select" not in final_df.columns:
                     final_df.insert(0, "Select", False)
                st.session_state.df = final_df
                # Update signature
                content_df = final_df.drop(columns=["Select"], errors='ignore')
                st.session_state.df_content_sig = content_df.to_json(orient='records', force_ascii=False)
            
            st.success(f"✅ Saved {len(new_cases)} test cases to library!")
            st.rerun()
