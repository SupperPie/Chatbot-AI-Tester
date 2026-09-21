"""
API Server - 提供测试报告导出等接口
启动方式: python3.11 -m uvicorn api_server:app --host 0.0.0.0 --port 8000
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv(override=True)

app = FastAPI(
    title="Chatbot AI Tester API",
    description="测试报告导出及管理接口",
    version="4.3"
)


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
