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
        st.session_state.generated_cases = pd.DataFrame(columns=["id", "input", "expected_output", "tags"])
    
    # Two-column layout for inputs
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📝 Test Requirements")
        requirements = st.text_area(
            "Describe what test cases you want to generate",
            height=200,
            placeholder="Example:\n- Generate 5 test cases about user login\n- Include edge cases for invalid passwords\n- Test both Chinese and English inputs",
            key="tester_requirements"
        )
    
    with col2:
        st.subheader("📚 Knowledge Base")
        knowledge_base = st.text_area(
            "Paste your knowledge, documentation, or facts",
            height=200,
            placeholder="Paste relevant information here:\n\nExample:\n- Users can login with email or phone number\n- Password must be 8-20 characters\n- System supports Chinese and English",
            key="tester_knowledge"
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
                    prompt = f"""You are a test case generator. Generate test cases based on the following requirements and knowledge.

Requirements:
{requirements}

Knowledge Base:
{knowledge_base if knowledge_base.strip() else "No additional knowledge provided."}

Generate test cases in the following JSON format. Each test case should have:
- input: The question or input to test
- expected_output: The expected answer or response
- tags: A list of relevant tags (e.g., ["login", "validation"])

Return ONLY a JSON array of test cases, no other text. Example:
[
  {{"input": "How do I login?", "expected_output": "You can login with email or phone number", "tags": ["login", "basic"]}},
  {{"input": "What is the password requirement?", "expected_output": "Password must be 8-20 characters", "tags": ["login", "password"]}}
]
"""
                    try:
                        from openai import OpenAI
                        
                        api_key = os.getenv("OPENAI_API_KEY")
                        base_url = os.getenv("OPENAI_BASE_URL")
                        model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
                        
                        if not api_key:
                            st.warning("⚠️ 缺省 OPENAI_API_KEY 环境变量，本次自动生成可能会失败。")
                        
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
                            generated_df = pd.DataFrame(cases_json)
                            # Add IDs
                            generated_df["id"] = [f"NEW{str(i+1).zfill(3)}" for i in range(len(generated_df))]
                            # Ensure required columns
                            for col in ["input", "expected_output", "tags"]:
                                if col not in generated_df.columns:
                                    generated_df[col] = "" if col != "tags" else [[] for _ in range(len(generated_df))]
                            
                            st.session_state.generated_cases = generated_df
                            st.success(f"✅ Generated {len(generated_df)} test cases!")
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
                "input": st.column_config.TextColumn("Input Question", width="large"),
                "expected_output": st.column_config.TextColumn("Expected Output", width="large"),
                "tags": st.column_config.ListColumn("Tags"),
            },
            num_rows="dynamic",
            key="editor_generated",
            use_container_width=True
        )
        
        # Save to Library
        if st.button("💾 Save to Library", type="primary"):
            new_cases = edited_generated.to_dict(orient="records")
            
            # Load existing
            existing_df = load_data()
            if "Select" in existing_df.columns:
                 existing_df = existing_df.drop(columns=["Select"])
                 
            new_df = pd.DataFrame(new_cases)
            if "id" in new_df.columns:
                del new_df["id"] # Let save_data regenerate IDs or handle it
                
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            
            # Save
            final_df = save_data(combined_df)
            
            # Clear generated cases
            st.session_state.generated_cases = pd.DataFrame(columns=["id", "input", "expected_output", "tags"])
            
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
