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


def get_airport_assis_response(message: str, url: str, user_id: str = None, session_id: str = None) -> str:
    """Airport Assistant API client with session support"""
    # Generate IDs if not provided
    if user_id is None:
        user_id = str(uuid.uuid4())
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]
    
    payload = {
        "session_id": session_id,
        "query": message,
        "stream_mode": "MESSAGE",
        "step": "",
        "phone": ""
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    print(f"Sending request to {url} with query: {message}")
    
    try:
        response = requests.post(url, json=payload, headers=headers, stream=True)
        
        if not response.ok:
            print(f"API Error {response.status_code}: {response.text}")
            return f"❌ SERVER DETAIL ({response.status_code}): {response.text}"
            
        response.raise_for_status()
        
        final_answer = ""
        thinking_process = []
        raw_chunks = [] # For debugging
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: "):
                    json_str = decoded_line[6:]
                    if json_str.strip() == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(json_str)
                        
                        # Capture EVERYTHING for debug
                        raw_chunks.append(json.dumps(data, ensure_ascii=False))
                        
                        # Handle string data (simple message stream)
                        if isinstance(data, str):
                            final_answer += data
                            continue

                        # Ensure data is a dictionary
                        if not isinstance(data, dict):
                            continue
                        
                        # Extract Agent Data
                        agent_name = data.get("agent", "unknown_agent")
                        
                        # 1. Customer Service Agent
                        if agent_name == "customer_service_agent":
                            reply = data.get("reply", "")
                            if reply:
                                thinking_process.append(f"**Customer Service Agent:** {reply}")
                                
                        # 2. Membership Guide Agent
                        elif agent_name == "membership_card_guide_agent":
                            reason = data.get("reason", "")
                            card = data.get("membership_card", "")
                            if reason:
                                thinking_process.append(f"**Membership Guide Agent ({card}):**\n{reason}")
                                
                        # 3. Supervisor Agent
                        elif agent_name == "supervisor_agent":
                            answer = data.get("answer", "")
                            if answer:
                                final_answer = answer # Overwrite or append? Usually overwrite in this logic
                            
                            reason = data.get("reason", "") 
                            if reason: 
                                thinking_process.append(f"**Supervisor Agent:** {reason}")
                        
                        # 4. Fallback for other agents/fields
                        else:
                             # Try to find any common text fields
                             content = data.get("content") or data.get("reply") or data.get("reason") or data.get("answer")
                             if content:
                                 thinking_process.append(f"**{agent_name}:** {content}")

                    except json.JSONDecodeError:
                        raw_chunks.append(f"Decode Error: {json_str}")
                        continue
        
        # Determine Final Result
        if not final_answer:
            # If no explicit answer found, check if we can deduce from thinking or use raw chunks
            if thinking_process:
                final_answer = "Refers to thinking process for details."
            elif raw_chunks:
                # If we have raw chunks but failed to parse structure
                final_answer = "Raw data captured (parsing failed). See Thinking Process."
            else:
                 final_answer = "Error: No response content found."

        # Combine thinking with RAW log for user visibility (as requested)
        full_debug_log = "\n\n".join(thinking_process)
        # full_debug_log += "\n\n--- RAW API RESPONSE STREAM ---\n" + "\n".join(raw_chunks)
        
        # Return as a structured JSON string 
        return json.dumps({
            "result": final_answer, 
            "thinking": full_debug_log
        }, ensure_ascii=False)

    except Exception as e:
        print(f"Error calling Airport Assistant API: {e}")
        return f"Error: {e}"


def get_skills_response(message: str, url: str, user_id: str = None, session_id: str = None) -> str:
    """Skills API client"""
    # Generate IDs if not provided
    if user_id is None:
        user_id = str(uuid.uuid4())
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]
    
    payload = {
        "session_id": session_id,
        "query": message,
        "stream_mode": "MESSAGE",
        "step": "",
        "phone": ""
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    print(f"Sending request to {url} with query: {message}")
    
    try:
        # TIMEOUT ADDED: 600s to prevent hanging
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=600)
        
        if not response.ok:
            print(f"API Error {response.status_code}: {response.text}")
            return f"❌ SERVER DETAIL ({response.status_code}): {response.text}"
            
        response.raise_for_status()
        
        final_answer = ""
        thinking_process = []
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

                        # Parse based on event type
                        event_type = data.get("event")
                        content = data.get("content", "")
                        
                        if event_type == "reasoning":
                            # Accumulate thinking
                            if content:
                                thinking_process.append(content)
                        elif event_type == "text":
                            # Accumulate final answer
                            if content:
                                final_answer += content
                        else:
                             # Fallback or other events
                             pass

                    except json.JSONDecodeError:
                        raw_chunks.append(f"Decode Error: {json_str}")
                        continue
        
        # Combine thinking
        thinking_str = "".join(thinking_process) # reasoning content is likely token fragments
        
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
        # full_debug_log += "\n\n--- RAW API RESPONSE STREAM ---\n" + "\n".join(raw_chunks)
        
        return json.dumps({
            "result": final_answer, 
            "thinking": full_debug_log
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
    
    if api_type == "airport":
        return get_airport_assis_response(message, url=url, user_id=user_id, session_id=session_id)
    elif api_type == "skills":
        return get_skills_response(message, url=url, user_id=user_id, session_id=session_id)
    else:
        # Default to Bundle type structure
        return get_bundle_response(message, url=url, user_id=user_id, session_id=session_id)


def get_available_apis():
    """Return list of available API names"""
    return list(load_api_configs().keys())


if __name__ == "__main__":
    # verification
    # print("Testing Bundle API...")
    # resp = get_chat_response("book a car", api_name="Bundle API")
    # print(f"Bundle Response: {resp}")
    
    print("\nTesting Airport Assistant API...")
    resp2 = get_chat_response("我想走快一点，但不需要太多服务", api_name="Airport Assistant")
    print(f"Airport Response: {resp2}")
