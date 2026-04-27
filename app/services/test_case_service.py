from typing import List, Optional, Dict
from datetime import datetime
import json
import math
from app.database import SessionLocal
# 必须先导入 Category，因为 TestCase 有外键引用
from app.models.category import Category
from app.models.test_case import TestCase


def _sanitize_record(r: dict) -> dict:
    """清洗一条记录，确保字段类型与 DB 列匹配。"""
    out = {}
    for k, v in r.items():
        # nan / 'nan' / 'None' → None
        if v is None:
            out[k] = None
        elif isinstance(v, float) and math.isnan(v):
            out[k] = None
        elif isinstance(v, str) and v.strip().lower() in ('nan', 'none'):
            out[k] = None
        else:
            out[k] = v

    # tags: JSONB 列，确保是 list（不能是字符串）
    tags = out.get('tags')
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
            out['tags'] = parsed if isinstance(parsed, list) else [tags]
        except (json.JSONDecodeError, ValueError):
            out['tags'] = [tags] if tags.strip() else []

    # overall_criteria / validation: Text 列，dict → JSON 字符串
    for field in ('overall_criteria', 'validation'):
        val = out.get(field)
        if isinstance(val, (dict, list)):
            out[field] = json.dumps(val, ensure_ascii=False)

    return out


class TestCaseService:
    def __init__(self):
        self.db = SessionLocal()
    
    def get_all(self) -> List[TestCase]:
        """获取所有测试用例"""
        return self.db.query(TestCase).order_by(TestCase.id).all()
    
    def get_by_category(self, category_id: str) -> List[TestCase]:
        """获取指定目录下的测试用例"""
        return self.db.query(TestCase).filter(TestCase.category_id == category_id).all()
    
    def update_category(self, test_case_ids: List[str], category_id: str) -> int:
        """批量更新测试用例的目录"""
        count = self.db.query(TestCase).filter(TestCase.id.in_(test_case_ids)).update(
            {TestCase.category_id: category_id},
            synchronize_session=False
        )
        self.db.commit()
        return count

    def delete_by_ids(self, ids: List[str]) -> int:
        """按 ID 列表批量删除测试用例"""
        count = self.db.query(TestCase).filter(TestCase.id.in_(ids)).delete(synchronize_session=False)
        self.db.commit()
        return count

    def upsert_all(self, records: List[Dict]) -> int:
        """全量同步：以 records 为准，更新已有、新增缺少、删除 DB 中多余的行"""
        incoming_ids = {r['id'] for r in records if r.get('id')}

        # 删除 DB 中不在 records 里的行
        if incoming_ids:
            self.db.query(TestCase).filter(~TestCase.id.in_(incoming_ids)).delete(synchronize_session=False)
        else:
            self.db.query(TestCase).delete(synchronize_session=False)

        # Upsert 每条记录
        allowed_fields = {c.name for c in TestCase.__table__.columns}
        for r in records:
            if not r.get('id'):
                continue
            clean = _sanitize_record(r)
            existing = self.db.query(TestCase).filter(TestCase.id == clean['id']).first()
            if existing:
                for k, v in clean.items():
                    if k != 'id' and k in allowed_fields:
                        setattr(existing, k, v)
                existing.updated_at = datetime.utcnow()
            else:
                fields = {k: v for k, v in clean.items() if k in allowed_fields}
                fields.setdefault('created_at', datetime.utcnow())
                fields.setdefault('updated_at', datetime.utcnow())
                self.db.add(TestCase(**fields))

        self.db.commit()
        return len(records)
    
    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()
