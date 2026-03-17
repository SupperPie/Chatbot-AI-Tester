import requests
import json
import uuid
import os
import time

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
        start_time = time.time()
        response = requests.post(url, json=payload, headers=headers, stream=True)
        response.raise_for_status()
        
        full_response_text = ""
        ttft = 0.0
        got_first_token = False
        
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
                                ttft = time.time() - start_time
                                return json.dumps({
                                    "result": content_obj.get("content"),
                                    "thinking": "",
                                    "inform_base": "",
                                    "raw": "",
                                    "ttft": ttft
                                }, ensure_ascii=False)
                                
                        if data.get("type") == "token" and data.get("agent") == "main":
                             if not got_first_token:
                                 ttft = time.time() - start_time
                                 got_first_token = True
                             full_response_text += data.get("content", "")

                    except json.JSONDecodeError:
                        continue

        if full_response_text:
            return json.dumps({
                "result": full_response_text,
                "thinking": "",
                "inform_base": "",
                "raw": "",
                "ttft": ttft
            }, ensure_ascii=False)
            
        return json.dumps({"result": "Error: No response content found.", "ttft": 0.0}, ensure_ascii=False)

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
        start_time = time.time()
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
        
        ttft = 0.0
        got_first_token = False
        
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
                                    if not got_first_token:
                                        ttft = time.time() - start_time
                                        got_first_token = True
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
            "raw": raw_full_str,
            "ttft": ttft
        }, ensure_ascii=False)

    except Exception as e:
        print(f"Error calling Skills API: {e}")
        return f"Error: {e}"


def get_flight_response(message: str, url: str, user_id: str = None, session_id: str = None) -> str:
    """Flight API client"""
    # Generate IDs if not provided
    if user_id is None:
        user_id = "12345" # Using default as per user request example, or uuid
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]
    
    payload = {
        "query": message,
        "user_id": user_id,
        "thread_id": session_id,
        "line_of_business": "dev_lob",
        "additionalProp1": {}
    }
    
    headers = {
        "Content-Type": "application/json",
        "accept": "application/json"
    }

    print(f"Sending request to {url} with message: {message}")
    
    try:
        start_time = time.time()
        response = requests.post(url, json=payload, headers=headers, timeout=600)
        
        if not response.ok:
            print(f"API Error {response.status_code}: {response.text}")
            return f"❌ SERVER DETAIL ({response.status_code}): {response.text}"
            
        data = response.json()
        ttft = time.time() - start_time # No stream, so ttft equals latency
        
        # Extract according to user requirements
        actual_output = data.get("output_response", "")
        raw_data = ""
        
        # Put result_intent_detection into raw_data
        intent_data = data.get("result_intent_detection")
        if intent_data:
            raw_data = json.dumps(intent_data, ensure_ascii=False, indent=2)
            
        return json.dumps({
            "result": actual_output, 
            "thinking": "", 
            "inform_base": "",
            "raw": raw_data,
            "ttft": ttft
        }, ensure_ascii=False)

    except requests.exceptions.Timeout:
        return "Error: API Request Timed Out (600s)"
    except Exception as e:
        print(f"Error calling Flight API: {e}")
        return f"Error: {str(e)}"

def get_limo_response(message: str, url: str, user_id: str = None, session_id: str = None) -> str:
    """Limo streaming API client"""
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
                "meta.semantic_info.flight_no",
                "meta.semantic_info.flight_date",
                "meta.semantic_info.service_type",
                "meta.semantic_info.address_keywords",
                "meta.semantic_info.service_time",
                "meta.semantic_info.arrival_time",
                "meta.semantic_info.airport_code",
                "meta.semantic_info.adult",
                "meta.semantic_info.child",
                "meta.semantic_info.luggage",
                "data.flight_info",
                "data.car_info",
                "data.address_info"
            ]
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "accept": "application/json"
    }

    print(f"Sending request to {url} with message: {message}")
    
    try:
        start_time = time.time()
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=600)
        
        if not response.ok:
            print(f"API Error {response.status_code}: {response.text}")
            return f"❌ SERVER DETAIL ({response.status_code}): {response.text}"
            
        final_answer = ""
        raw_chunks = []
        ttft = 0.0
        got_first_token = False
        
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
                        
                        if data.get("type") == "token" and data.get("agent") == "main":
                            content = data.get("content", "")
                            if content:
                                if not got_first_token:
                                    ttft = time.time() - start_time
                                    got_first_token = True
                                final_answer += content
                                
                    except json.JSONDecodeError:
                        raw_chunks.append(f"Decode Error: {json_str}")
                        continue
                        
        if not final_answer:
            final_answer = "Error: No main token content found."
            
        return json.dumps({
            "result": final_answer, 
            "thinking": "",
            "inform_base": "",
            "raw": "\n".join(raw_chunks),
            "ttft": ttft
        }, ensure_ascii=False)

    except requests.exceptions.Timeout:
        return "Error: API Request Timed Out (600s)"
    except Exception as e:
        print(f"Error calling Limo API: {e}")
        return f"Error: {str(e)}"

def get_dify_response(message: str, url: str, token: str = None, user_id: str = None, session_id: str = None) -> str:
    """Dify /v1/chat-messages streaming API client.
    
    Expects config with:
      url  : base_url up to /v1/chat-messages (e.g. http://192.168.25.247/v1/chat-messages)
      token: Bearer app token (e.g. app-xxxxx)
    """
    if user_id is None:
        user_id = str(uuid.uuid4())
    # Dify requires conversation_id to be a valid UUID (36-char) or empty string.
    # Our test engine passes 8-char truncated IDs which Dify rejects with a 400 error.
    # Validate and fall back to "" (Dify will create a new conversation).
    import re as _re
    _uuid_pattern = _re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', _re.IGNORECASE
    )
    conversation_id = session_id if session_id and _uuid_pattern.match(session_id) else ""

    payload = {
        "inputs": {},
        "query": message,
        "response_mode": "streaming",
        "conversation_id": conversation_id,
        "user": user_id,
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Authorization": f"Bearer {token}" if token else "",
    }

    print(f"[Dify] Sending request to {url} with message: {message}")

    try:
        start_time = time.time()
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=600)

        if not response.ok:
            print(f"[Dify] API Error {response.status_code}: {response.text}")
            return f"❌ SERVER DETAIL ({response.status_code}): {response.text}"

        final_answer = ""
        raw_chunks = []
        ttft = 0.0
        got_first_token = False
        metadata = {}

        for line in response.iter_lines():
            if line:
                decoded_line = line.decode("utf-8")
                if decoded_line.startswith("data: "):
                    json_str = decoded_line[6:]
                    if json_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(json_str)
                        raw_chunks.append(json.dumps(data, ensure_ascii=False))

                        event = data.get("event", "")

                        if event == "message":
                            # Incremental answer token
                            chunk = data.get("answer", "")
                            if chunk:
                                if not got_first_token:
                                    ttft = time.time() - start_time
                                    got_first_token = True
                                final_answer += chunk

                        elif event == "message_end":
                            # Dify returns total usage and conversation_id here
                            metadata = {
                                "conversation_id": data.get("conversation_id", ""),
                                "usage": data.get("metadata", {}).get("usage", {}),
                            }

                        elif event == "error":
                            err_msg = data.get("message", "Unknown Dify error")
                            return f"Error: Dify returned error event: {err_msg}"

                    except json.JSONDecodeError:
                        raw_chunks.append(f"Decode Error: {json_str}")
                        continue

        if not final_answer:
            final_answer = "Error: No answer content found in Dify response."

        return json.dumps(
            {
                "result": final_answer,
                "thinking": "",
                "inform_base": json.dumps(metadata, ensure_ascii=False) if metadata else "",
                "raw": "\n".join(raw_chunks),
                "ttft": ttft,
            },
            ensure_ascii=False,
        )

    except requests.exceptions.Timeout:
        return "Error: Dify API Request Timed Out (600s)"
    except Exception as e:
        print(f"[Dify] Error: {e}")
        return f"Error: {str(e)}"


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
    elif api_type == "flight":
        return get_flight_response(message, url=url, user_id=user_id, session_id=session_id)
    elif api_type == "limo":
        return get_limo_response(message, url=url, user_id=user_id, session_id=session_id)
    elif api_type == "dify":
        token = config.get("token", "")
        return get_dify_response(message, url=url, token=token, user_id=user_id, session_id=session_id)
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
    

