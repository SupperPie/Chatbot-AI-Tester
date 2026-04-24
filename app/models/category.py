from sqlalchemy import Column, String, Integer, ForeignKey, CheckConstraint, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base, SCHEMA

class Category(Base):
    __tablename__ = 'categories'
    __table_args__ = (
        CheckConstraint('level >= 1 AND level <= 3', name='chk_level'),
        {'schema': SCHEMA}
    )
    
    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(String(50), ForeignKey(f'{SCHEMA}.categories.id', ondelete='CASCADE'), nullable=True)
    path = Column(String(500), nullable=False)
    level = Column(Integer, nullable=False, default=1)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    parent = relationship('Category', remote_side=[id], backref='children')
    test_cases = relationship('TestCase', back_populates='category', cascade='all, delete-orphan')
    
    @property
    def is_root(self):
        return self.id == 'root'
    
    def can_add_child(self):
        """检查是否可以添加子目录（不超过3级）"""
        return self.level < 3
