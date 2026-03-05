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
        st.session_state.generated_cases = pd.DataFrame(columns=["id", "input", "expected_output", "description", "tags", "conversation"])
        
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
CRITICAL: You MUST output ONLY a valid JSON array of test case objects. Each test case MUST explicitly be of type "multi_turn" and contain a "conversation" array, even if it's just 1 turn.

Requirements:
{requirements}

Knowledge Base:
{knowledge_base if knowledge_base.strip() else "No additional knowledge provided."}

The JSON format MUST strictly follow this schema:
[
  {{
    "type": "multi_turn",
    "tags": ["example_tag"],
    "description": "Short description of the test case",
    "input": "Summary or title of the user's overall goal",
    "expected_output": "Summary of the final expected state",
    "conversation": [
      {{
        "turn": 1,
        "user": "First user message",
        "expected": "Expected AI response",
        "validation": {{"type": "semantic", "threshold": 0.5}}
      }},
      {{
        "turn": 2,
        "user": "Follow up message",
        "expected": "Expected follow up response",
        "validation": {{"type": "semantic", "threshold": 0.5}}
      }}
    ],
    "overall_criteria": {{"must_complete_all_turns": true, "min_success_rate": 0.8}}
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
                            # We flatten it slightly for the UI editor, but keep conversation intact
                            flat_cases = []
                            for i, case in enumerate(cases_json):
                                flat_cases.append({
                                    "id": f"GEN_MULTI_{str(i+1).zfill(3)}",
                                    "type": "multi_turn",
                                    "input": case.get("input", "N/A"),
                                    "expected_output": case.get("expected_output", "N/A"),
                                    "description": case.get("description", f"Generated Test {i+1}"),
                                    "tags": case.get("tags", []),
                                    "conversation": json.dumps(case.get("conversation", []), ensure_ascii=False),
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
                "input": st.column_config.TextColumn("Input Goal", width="medium"),
                "expected_output": st.column_config.TextColumn("Expected Goal", width="medium"),
                "description": st.column_config.TextColumn("Description", width="medium"),
                "tags": st.column_config.ListColumn("Tags"),
                "conversation": st.column_config.TextColumn("Conversation (JSON)", width="large"),
                "overall_criteria": st.column_config.TextColumn("Criteria", disabled=True)
            },
            num_rows="dynamic",
            key="editor_generated",
            use_container_width=True
        )
        
        # Save to Library
        if st.button("💾 Save to Library", type="primary"):
            new_cases = edited_generated.to_dict(orient="records")
            
            # Format back to real JSON from string for conversation/criteria
            clean_new_cases = []
            for case in new_cases:
                try:
                    case["conversation"] = json.loads(case["conversation"]) if isinstance(case["conversation"], str) else case["conversation"]
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
            st.session_state.generated_cases = pd.DataFrame(columns=["id", "input", "expected_output", "description", "tags", "conversation"])
            
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
