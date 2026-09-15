from sqlalchemy import Column, String, Text, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base, SCHEMA
from sqlalchemy.dialects.postgresql import JSONB

class TestCase(Base):
    __tablename__ = 'test_cases'
    __table_args__ = {'schema': SCHEMA}
    
    id = Column(String(50), primary_key=True)
    turn_index = Column(Integer, primary_key=True, default=1)
    type = Column(String(20), default='single')
    input = Column(Text, nullable=False)
    input_cn = Column(Text)
    expected_output = Column(Text)
    expected_output_cn = Column(Text)
    retrieval_context = Column(Text)
    description = Column(Text)
    validation = Column(Text)
    overall_criteria = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 目录关联
    category_id = Column(String(50), ForeignKey(f'{SCHEMA}.categories.id', ondelete='CASCADE'), default='root')
    category = relationship('Category', back_populates='test_cases')
    
    tags = Column(JSONB, default=list)
    assertions = Column(JSONB, default=list)  # [{"ref": "AC001", "params": {"expected": "dc"}}]
    priority = Column(String(2), nullable=True)  # P0/P1/P2，历史数据可为空
    module = Column(String(100), nullable=True)   # 模块/功能域标签（自由文本）
