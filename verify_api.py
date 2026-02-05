
import subprocess
import time
import requests
import sys

def verify():
    # Wait for server to start
    print("Waiting for server...")
    time.sleep(3)
    
    base_url = "http://localhost:8000"
    
    try:
        # Check Health / Static file
        print("Checking frontend access...")
        res = requests.get(f"{base_url}/")
        if res.status_code == 200:
            print("[SUCCESS] Frontend accessible")
        else:
             print(f"[FAIL] Frontend returned {res.status_code}")

        # Check API: Get Cases
        print("\nChecking API: Get Cases...")
        res = requests.get(f"{base_url}/api/cases")
        if res.status_code == 200:
            count = len(res.json())
            print(f"[SUCCESS] Found {count} test cases")
        else:
            print(f"[FAIL] API returned {res.status_code}: {res.text}")

        # Check API: Get History
        print("\nChecking API: Get History...")
        res = requests.get(f"{base_url}/api/run/history")
        if res.status_code == 200:
            print("[SUCCESS] History endpoint works")
        else:
            print(f"[FAIL] API returned {res.status_code}: {res.text}")
            
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")

if __name__ == "__main__":
    verify()
