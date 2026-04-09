import requests
import json
import uuid
import os
import time
import logging

# 获取 logger（配置在 streamlit_app.py 入口统一处理）
logger = logging.getLogger(__name__)

# Configuration File Path
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "api_config.json")

def load_api_configs():
    """Load API configurations from JSON file"""
    logger.debug(f"load_api_configs() 调用, CONFIG_FILE={CONFIG_FILE}")
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                logger.debug(f"load_api_configs() 成功加载 {len(config)} 个API配置")
                return config
        except Exception as e:
            logger.error(f"Error loading API config: {e}")
            return {}
    logger.warning(f"配置文件不存在: {CONFIG_FILE}")
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
        raw_chunks = []  # 收集完整原始响应
        bundle_list = None  # 收集 bundle_list
        ttft = 0.0
        got_first_token = False
        ai_content = None  # 保存 AI 回复内容
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: "):
                    json_str = decoded_line[6:]
                    if json_str.strip() == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(json_str)
                        raw_chunks.append(json.dumps(data, ensure_ascii=False))  # 保存原始数据
                        
                        # 提取 AI 回复内容
                        if data.get("type") == "message" and data.get("agent") == "bundle":
                            content_obj = data.get("content", {})
                            if isinstance(content_obj, dict) and content_obj.get("type") == "ai":
                                if not got_first_token:
                                    ttft = time.time() - start_time
                                    got_first_token = True
                                ai_content = content_obj.get("content")
                        
                        # 提取 bundle_list
                        if data.get("type") == "done" and data.get("agent") == "bundle":
                            data_obj = data.get("data", {})
                            if data_obj.get("bundle_list"):
                                bundle_list = data_obj.get("bundle_list")
                                
                        if data.get("type") == "token" and data.get("agent") == "main":
                             if not got_first_token:
                                 ttft = time.time() - start_time
                                 got_first_token = True
                             full_response_text += data.get("content", "")

                    except json.JSONDecodeError:
                        raw_chunks.append(f"Decode Error: {json_str}")
                        continue

        # 构建返回结果
        result_content = ai_content if ai_content else full_response_text
        if result_content:
            result_obj = {
                "result": result_content,
                "thinking": "",
                "inform_base": "",
                "raw": "\n".join(raw_chunks),
                "ttft": ttft
            }
            if bundle_list:
                result_obj["bundle_list"] = bundle_list
            return json.dumps(result_obj, ensure_ascii=False)
            
        return json.dumps({"result": "Error: No response content found.", "raw": "\n".join(raw_chunks), "ttft": 0.0}, ensure_ascii=False)

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
        
        # 保存完整原始响应
        raw_data = json.dumps(data, ensure_ascii=False, indent=2)
            
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


def get_agent_qa_response(message: str, url: str, user_id: str = None, session_id: str = None) -> str:
    """Agent Q&A API client"""
    # Generate IDs if not provided
    if user_id is None:
        user_id = str(uuid.uuid4())
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]
    
    # Payload based on user specification
    # Note: API expects 'session_id' not 'thread_id'
    payload = {
        "query": message,
        "user_id": user_id,
        "session_id": session_id,  # API expects 'session_id'
        "lob": "dc"  # Default to 'dc', can be 'dc' or 'ata'
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }

    print(f"Sending request to {url} with query: {message}")
    
    try:
        start_time = time.time()
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
                        content = data.get("content") or data.get("text") or ""
                        
                        if msg_type == "token":
                            # Token stream - concatenate content
                            if content and isinstance(content, str):
                                if not got_first_token:
                                    ttft = time.time() - start_time
                                    got_first_token = True
                                final_answer += content
                        elif msg_type == "done":
                            # Done signal - stop processing
                            break
                        elif msg_type == "reasoning":
                            if content:
                                thinking_process.append(content)
                        elif msg_type == "tools":
                            if content:
                                inform_base_process.append(f"[Tool] {content}")
                        elif msg_type == "text":
                            if content:
                                if not got_first_token:
                                    ttft = time.time() - start_time
                                    got_first_token = True
                                final_answer += content
                        else:
                            pass

                    except json.JSONDecodeError:
                        raw_chunks.append(f"Decode Error: {json_str}")
                        continue
        
        # Combine results
        thinking_str = "".join(thinking_process)
        inform_base_str = "\n".join(inform_base_process)
        raw_full_str = "\n".join(raw_chunks)
        
        # Fallback if empty
        if not final_answer:
            if thinking_str:
                final_answer = "Refers to thinking process for details."
            elif raw_chunks:
                final_answer = "Raw data captured (parsing failed). See Raw Data."
            else:
                final_answer = "Error: No response content found."

        return json.dumps({
            "result": final_answer, 
            "thinking": thinking_str,
            "inform_base": inform_base_str,
            "raw": raw_full_str,
            "ttft": ttft
        }, ensure_ascii=False)

    except requests.exceptions.Timeout:
        return "Error: Agent Q&A API Request Timed Out (600s)"
    except Exception as e:
        print(f"Error calling Agent Q&A API: {e}")
        return f"Error: {e}"


def get_hotel_response(message: str, url: str, user_id: str = None, session_id: str = None) -> str:
    """Hotel streaming API client
    
    Uses the health check payload format with 'ex' field containing semantic_info.
    Response format: type=done, agent=hotel, content contains AI response, data contains hotel_list.
    """
    if user_id is None:
        user_id = str(uuid.uuid4())
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]
    
    # Health check payload with semantic_info for Hotel API
    payload = {
        "message": message,
        "thread_id": session_id,
        "user_id": user_id,
        "ex": {
            "max_results": 5,
            "use_ai_description": False,
            "use_ai_commentary": True,
            "previous_params": {},
            "semantic_info": {
                "lang": "zh-CN",
                "userMessage": message,
                "destination": "广州",
                "cityCode": "10112",
                "hotelName": "",
                "checkInDate": "2026-04-02",
                "checkOutDate": "2026-04-03",
                "adultNum": 1,
                "childNum": 0,
                "childAgeList": [],
                "roomNum": 1,
                "hotelBrandName": "",
                "hotelFacilityList": [],
                "hotelRoomeFacilityList": [],
                "hotelStarCode": "",
                "hotelTypeCode": "",
                "sortList": []
            },
            "ambiguous_fields": {},
            "missing_fields": {}
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "accept": "application/json"
    }

    print(f"[Hotel] Sending request to {url} with message: {message}")
    
    try:
        start_time = time.time()
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=600)
        
        if not response.ok:
            print(f"[Hotel] API Error {response.status_code}: {response.text}")
            return f"❌ SERVER DETAIL ({response.status_code}): {response.text}"
            
        final_answer = ""
        raw_chunks = []
        inform_base = ""
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
                        
                        msg_type = data.get("type")
                        agent = data.get("agent")
                        content = data.get("content", "")
                        
                        # Handle token streaming (type=token, agent=main)
                        if msg_type == "token" and agent == "main":
                            if content:
                                if not got_first_token:
                                    ttft = time.time() - start_time
                                    got_first_token = True
                                final_answer += content
                        
                        # Handle done event (type=done, agent=hotel)
                        elif msg_type == "done" and agent == "hotel":
                            if not got_first_token:
                                ttft = time.time() - start_time
                                got_first_token = True
                            if content:
                                final_answer = content
                            # Extract hotel_list metadata
                            hotel_data = data.get("data", {})
                            if hotel_data.get("hotel_list"):
                                hotel_count = len(hotel_data["hotel_list"])
                                inform_base = f"返回 {hotel_count} 家酒店"
                            # Extract metadata
                            metadata = data.get("metadata", {})
                            if metadata:
                                semantic = metadata.get("semantic_info", {})
                                if semantic:
                                    inform_base += f"\n目的地: {semantic.get('destination', 'N/A')}"
                                    inform_base += f"\n入住: {semantic.get('checkInDate', 'N/A')} - {semantic.get('checkOutDate', 'N/A')}"
                                
                    except json.JSONDecodeError:
                        raw_chunks.append(f"Decode Error: {json_str}")
                        continue
                        
        if not final_answer:
            final_answer = "Error: No response content found from Hotel API."
            
        return json.dumps({
            "result": final_answer, 
            "thinking": "",
            "inform_base": inform_base,
            "raw": "\n".join(raw_chunks),
            "ttft": ttft
        }, ensure_ascii=False)

    except requests.exceptions.Timeout:
        return "Error: Hotel API Request Timed Out (600s)"
    except Exception as e:
        print(f"[Hotel] Error: {e}")
        return f"Error: {str(e)}"


def get_dify_workflow_response(message: str, url: str, token: str = None, user_id: str = None, session_id: str = None) -> str:
    """Dify Workflow API client (extracts answer from workflow_finished event).
    
    This is for Dify APIs that return the final answer in the workflow_finished event's
    data.outputs.answer field, rather than streaming message tokens.
    
    Token format: "x-app-code|x-app-passport" (separated by |)
    """
    if user_id is None:
        user_id = str(uuid.uuid4())
    
    # Parse token: "x-app-code|x-app-passport"
    app_code, app_passport = "", ""
    if token and "|" in token:
        parts = token.split("|", 1)
        app_code, app_passport = parts[0], parts[1]
    
    # Validate conversation_id (must be UUID format or empty)
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
        "files": [],
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "x-app-code": app_code,
        "x-app-passport": app_passport,
    }

    print(f"[DifyWorkflow] Sending request to {url} with message: {message}")

    try:
        start_time = time.time()
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=600)

        if not response.ok:
            print(f"[DifyWorkflow] API Error {response.status_code}: {response.text}")
            return f"❌ SERVER DETAIL ({response.status_code}): {response.text}"

        final_answer = ""
        raw_chunks = []
        ttft = 0.0
        got_first_token = False

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

                        if event == "workflow_finished":
                            # Extract answer from outputs
                            if not got_first_token:
                                ttft = time.time() - start_time
                                got_first_token = True
                            outputs = data.get("data", {}).get("outputs", {})
                            final_answer = outputs.get("answer", "")

                        elif event == "error":
                            err_msg = data.get("message", "Unknown DifyWorkflow error")
                            return f"Error: DifyWorkflow returned error event: {err_msg}"

                    except json.JSONDecodeError:
                        raw_chunks.append(f"Decode Error: {json_str}")
                        continue

        if not final_answer:
            final_answer = "Error: No answer content found in workflow_finished event."

        return json.dumps(
            {
                "result": final_answer,
                "thinking": "",
                "inform_base": "",
                "raw": "\n".join(raw_chunks),
                "ttft": ttft,
            },
            ensure_ascii=False,
        )

    except requests.exceptions.Timeout:
        return "Error: DifyWorkflow API Request Timed Out (600s)"
    except Exception as e:
        print(f"[DifyWorkflow] Error: {e}")
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
    elif api_type == "agent_qa":
        return get_agent_qa_response(message, url=url, user_id=user_id, session_id=session_id)
    elif api_type == "hotel":
        return get_hotel_response(message, url=url, user_id=user_id, session_id=session_id)
    elif api_type == "dify_workflow":
        token = config.get("token", "")
        return get_dify_workflow_response(message, url=url, token=token, user_id=user_id, session_id=session_id)
    else:
        # Default to Bundle type structure
        return get_bundle_response(message, url=url, user_id=user_id, session_id=session_id)


def get_available_apis():
    """Return list of available API names"""
    logger.debug("get_available_apis() 调用")
    result = list(load_api_configs().keys())
    logger.debug(f"get_available_apis() 返回: {result}")
    return result


if __name__ == "__main__":
    pass
    # verification
    # print("Testing Bundle API...")
    # resp = get_chat_response("book a car", api_name="Bundle API")
    # print(f"Bundle Response: {resp}")
    

