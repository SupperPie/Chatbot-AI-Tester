"""对外接口 - 测试用例管理（PostgreSQL）

对外契约字段与 app.models.TestCase 对齐：
id, turn_index, type, input, input_cn, expected_output, expected_output_cn,
retrieval_context, description, validation, overall_criteria,
category_id, tags, assertions, priority, module
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.test_case_service import TestCaseService

router = APIRouter()


def case_to_dict(c) -> dict:
    """ORM 对象转对外 dict。"""
    return {
        "id": c.id,
        "turn_index": c.turn_index,
        "type": c.type,
        "input": c.input,
        "input_cn": c.input_cn,
        "expected_output": c.expected_output,
        "expected_output_cn": c.expected_output_cn,
        "retrieval_context": c.retrieval_context,
        "description": c.description,
        "validation": c.validation,
        "overall_criteria": c.overall_criteria,
        "category_id": c.category_id,
        "tags": c.tags or [],
        "assertions": c.assertions or [],
        "priority": c.priority,
        "module": c.module,
    }


class TestCaseIn(BaseModel):
    id: Optional[str] = None
    turn_index: int = 1
    type: str = "single"
    input: Optional[str] = None
    input_cn: Optional[str] = None
    expected_output: Optional[str] = None
    expected_output_cn: Optional[str] = None
    retrieval_context: Optional[str] = None
    description: Optional[str] = None
    validation: Optional[str] = None
    overall_criteria: Optional[str] = None
    category_id: Optional[str] = "root"
    tags: List[str] = []
    assertions: List[dict] = []
    priority: Optional[str] = None
    module: Optional[str] = None


class ImportRequest(BaseModel):
    cases: List[TestCaseIn]


class DeleteRequest(BaseModel):
    ids: List[str]


class BulkUpdateRequest(BaseModel):
    ids: List[str]
    category_id: Optional[str] = None
    priority: Optional[str] = None
    module: Optional[str] = None


@router.get("")
def list_cases(category_id: Optional[str] = None, limit: int = 200, offset: int = 0):
    """用例列表，可按 category_id 筛选。"""
    service = TestCaseService()
    try:
        rows = service.get_by_category(category_id) if category_id else service.get_all()
        items = [case_to_dict(c) for c in rows]
        return {"total": len(items), "items": items[offset:offset + limit]}
    finally:
        service.db.close()


@router.post("")
def save_case(case: TestCaseIn):
    """编写 -> 保存单条（有 id 则更新，无 id 自动生成 TC 前缀 id）。"""
    if not case.input:
        raise HTTPException(status_code=400, detail="input is required")
    service = TestCaseService()
    try:
        data = case.model_dump()
        if not (data.get("id") or "").strip():
            data["id"] = f"TC{service.get_max_tc_id_num() + 1:04d}"
        service.upsert_records([data])
        return {"ok": True, "id": data["id"], "turn_index": data["turn_index"]}
    finally:
        service.db.close()


@router.post("/import")
def import_cases(req: ImportRequest):
    """批量导入/更新（INSERT ... ON CONFLICT DO UPDATE）。"""
    if not req.cases:
        raise HTTPException(status_code=400, detail="cases is empty")
    service = TestCaseService()
    try:
        records = [c.model_dump() for c in req.cases]
        # 缺失 id 的用例自动生成不重复的 TC 前缀 id
        no_id = [r for r in records if not (r.get("id") or "").strip()]
        if no_id:
            next_num = service.get_max_tc_id_num() + 1
            for r in records:
                if not (r.get("id") or "").strip():
                    r["id"] = f"TC{next_num:04d}"
                    next_num += 1
        saved = service.upsert_records(records)
        return {"ok": True, "saved": saved, "total": len(records)}
    finally:
        service.db.close()


@router.delete("")
def delete_cases(req: DeleteRequest):
    """按 ID 列表批量删除。"""
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids is empty")
    service = TestCaseService()
    try:
        deleted = service.delete_by_ids(req.ids)
        return {"ok": True, "deleted": deleted}
    finally:
        service.db.close()


@router.post("/bulk-update")
def bulk_update(req: BulkUpdateRequest):
    """批量更新 category_id / priority / module（至少指定一项）。"""
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids is empty")
    if req.category_id is None and req.priority is None and req.module is None:
        raise HTTPException(status_code=400, detail="nothing to update")
    if req.priority is not None and req.priority.strip().upper() not in ("P0", "P1", "P2"):
        raise HTTPException(status_code=400, detail="priority must be P0/P1/P2")
    service = TestCaseService()
    try:
        updated = 0
        if req.category_id is not None:
            updated += service.update_category(req.ids, req.category_id)
        if req.priority is not None:
            updated += service.update_priority_by_ids(req.ids, req.priority.strip().upper())
        if req.module is not None:
            updated += service.update_module_by_ids(req.ids, req.module)
        return {"ok": True, "updated": updated}
    finally:
        service.db.close()