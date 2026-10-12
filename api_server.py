"""
API Server - 提供测试报告导出等接口
启动方式: python3.11 -m uvicorn api_server:app --host 0.0.0.0 --port 8000
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv(override=True)

# 公网鉴权：所有 /api/* 接口要求携带 X-API-Key 头，值须匹配 .env 中的 API_KEY
# 未配置 API_KEY 时直接拒绝所有 API 请求，避免暴露到公网后裸奔
API_KEY = os.getenv("API_KEY", "").strip()

app = FastAPI(
    title="Chatbot AI Tester API",
    description="测试执行、报告导出及管理接口",
    version="5.0"
)


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """统一鉴权：仅保护 /api/* 路径，根路径保持开放用于健康检查"""
    if request.url.path.startswith("/api/"):
        if not API_KEY:
            return JSONResponse(
                status_code=503,
                content={"detail": "服务端未配置 API_KEY，已拒绝所有 API 请求"},
            )
        key = request.headers.get("X-API-Key", "")
        if key != API_KEY:
            return JSONResponse(
                status_code=401,
                content={"detail": "无效或缺失的 API Key"},
            )
    return await call_next(request)


class ExportToFeishuRequest(BaseModel):
    """导出到飞书的请求参数"""
    report_id: str  # 报告 ID
    feishu_url: str  # 飞书表格 URL
    create_new_sheet: bool = True  # 是否创建新工作表


class ExportToFeishuResponse(BaseModel):
    """导出到飞书的响应"""
    success: bool
    message: str
    rows_count: Optional[int] = None
    sheet_name: Optional[str] = None


class ReportListItem(BaseModel):
    """报告列表项"""
    id: str
    timestamp: str
    api_name: str
    passed: int
    total: int
    pass_rate: float


@app.get("/")
def root():
    """API 根路径"""
    return {"message": "Chatbot AI Tester API", "version": "1.0.0"}


@app.get("/api/reports", response_model=List[ReportListItem])
def list_reports(limit: int = 20, offset: int = 0):
    """
    获取报告列表
    
    - **limit**: 返回数量，默认 20
    - **offset**: 偏移量，默认 0
    """
    try:
        from app.services.history_service import HistoryService
        service = HistoryService()
        history = service.get_all(include_results=False)
        
        # 分页
        paginated = history[offset:offset + limit]
        
        result = []
        for entry in paginated:
            total = entry.get('total', 0)
            passed = entry.get('passed', 0)
            pass_rate = (passed / total * 100) if total > 0 else 0
            
            result.append(ReportListItem(
                id=entry.get('id', ''),
                timestamp=entry.get('timestamp', ''),
                api_name=entry.get('api_name', 'Unknown'),
                passed=passed,
                total=total,
                pass_rate=round(pass_rate, 2)
            ))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reports/{report_id}")
def get_report(report_id: str):
    """
    获取单个报告详情
    
    - **report_id**: 报告 ID
    """
    try:
        from app.services.history_service import HistoryService
        service = HistoryService()
        entry = service.get_by_id(report_id)
        
        if not entry:
            raise HTTPException(status_code=404, detail="Report not found")
        
        return entry
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reports/{report_id}/export/feishu", response_model=ExportToFeishuResponse)
def export_report_to_feishu(report_id: str, request: ExportToFeishuRequest):
    """
    导出报告到飞书表格
    
    - **report_id**: 报告 ID
    - **feishu_url**: 飞书表格 URL (支持 wiki 和 sheets 格式)
    - **create_new_sheet**: 是否创建新工作表，默认 True
    
    示例请求:
    ```json
    {
        "report_id": "xxx",
        "feishu_url": "https://dragonpass.feishu.cn/wiki/QKLQwwM0BixcMjkTZWVc4Wvmnoh?sheet=eRNryN",
        "create_new_sheet": true
    }
    ```
    """
    try:
        # 1. 获取报告数据
        from app.services.history_service import HistoryService
        service = HistoryService()
        entry = service.get_by_id(report_id)
        
        if not entry:
            raise HTTPException(status_code=404, detail="Report not found")
        
        results = entry.get('results', [])
        if not results:
            return ExportToFeishuResponse(
                success=False,
                message="报告中没有测试结果"
            )
        
        # 2. 解析飞书 URL
        from app.feishu_client import export_report_to_feishu as do_export, parse_feishu_url
        parsed = parse_feishu_url(request.feishu_url)
        
        # 3. 执行导出
        api_name = entry.get('api_name', 'Test')
        export_result = do_export(
            results,
            spreadsheet_token=parsed.get("spreadsheet_token"),
            sheet_id=parsed.get("sheet_id"),
            wiki_token=parsed.get("wiki_token"),
            api_name=api_name,
            create_new_sheet=request.create_new_sheet
        )
        
        if export_result.get("success"):
            from datetime import datetime
            sheet_name = f"{api_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}" if request.create_new_sheet else None
            return ExportToFeishuResponse(
                success=True,
                message=export_result.get("message"),
                rows_count=export_result.get("rows_count"),
                sheet_name=sheet_name
            )
        else:
            return ExportToFeishuResponse(
                success=False,
                message=export_result.get("message")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reports/latest/export/feishu")
def export_latest_report_to_feishu(feishu_url: str, create_new_sheet: bool = True):
    """
    导出最新报告到飞书表格 (GET 方式，方便直接调用)
    
    - **feishu_url**: 飞书表格 URL
    - **create_new_sheet**: 是否创建新工作表，默认 True
    
    示例:
    ```
    GET /api/reports/latest/export/feishu?feishu_url=https://xxx.feishu.cn/wiki/xxx
    ```
    """
    try:
        # 获取最新报告
        from app.services.history_service import HistoryService
        service = HistoryService()
        history = service.get_all(include_results=False)
        
        if not history:
            raise HTTPException(status_code=404, detail="No reports found")
        
        latest = history[0]  # 最新的报告
        
        # 调用导出
        request = ExportToFeishuRequest(
            report_id=latest['id'],
            feishu_url=feishu_url,
            create_new_sheet=create_new_sheet
        )
        
        return export_report_to_feishu(latest['id'], request)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────
# 测试执行接口（供 AI Agent / 外部调用触发执行测试用例）
# ─────────────────────────────────────────────────────────────


class RunJobsRequest(BaseModel):
    """触发执行测试用例的请求参数

    支持两种用例指定方式：
    - case_ids: 单个 ID 列表（等同 batches 只含一个批次）
    - batches: 多个 ID 列表，每个列表生成一份独立的测试报告
    """
    api_name: str = "Bundle API"
    execution_mode: str = "full"  # full | semantic | assertion
    max_workers: int = 3          # 并发线程数 1-10
    report_name: Optional[str] = None
    case_ids: List[str] = []
    batches: List[List[str]] = []
    wait: bool = False            # True 时阻塞到执行结束再返回
    timeout_seconds: int = 1800   # wait=True 时的最长等待秒数


def _load_cases_by_ids(case_ids: List[str]) -> List[Dict]:
    """按用例 ID 从主数据源加载完整 case 数据（含多轮的所有 turn）"""
    from app.utils import load_data
    df = load_data()
    if df is None or df.empty or "id" not in df.columns:
        return []
    wanted = {str(c).strip() for c in case_ids if str(c).strip()}
    if not wanted:
        return []
    mask = df["id"].astype(str).str.strip().isin(wanted)
    return df[mask].to_dict(orient="records")


def _build_job_json(data: Dict) -> Dict:
    """把 HistoryService 返回的报告 dict 整理成对 agent 友好的结构"""
    total = data.get("total") or 0
    passed = data.get("passed") or 0
    pass_rate = round(passed / total * 100, 2) if total > 0 else 0.0
    return {
        "id": data.get("id"),
        "status": data.get("status"),
        "api_name": data.get("api_name"),
        "report_name": data.get("report_name"),
        "execution_mode": data.get("execution_mode"),
        "max_workers": data.get("max_workers"),
        "total": int(total),
        "passed": int(passed),
        "failed": int(data.get("failed") or 0),
        "started_count": int(data.get("started_count") or 0),
        "pass_rate": pass_rate,
        "error_message": data.get("error_message"),
        "timestamp": data.get("timestamp"),
        "duration": data.get("duration"),
        "results": data.get("results", []),
    }


def _poll_job(job_id: str, timeout_seconds: int) -> Dict:
    """轮询 job 直到结束或超时，返回最终的报告数据"""
    import time
    from app.services.history_service import HistoryService
    deadline = time.time() + max(int(timeout_seconds), 1)
    data = None
    while time.time() < deadline:
        svc = HistoryService()
        data = svc.get_by_id(job_id)
        if data and data.get("status") not in ("running",):
            break
        time.sleep(1)
    if data is None:
        svc = HistoryService()
        data = svc.get_by_id(job_id)
    return data or {}


@app.get("/api/meta/apis")
def list_apis():
    """列出可用的 API 配置名（作为 POST /api/jobs 的 api_name 参数）"""
    try:
        from chat_client import get_available_apis
        return {"apis": get_available_apis()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jobs")
def create_jobs(request: RunJobsRequest):
    """触发执行测试用例，支持多批（每个 ID 列表生成一份独立报告）

    示例:
    ```json
    {
        "api_name": "Bundle API",
        "execution_mode": "full",
        "max_workers": 3,
        "report_name": "PRD 回归",
        "batches": [["TC0001", "TC0002"], ["TC0003"]],
        "wait": false
    }
    ```
    """
    from app.job_manager import get_job_manager
    from chat_client import get_available_apis

    # 1. 校验 api_name
    available = set(get_available_apis())
    if request.api_name not in available:
        raise HTTPException(
            status_code=400,
            detail=f"api_name '{request.api_name}' 不存在，可用: {sorted(available)}",
        )

    # 2. 校验执行模式
    mode = (request.execution_mode or "full").strip().lower()
    if mode not in ("full", "semantic", "assertion"):
        raise HTTPException(status_code=400, detail="execution_mode 必须是 full/semantic/assertion")

    # 3. 规范化并发数
    workers = max(1, min(int(request.max_workers or 3), 10))

    # 4. 归一化批次：优先 batches，否则单列表 case_ids
    batches = list(request.batches) if request.batches else ([list(request.case_ids)] if request.case_ids else [])
    if not batches:
        raise HTTPException(status_code=400, detail="请提供 case_ids 或 batches")

    mgr = get_job_manager()
    multi = len(batches) > 1
    launched = []  # [{job_id, total, report_name} 或 {error, case_ids}]

    for i, batch in enumerate(batches):
        cases = _load_cases_by_ids(batch)
        if not cases:
            launched.append({"error": f"批次 {i + 1} 未匹配到任何用例", "case_ids": batch})
            continue
        name = None
        if request.report_name:
            name = f"{request.report_name} #{i + 1}" if multi else request.report_name
        job_id = mgr.run_background_job(
            cases,
            api_name=request.api_name,
            execution_mode=mode,
            max_workers=workers,
            report_name=name,
        )
        total = len({c.get("id") for c in cases if c.get("id") is not None})
        launched.append({"job_id": job_id, "total": total, "report_name": name})

    if not launched:
        raise HTTPException(status_code=400, detail="没有可执行的用例")

    # 5. 组装返回
    payload = []
    for item in launched:
        if "error" in item:
            payload.append(item)
            continue
        if request.wait:
            data = _poll_job(item["job_id"], request.timeout_seconds)
            payload.append(_build_job_json(data))
        else:
            payload.append({
                "job_id": item["job_id"],
                "total": item["total"],
                "report_name": item["report_name"],
                "status": "running",
            })

    return {"jobs": payload}


@app.get("/api/jobs")
def list_jobs(status: Optional[str] = None, limit: int = 20, offset: int = 0, include_results: bool = False):
    """获取执行任务（报告）列表，可按 status 过滤：running/completed/failed/cancelled/interrupted"""
    try:
        from app.services.history_service import HistoryService
        svc = HistoryService()
        history = svc.get_all(include_results=include_results)
        if status:
            history = [h for h in history if h.get("status") == status]
        paginated = history[offset:offset + int(limit)]
        return [_build_job_json(h) for h in paginated]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, include_results: bool = True):
    """获取某个执行任务的进度、结果与总结"""
    try:
        from app.services.history_service import HistoryService
        svc = HistoryService()
        data = svc.get_by_id(job_id)
        if not data:
            raise HTTPException(status_code=404, detail="Job not found")
        out = _build_job_json(data)
        if not include_results:
            out.pop("results", None)
        return out
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
