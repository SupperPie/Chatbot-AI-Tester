
import requests
import json
import uuid

def debug_stream():
    url = "https://air-assis-dev.dragonpass.com.cn/airport_assis/stream"
    
    payload = {
        "session_id": str(uuid.uuid4())[:8],
        "message": "我想走快一点，但不需要太多服务",
        "stream_mode": "MESSAGES",
        "anchor": "MAIN",
        "mobile_no": "13112748887"
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }
    
    print(f"Sending request to {url}...")
    try:
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                print(f"RAW LINE: {decoded_line}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_stream()
