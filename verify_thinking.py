
import sys
import os
import json

# Ensure we can import modules from root
sys.path.append(os.getcwd())
# Fix for Windows console encoding
sys.stdout.reconfigure(encoding='utf-8')

from chat_client import get_chat_response
from app.test_engine import TestEngine

def verify_chat_client():
    print("Testing Chat Client...")
    try:
        raw_resp = get_chat_response("我想走快一点，但不需要太多服务", api_name="Airport Assistant")
        print(f"Raw Response: {raw_resp}")
        
        data = json.loads(raw_resp)
        if "thinking" in data and "result" in data:
            print("✅ Chat Client returned correct JSON structure.")
            print(f"Thinking Length: {len(data['thinking'])}")
            print(f"Result Length: {len(data['result'])}")
        else:
            print("❌ Chat Client returned JSON but missing keys.")
    except Exception as e:
        print(f"❌ Chat Client failed: {e}")

def verify_test_engine():
    print("\nTesting TestEngine parsing...")
    engine = TestEngine()
    
    # Mock a test case
    case = {
        "id": "TEST001",
        "input": "我想走快一点，但不需要太多服务",
        "expected_output": "N/A",
        "retrieval_context": [],
        "type": "single_turn"
    }
    
    try:
        result = engine.run_case(case, api_name="Airport Assistant")
        
        if result.get("thinking"):
            print("✅ TestEngine correctly parsed 'thinking' field.")
            print(f"Thinking content preview: {result['thinking'][:50]}...")
        else:
            print("❌ TestEngine failed to parse 'thinking' field.")
            print(f"Actual Output: {result.get('actual_output')}")
            
    except Exception as e:
        print(f"❌ TestEngine run failed: {e}")

if __name__ == "__main__":
    verify_chat_client()
    # verify_test_engine()
