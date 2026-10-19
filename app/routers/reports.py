"""对外接口 - 测试报告管理 + 导出飞书"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.history_service import HistoryService
from app.feishu_client import export_report_to_feishu, parse_feishu_url

router = APIRouter()


class DeleteRequest(BaseModel):
    ids: List[str]


class FeishuExport(BaseModel):
    feishu_url: str
    create_new_sheet: bool = True
    sheet_title: Optional[str] = None


class FeishuExportItem(BaseModel):
    report_id: str
    feishu_url: str
    sheet_id: Optional[str] = None


class FeishuBatchExport(BaseModel):
    exports: List[FeishuExportItem]
    # new_sheet_per_report: 每个报告在目标文档里新建一个 sheet
    # append_same_sheet: 追加到同一 sheet（需提供 sheet_id）
    mode: str = "new_sheet_per_report"
    sheet_title: Optional[str] = None


def _load_report(report_id: str):
    service = HistoryService()
    try:
        return service.get_by_id(report_id)
    finally:
        service.db.close()


# 注意：此批量端点必须注册在 /{report_id}/export/feishu 之前，
# 否则 /api/v1/reports/export/feishu 会被误解析成 report_id="export"。
@router.post("/export/feishu")
def export_batch(req: FeishuBatchExport):
    """批量导出多个报告到飞书（支持同一文档多 sheet / 追加同一 sheet / 多个文档）。"""
    if not req.exports:
        raise HTTPException(status_code=400, detail="exports is empty")
    if req.mode not in ("new_sheet_per_report", "append_same_sheet"):
        raise HTTPException(status_code=400, detail="mode must be new_sheet_per_report or append_same_sheet")

    results_out = []
    for item in req.exports:
        entry = _load_report(item.report_id)
        if not entry:
            results_out.append({"report_id": item.report_id, "success": False, "message": "report not found"})
            continue
        report_results = entry.get("results", [])
        if not report_results:
            results_out.append({"report_id": item.report_id, "success": False, "message": "report has no results"})
            continue

        parsed = parse_feishu_url(item.feishu_url)
        create_new = req.mode == "new_sheet_per_report"
        sheet_id = parsed.get("sheet_id") or item.sheet_id
        try:
            result = export_report_to_feishu(
                report_results,
                spreadsheet_token=parsed.get("spreadsheet_token"),
                sheet_id=sheet_id,
                wiki_token=parsed.get("wiki_token"),
                api_name=entry.get("api_name", "Test"),
                create_new_sheet=create_new,
                sheet_title=req.sheet_title,
            )
            results_out.append({
                "report_id": item.report_id,
                "success": bool(result.get("success")),
                "message": result.get("message", ""),
                "rows_count": result.get("rows_count", 0),
            })
        except Exception as e:
            results_out.append({"report_id": item.report_id, "success": False, "message": str(e)})
    return {"results": results_out}


@router.get("")
def list_reports(limit: int = 20, offset: int = 0):
    """报告列表（摘要，不含 results）。"""
    service = HistoryService()
    try:
        history = service.get_all(include_results=False)
        return {"total": len(history), "items": history[offset:offset + limit]}
    finally:
        service.db.close()


@router.get("/{report_id}")
def get_report(report_id: str):
    """报告详情（含 results）。"""
    entry = _load_report(report_id)
    if not entry:
        raise HTTPException(status_code=404, detail="report not found")
    return entry


@router.delete("")
def delete_reports(req: DeleteRequest):
    """批量删除报告。"""
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids is empty")
    service = HistoryService()
    try:
        deleted = service.delete(req.ids)
        return {"ok": True, "deleted": deleted}
    finally:
        service.db.close()


@router.post("/{report_id}/export/feishu")
def export_one(report_id: str, req: FeishuExport):
    """导出单个报告到飞书表格。"""
    entry = _load_report(report_id)
    if not entry:
        raise HTTPException(status_code=404, detail="report not found")
    results = entry.get("results", [])
    if not results:
        return {"success": False, "message": "report has no results"}

    parsed = parse_feishu_url(req.feishu_url)
    return export_report_to_feishu(
        results,
        spreadsheet_token=parsed.get("spreadsheet_token"),
        sheet_id=parsed.get("sheet_id"),
        wiki_token=parsed.get("wiki_token"),
        api_name=entry.get("api_name", "Test"),
        create_new_sheet=req.create_new_sheet,
        sheet_title=req.sheet_title,
    )