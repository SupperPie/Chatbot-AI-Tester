import requests
import json
import uuid
import os

# Configuration File Path
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "api_config.json")

def load_api_configs():
    """Load API configurations from JSON file"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading API config: {e}")
            return {}
    return {}

def get_bundle_response(message: str, url: str, user_id: str = None, session_id: str = None) -> str:
    """Bundle API client with session support"""
    # Generate IDs if not provided
    if user_id is None:
        user_id = str(uuid.uuid4())
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]
    
    payload = {
        "message": message,
        "thread_id": session_id,
        "user_id": user_id,
        "config": {
            "struc_properties_filter": [
                "meta.semantic_info.intent",
                "data.bundle_list"
            ]
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }

    print(f"Sending request to {url} with message: {message}")
    
    try:
        response = requests.post(url, json=payload, headers=headers, stream=True)
        response.raise_for_status()
        
        full_response_text = ""
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: "):
                    json_str = decoded_line[6:]
                    if json_str.strip() == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(json_str)
                        
                        if data.get("type") == "message" and data.get("agent") == "bundle":
                            content_obj = data.get("content", {})
                            if isinstance(content_obj, dict) and content_obj.get("type") == "ai":
                                return content_obj.get("content")
                                
                        if data.get("type") == "token" and data.get("agent") == "main":
                             full_response_text += data.get("content", "")

                    except json.JSONDecodeError:
                        continue

        if full_response_text:
            return full_response_text
            
        return "Error: No response content found."

    except Exception as e:
        print(f"Error calling Bundle API: {e}")
        return f"Error: {e}"





def get_skills_response(message: str, url: str, user_id: str = None, session_id: str = None) -> str:
    """Skills API client"""
    # Generate IDs if not provided
    if user_id is None:
        user_id = str(uuid.uuid4())
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]
    
    
    # Updated payload based on user request (2026-02-09)
    payload = {
        "session_id": session_id,
        "message": message,  # Renamed from 'query'
        "stream_mode": "MESSAGES", # Changed from 'MESSAGE'
        "anchor": "", # Renamed from 'step'
        "mobile_no": "13112748887" # Renamed from 'phone' and added default
    }
    
    headers = {
        "Content-Type": "application/json",
        "accept": "application/json"
    }

    print(f"Sending request to {url} with message: {message}")
    
    try:
        # TIMEOUT ADDED: 600s to prevent hanging
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=600)
        
        if not response.ok:
            print(f"API Error {response.status_code}: {response.text}")
            return f"❌ SERVER DETAIL ({response.status_code}): {response.text}"
            
        response.raise_for_status()
        
        final_answer = ""
        thinking_process = []
        inform_base_process = []
        raw_chunks = []
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: "):
                    json_str = decoded_line[6:]
                    if json_str.strip() == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(json_str)
                        raw_chunks.append(json.dumps(data, ensure_ascii=False))

                        # Parse based on message type
                        msg_type = data.get("type")
                        # Try to find content in common fields (text/content)
                        content = data.get("text") or data.get("content") or ""
                        
                        if msg_type == "reasoning":
                            # Accumulate thinking
                            if content:
                                thinking_process.append(content)
                        elif msg_type == "tools":
                             # Handle tools event for inform base
                             # User mentioned: "type":"tools","event":"load_skills"
                             # You might want to capture the whole data or specific fields
                             if content:
                                 inform_base_process.append(f"[Tool] {content}")
                             else:
                                 # If content is empty or structure is different
                                 # Dump the whole data for tools
                                 inform_base_process.append(json.dumps(data, ensure_ascii=False))

                        elif msg_type == "text":
                            if data.get("agent") == "tools":
                                # Tool output goes to INFORM BASE
                                if content:
                                    inform_base_process.append(content)
                            else:
                                # Regular text goes to FINAL ANSWER
                                if content:
                                    final_answer += content
                        else:
                             # Fallback or other events
                             pass

                    except json.JSONDecodeError:
                        raw_chunks.append(f"Decode Error: {json_str}")
                        continue
        
        # Combine thinking
        thinking_str = "".join(thinking_process)
        inform_base_str = "\n".join(inform_base_process)
        raw_full_str = "\n".join(raw_chunks)
        
        # Fallback if empty
        if not final_answer:
            if thinking_str:
                final_answer = "Refers to thinking process for details."
            elif raw_chunks:
                final_answer = "Raw data captured (parsing failed). See Thinking Process."
            else:
                 final_answer = "Error: No response content found."

        # Add raw chunks to thinking for debug
        full_debug_log = thinking_str
        
        return json.dumps({
            "result": final_answer, 
            "thinking": full_debug_log,
            "inform_base": inform_base_str,
            "raw": raw_full_str
        }, ensure_ascii=False)

    except Exception as e:
        print(f"Error calling Skills API: {e}")
        return f"Error: {e}"


def get_chat_response(message: str, api_name: str = "Bundle API", user_id: str = None, session_id: str = None) -> str:
    """Unified API call function - selects the appropriate API based on api_name"""
    
    configs = load_api_configs()
    config = configs.get(api_name)
    
    if not config:
        return f"Error: API Configuration '{api_name}' not found."
    
    url = config.get("url")
    if not url:
        return f"Error: No URL configured for '{api_name}'."
        
    api_type = config.get("type", "bundle") # Default to bundle type if not specified
    
    if api_type == "skills":
        return get_skills_response(message, url=url, user_id=user_id, session_id=session_id)
    else:
        # Default to Bundle type structure
        return get_bundle_response(message, url=url, user_id=user_id, session_id=session_id)


def get_available_apis():
    """Return list of available API names"""
    return list(load_api_configs().keys())


if __name__ == "__main__":
    pass
    # verification
    # print("Testing Bundle API...")
    # resp = get_chat_response("book a car", api_name="Bundle API")
    # print(f"Bundle Response: {resp}")
    

