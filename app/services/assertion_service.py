from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
from app.database import SessionLocal
import app.models  # noqa: F401 - ensure all models loaded for relationship resolution
from app.models.assertion_component import AssertionComponent


class AssertionService:
    def __init__(self):
        self.db = SessionLocal()

    # ──────────────────── 查询 ────────────────────

    def get_all(self) -> List[AssertionComponent]:
        return self.db.query(AssertionComponent).order_by(AssertionComponent.created_at.desc()).all()

    def get_by_id(self, component_id: str) -> Optional[AssertionComponent]:
        return self.db.query(AssertionComponent).filter(AssertionComponent.id == component_id).first()

    def get_by_category(self, category: str) -> List[AssertionComponent]:
        return self.db.query(AssertionComponent).filter(
            AssertionComponent.category == category
        ).order_by(AssertionComponent.created_at.desc()).all()

    def search(self, keyword: Optional[str] = None, category: Optional[str] = None,
               tag: Optional[str] = None) -> List[AssertionComponent]:
        query = self.db.query(AssertionComponent)
        if category:
            query = query.filter(AssertionComponent.category == category)
        if keyword:
            query = query.filter(AssertionComponent.name.ilike(f"%{keyword}%"))
        if tag:
            # JSONB array contains
            query = query.filter(AssertionComponent.tags.contains([tag]))
        return query.order_by(AssertionComponent.created_at.desc()).all()

    def get_all_tags(self) -> List[str]:
        """获取所有已使用的标签（去重）"""
        components = self.db.query(AssertionComponent.tags).all()
        tag_set = set()
        for (tags,) in components:
            if tags:
                for t in tags:
                    tag_set.add(t)
        return sorted(tag_set)

    # ──────────────────── 写入 ────────────────────

    def create(self, data: Dict[str, Any]) -> AssertionComponent:
        component_id = data.get('id') or f"AC{uuid.uuid4().hex[:6].upper()}"
        component = AssertionComponent(
            id=component_id,
            name=data['name'],
            description=data.get('description', ''),
            category=data['category'],
            condition=data['condition'],
            config=data.get('config', {}),
            tags=data.get('tags', []),
        )
        self.db.add(component)
        self.db.commit()
        self.db.refresh(component)
        return component

    def update(self, component_id: str, data: Dict[str, Any]) -> Optional[AssertionComponent]:
        component = self.get_by_id(component_id)
        if not component:
            return None
        for key in ('name', 'description', 'category', 'condition', 'config', 'tags'):
            if key in data:
                setattr(component, key, data[key])
        component.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(component)
        return component

    def delete(self, component_id: str) -> bool:
        component = self.get_by_id(component_id)
        if not component:
            return False
        self.db.delete(component)
        self.db.commit()
        return True

    # ──────────────────── 引用统计 ────────────────────

    def get_reference_count(self, component_id: str) -> int:
        """统计该组件被多少测试用例的 validation 字段引用"""
        from app.models.test_case import TestCase
        import json
        count = 0
        cases = self.db.query(TestCase.validation).filter(TestCase.validation.isnot(None)).all()
        for (validation_str,) in cases:
            if not validation_str or not validation_str.strip():
                continue
            try:
                validation = json.loads(validation_str)
                if isinstance(validation, list):
                    for item in validation:
                        if isinstance(item, dict) and item.get('ref') == component_id:
                            count += 1
                            break
            except (json.JSONDecodeError, TypeError):
                continue
        return count

    # ──────────────────── 去重匹配 ────────────────────

    def find_matching_component(self, category: str, condition: str,
                                preset_params: Dict[str, Any]) -> Optional[AssertionComponent]:
        """
        查找与给定 category + condition + preset 参数完全匹配的已有组件。
        用于 AI 生成时的去重判断。
        """
        candidates = self.db.query(AssertionComponent).filter(
            AssertionComponent.category == category,
            AssertionComponent.condition == condition,
        ).all()

        for comp in candidates:
            config = comp.config or {}
            params = config.get('params', config)
            # 提取 preset 参数（排除 deferred）
            deferred = config.get('deferred_params', [])
            comp_preset = {k: v for k, v in params.items() if k not in deferred}
            if comp_preset == preset_params:
                return comp
        return None

    def find_similar_components(self, category: str, condition: str) -> List[AssertionComponent]:
        """查找同 category + condition 的组件（近似匹配，用于提示）"""
        return self.db.query(AssertionComponent).filter(
            AssertionComponent.category == category,
            AssertionComponent.condition == condition,
        ).all()
