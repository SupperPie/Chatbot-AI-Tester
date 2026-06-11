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

    # assertions: JSONB 列，确保是 list
    assertions = out.get('assertions')
    if isinstance(assertions, str):
        try:
            parsed = json.loads(assertions)
            out['assertions'] = parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            out['assertions'] = []

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

    def insert_many(self, records: List[Dict]) -> int:
        """只插入新记录（不做全量同步）"""
        allowed_fields = {c.name for c in TestCase.__table__.columns}
        count = 0
        
        for r in records:
            if not r.get('id'):
                continue
            clean = _sanitize_record(r)
            ti = int(clean.get('turn_index') or 1)
            clean['turn_index'] = ti
            
            # 检查是否已存在
            existing = self.db.query(TestCase).filter(
                TestCase.id == clean['id'],
                TestCase.turn_index == ti
            ).first()
            
            if not existing:
                fields = {k: v for k, v in clean.items() if k in allowed_fields}
                fields['turn_index'] = ti
                fields.setdefault('created_at', datetime.utcnow())
                fields.setdefault('updated_at', datetime.utcnow())
                self.db.add(TestCase(**fields))
                count += 1
        
        self.db.commit()
        return count

    def upsert_all(self, records: List[Dict]) -> int:
        """批量 upsert：更新已有、新增缺少（不自动删除其他记录）"""
        # 注意：此方法不会删除数据库中不在 records 里的记录
        # 如需删除，请显式调用 delete_by_ids()
        
        # Upsert 每条记录，分批提交避免超时
        allowed_fields = {c.name for c in TestCase.__table__.columns}
        BATCH_SIZE = 100  # 每 100 条提交一次
        count = 0
        
        for r in records:
            if not r.get('id'):
                continue
            clean = _sanitize_record(r)
            ti = int(clean.get('turn_index') or 1)
            clean['turn_index'] = ti
            existing = self.db.query(TestCase).filter(
                TestCase.id == clean['id'],
                TestCase.turn_index == ti
            ).first()
            if existing:
                for k, v in clean.items():
                    if k not in ('id', 'turn_index') and k in allowed_fields:
                        setattr(existing, k, v)
                existing.updated_at = datetime.utcnow()
            else:
                fields = {k: v for k, v in clean.items() if k in allowed_fields}
                fields['turn_index'] = ti
                fields.setdefault('created_at', datetime.utcnow())
                fields.setdefault('updated_at', datetime.utcnow())
                self.db.add(TestCase(**fields))
            
            count += 1
            # 每 BATCH_SIZE 条提交一次
            if count % BATCH_SIZE == 0:
                self.db.commit()

        # 提交剩余的
        self.db.commit()
        return len(records)

    def upsert_records(self, records: List[Dict]) -> int:
        """增量 upsert：只对给定的若干条记录做更新或插入。

        与 upsert_all 的区别：
        - 语义明确为"只保存这几条"，不做全量同步
        - 一次性 commit（适合小批量）
        - 不含任何 ID 自动生成/重分配逻辑：id 仅作为 (id, turn_index) 查询条件
          用于定位 DB 记录；如果传入的 record 中字段值由用户修改（包括 id 本身），
          会按用户提供的值写入，但方法内部不会主动生成新 ID
        """
        allowed_fields = {c.name for c in TestCase.__table__.columns}
        for r in records:
            if not r.get('id'):
                continue
            clean = _sanitize_record(r)
            ti = int(clean.get('turn_index') or 1)
            clean['turn_index'] = ti
            existing = self.db.query(TestCase).filter(
                TestCase.id == clean['id'],
                TestCase.turn_index == ti
            ).first()
            if existing:
                for k, v in clean.items():
                    if k not in ('id', 'turn_index') and k in allowed_fields:
                        setattr(existing, k, v)
                existing.updated_at = datetime.utcnow()
            else:
                fields = {k: v for k, v in clean.items() if k in allowed_fields}
                fields['turn_index'] = ti
                fields.setdefault('created_at', datetime.utcnow())
                fields.setdefault('updated_at', datetime.utcnow())
                self.db.add(TestCase(**fields))
        self.db.commit()
        return len(records)

    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()
