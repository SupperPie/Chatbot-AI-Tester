from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List
import json
import os
import datetime
from app.test_engine import TestEngine
from app.routers.cases import load_cases

router = APIRouter()
HISTORY_FILE = "data/history.json"
engine = TestEngine()

class RunRequest(BaseModel):
    case_ids: List[str]

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_history_entry(entry):
    history = load_history()
    history.insert(0, entry) # Prepend new entry
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4, ensure_ascii=False)

@router.post("")
async def run_tests(request: RunRequest):
    # Fetch selected cases
    all_cases = load_cases()
    selected_cases = [c for c in all_cases if c["id"] in request.case_ids]
    
    if not selected_cases:
        raise HTTPException(status_code=400, detail="No valid cases selected")

    # Run tests
    results = await engine.run_batch(selected_cases)
    
    # Calculate stats
    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    
    # Create history entry
    entry = {
        "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        "timestamp": datetime.datetime.now().isoformat(),
        "total": total_count,
        "passed": passed_count,
        "failed": total_count - passed_count,
        "results": results
    }
    
    save_history_entry(entry)
    
    return entry

@router.get("/history")
def get_history():
    return load_history()

@router.delete("/history/{entry_id}")
def delete_history(entry_id: str):
    history = load_history()
    new_history = [h for h in history if h["id"] != entry_id]
    
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(new_history, f, indent=4, ensure_ascii=False)
        
    return {"status": "success"}
