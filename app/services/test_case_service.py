from typing import List, Optional
from app.database import SessionLocal
# 必须先导入 Category，因为 TestCase 有外键引用
from app.models.category import Category
from app.models.test_case import TestCase

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
    
    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()
