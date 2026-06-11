from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
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

    @field_validator('retrieval_context', mode='before')
    @classmethod
    def fix_retrieval_context(cls, v):
        if v is None or v == 'nan' or v == '':
            return []
        if isinstance(v, str):
            return [v] if v else []
        if isinstance(v, list):
            return v
        return []

    @field_validator('tags', mode='before')
    @classmethod
    def fix_tags(cls, v):
        if v is None or v == 'nan' or v == '':
            return []
        if isinstance(v, list):
            return v
        return []

import math

def _sanitize_value(v):
    """将 NaN/None 转为合适的默认值"""
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return v

def _sanitize_case(case):
    """清洗单条记录中的 NaN 值"""
    for key in ("id", "input", "expected_output"):
        if key in case:
            case[key] = str(_sanitize_value(case[key])) if _sanitize_value(case[key]) != "" else ""
    for key in ("retrieval_context", "tags"):
        val = case.get(key)
        if val is None or val == "nan" or (isinstance(val, float) and math.isnan(val)):
            case[key] = []
        elif isinstance(val, str):
            case[key] = [val] if val else []
    return case

def load_cases():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        cases = json.load(f)
    return [_sanitize_case(c) for c in cases]

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
