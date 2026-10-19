"""对外接口 - 元信息（分类树 / API 配置），供 agent 自主选择分类与目标接口。"""
from fastapi import APIRouter

from app.services.category_service import CategoryService
from app.services.api_config_service import ApiConfigService

router = APIRouter()


@router.get("/categories/tree")
def category_tree():
    """完整目录树结构。"""
    service = CategoryService()
    try:
        return service.get_tree()
    finally:
        service.db.close()


@router.get("/api-configs")
def api_configs():
    """所有 API 配置（name -> url/type/...），用于执行时指定 api_name。"""
    service = ApiConfigService()
    try:
        return service.get_all()
    finally:
        service.db.close()