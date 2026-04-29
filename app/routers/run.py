from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List
from app.test_engine import TestEngine
from app.routers.cases import load_cases

router = APIRouter()
engine = TestEngine()

class RunRequest(BaseModel):
    case_ids: List[str]


@router.post("")
async def run_tests(request: RunRequest):
    # Fetch selected cases
    all_cases = load_cases()
    selected_cases = [c for c in all_cases if c["id"] in request.case_ids]
    
    if not selected_cases:
        raise HTTPException(status_code=400, detail="No valid cases selected")

    # Run tests
    results = await engine.run_batch(selected_cases)
    
    # Save to DB
    from app.services.history_service import HistoryService
    service = HistoryService()
    history_id = service.save(results)

    return {
        "id": history_id,
        "total": len(results),
        "passed": sum(1 for r in results if r.get("passed")),
        "failed": sum(1 for r in results if not r.get("passed")),
        "results": results
    }

@router.get("/history")
def get_history():
    from app.services.history_service import HistoryService
    service = HistoryService()
    return service.get_all()

@router.delete("/history/{entry_id}")
def delete_history(entry_id: str):
    from app.services.history_service import HistoryService
    service = HistoryService()
    service.delete([entry_id])
    return {"status": "success"}
