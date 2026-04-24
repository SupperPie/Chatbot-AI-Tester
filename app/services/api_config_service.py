from typing import Dict, Optional
from app.database import SessionLocal
from app.models.api_config import ApiConfig


class ApiConfigService:
    def __init__(self):
        self.db = SessionLocal()

    def get_all(self) -> Dict[str, dict]:
        """获取所有 API 配置，返回 {name: config_dict} 格式"""
        rows = self.db.query(ApiConfig).order_by(ApiConfig.name).all()
        result = {}
        for row in rows:
            result[row.name] = {
                "url": row.url or "",
                "description": row.description or "",
                "type": row.type or "",
                "token": row.token or "",
                "request_params": row.request_params or {},
            }
        return result

    def upsert(self, name: str, config: dict) -> None:
        """插入或更新单条 API 配置"""
        existing = self.db.query(ApiConfig).filter(ApiConfig.name == name).first()
        if existing:
            existing.url = config.get("url", "")
            existing.description = config.get("description", "")
            existing.type = config.get("type", "")
            existing.token = config.get("token", "")
            existing.request_params = config.get("request_params", {})
        else:
            row = ApiConfig(
                name=name,
                url=config.get("url", ""),
                description=config.get("description", ""),
                type=config.get("type", ""),
                token=config.get("token", ""),
                request_params=config.get("request_params", {}),
            )
            self.db.add(row)
        self.db.commit()

    def save_all(self, configs: Dict[str, dict]) -> None:
        """全量保存：删除不在 configs 中的行，upsert 所有行"""
        existing_names = {r.name for r in self.db.query(ApiConfig.name).all()}
        new_names = set(configs.keys())

        # 删除被移除的配置
        removed = existing_names - new_names
        if removed:
            self.db.query(ApiConfig).filter(ApiConfig.name.in_(removed)).delete(synchronize_session=False)

        # upsert 每条
        for name, config in configs.items():
            existing = self.db.query(ApiConfig).filter(ApiConfig.name == name).first()
            if existing:
                existing.url = config.get("url", "")
                existing.description = config.get("description", "")
                existing.type = config.get("type", "")
                existing.token = config.get("token", "")
                existing.request_params = config.get("request_params", {})
            else:
                row = ApiConfig(
                    name=name,
                    url=config.get("url", ""),
                    description=config.get("description", ""),
                    type=config.get("type", ""),
                    token=config.get("token", ""),
                    request_params=config.get("request_params", {}),
                )
                self.db.add(row)
        self.db.commit()

    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()
