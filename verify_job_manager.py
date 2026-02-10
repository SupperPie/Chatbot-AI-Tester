
import os
import json
import time
from app.job_manager import get_job_manager

def verify_job_execution():
    print("Testing Job Manager...")
    mgr = get_job_manager()
    
    # Mock cases
    cases = [
        {"id": "TEST_MOCK_001", "input": "Hello", "expected_output": "Hi"},
        {"id": "TEST_MOCK_002", "input": "Bye", "expected_output": "Goodbye"}
    ]
    
    # Run job
    job_id = mgr.run_background_job(cases, api_name="Bundle API")
    print(f"Job started with ID: {job_id}")
    
    # Check history immediately
    history_file = "data/history.json"
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            hist = json.load(f)
            job_entry = next((h for h in hist if h["id"] == job_id), None)
            
            if job_entry:
                print(f"[OK] Job entry found in history. Status: {job_entry.get('status')}")
            else:
                print("[ERROR] Job entry NOT found in history immediately.")
    else:
        print("[ERROR] History file not found.")

    # Wait a bit (simulating run)
    print("Waiting for job to process...")
    time.sleep(5) 
    
    # Check update
    with open(history_file, "r", encoding="utf-8") as f:
        hist = json.load(f)
        job_entry = next((h for h in hist if h["id"] == job_id), None)
        if job_entry:
            print(f"Job Status after 5s: {job_entry.get('status')}")
            print(f"Passed: {job_entry.get('passed')}")
            print(f"Results count: {len(job_entry.get('results', []))}")
            if job_entry.get("status") in ["running", "completed", "failed"]:
                 print("[OK] Job status is valid.")
            else:
                 print(f"[ERROR] Unexpected job status: {job_entry.get('status')}")

if __name__ == "__main__":
    verify_job_execution()
