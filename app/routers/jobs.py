"""对外接口 - 测试执行（后台 Job：触发/进度/取消/续跑）"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import SessionLocal
from app.models.test_case import TestCase
from app.job_manager import get_job_manager
from app.services.history_service import HistoryService
from app.routers.cases import case_to_dict

router = APIRouter()


class JobCreate(BaseModel):
    case_ids: List[str]
    api_name: str
    execution_mode: str = "full"
    max_workers: int = 5
    report_name: Optional[str] = None


def _load_cases_by_ids(case_ids: List[str]) -> List[dict]:
    """按 id 从 PostgreSQL 加载完整用例（含多轮所有 turn），供 job_manager 执行。"""
    db = SessionLocal()
    try:
        rows = (db.query(TestCase)
                .filter(TestCase.id.in_(case_ids))
                .order_by(TestCase.id, TestCase.turn_index)
                .all())
        return [case_to_dict(r) for r in rows]
    finally:
        db.close()


@router.post("")
def create_job(req: JobCreate):
    """触发后台执行，立即返回 report_id（用于后续查询进度/取消/续跑）。"""
    if req.execution_mode not in ("full", "semantic", "assertion"):
        raise HTTPException(status_code=400, detail="execution_mode must be full/semantic/assertion")
    cases = _load_cases_by_ids(req.case_ids)
    if not cases:
        raise HTTPException(status_code=404, detail="no cases found for given case_ids")
    mgr = get_job_manager()
    report_id = mgr.run_background_job(
        cases,
        api_name=req.api_name,
        execution_mode=req.execution_mode,
        max_workers=req.max_workers,
        report_name=req.report_name,
    )
    return {"report_id": report_id, "submitted_cases": len(cases)}


@router.get("")
def list_jobs():
    """所有 job（含状态、进度），按时间倒序。"""
    service = HistoryService()
    try:
        return service.get_all(include_results=False)
    finally:
        service.db.close()


@router.get("/{report_id}")
def get_job(report_id: str):
    """单个 job 详情（含 results）。"""
    service = HistoryService()
    try:
        entry = service.get_by_id(report_id)
        if not entry:
            raise HTTPException(status_code=404, detail="report not found")
        return entry
    finally:
        service.db.close()


@router.post("/{report_id}/cancel")
def cancel_job(report_id: str):
    """取消 job。"""
    get_job_manager().cancel_job(report_id)
    return {"ok": True}


@router.post("/{report_id}/continue")
def continue_job(report_id: str, max_workers: int = 5):
    """续跑 cancelled/interrupted/failed 的 job，只执行剩余用例。"""
    result = get_job_manager().continue_job(report_id, max_workers=max_workers)
    return result