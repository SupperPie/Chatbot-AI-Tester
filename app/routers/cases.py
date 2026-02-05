from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import uuid

router = APIRouter()
DATA_FILE = "data/test_cases.json"

class TestCase(BaseModel):
    id: Optional[str] = None
    input: str
    expected_output: str
    retrieval_context: List[str] = []
    tags: List[str] = []

def load_cases():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_cases(cases):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=4, ensure_ascii=False)

@router.get("", response_model=List[TestCase])
def get_cases():
    return load_cases()

@router.post("", response_model=TestCase)
def create_or_update_case(case: TestCase):
    cases = load_cases()
    
    if case.id:
        # Update existing
        for i, c in enumerate(cases):
            if c["id"] == case.id:
                cases[i] = case.dict()
                save_cases(cases)
                return case
        raise HTTPException(status_code=404, detail="Case not found")
    else:
        # Create new
        case.id = str(uuid.uuid4())
        cases.append(case.dict())
        save_cases(cases)
        return case

@router.delete("/{case_id}")
def delete_case(case_id: str):
    cases = load_cases()
    initial_len = len(cases)
    cases = [c for c in cases if c["id"] != case_id]
    
    if len(cases) == initial_len:
        raise HTTPException(status_code=404, detail="Case not found")
        
    save_cases(cases)
    return {"status": "success", "message": "Case deleted"}
