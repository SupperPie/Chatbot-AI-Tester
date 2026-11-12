"""
API Server - 对外接口（给 AI Agent / 第三方调用）

复用 app 下的 service / engine / job_manager 层，不经过 Streamlit UI。
统一鉴权：除根路径 `/` 健康检查外，所有接口要求 `X-API-Key` 头（值来自 .env 的 API_KEY）。

启动方式: .venv/bin/uvicorn api_server:app --host 0.0.0.0 --port 8000
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv(override=True)

from app.routers import cases, jobs, reports, meta

app = FastAPI(
    title="Chatbot AI Tester Open API",
    description="对外接口：测试用例 / 执行 / 报告 / 导出飞书",
    version="5.1"
)

API_KEY = os.getenv("API_KEY", "")


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """X-API-Key 鉴权：根路径 `/` 开放健康检查，其余全部要求携带密钥。"""
    if request.url.path == "/":
        return await call_next(request)
    if not API_KEY:
        return JSONResponse(status_code=503, content={"detail": "API_KEY not configured on server"})
    if request.headers.get("X-API-Key") != API_KEY:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing X-API-Key header"})
    return await call_next(request)


@app.get("/")
def root():
    """健康检查（开放，无需鉴权）。"""
    return {"message": "Chatbot AI Tester API", "version": "5.1"}


app.include_router(cases.router, prefix="/api/v1/cases", tags=["cases"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(meta.router, prefix="/api/v1", tags=["meta"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)