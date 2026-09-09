from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from app.database import Base, SCHEMA


class TestHistory(Base):
    __tablename__ = 'test_history'
    __table_args__ = {'schema': SCHEMA}

    id = Column(String(50), primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    api_name = Column(String(100))
    total = Column(Integer, default=0)
    passed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    status = Column(String(20), default='pending')
    started_count = Column(Integer, default=0)
    source = Column(String(20), default='local')
    case_ids = Column(JSONB)  # 原始用例 ID 列表 [{"id": "TC0001", "turn_index": 1}, ...]
    error_message = Column(Text)  # 失败/中断的错误信息
    created_at = Column(DateTime, default=datetime.utcnow)

    results = relationship('TestResult', back_populates='history', cascade='all, delete-orphan',
                           order_by='TestResult.id')


class TestResult(Base):
    __tablename__ = 'test_results'
    __table_args__ = {'schema': SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    history_id = Column(String(50), ForeignKey(f'{SCHEMA}.test_history.id', ondelete='CASCADE'))
    case_id = Column(String(50))
    input = Column(Text)
    actual_output = Column(Text)
    expected_output = Column(Text)
    retrieval_context = Column(Text)
    score = Column(Float)
    reason = Column(Text)
    faithfulness_score = Column(Float)
    faithfulness_reason = Column(Text)
    passed = Column(Boolean, default=False)
    thinking = Column(Text)
    inform_base = Column(Text)
    raw = Column(Text)
    latency = Column(Float)
    ttft = Column(Float)
    type = Column(String(20))
    total_turns = Column(Integer)
    passed_turns = Column(Integer)
    success_rate = Column(Float)
    overall_score = Column(Float)
    overall_passed = Column(Boolean)
    turns = Column(JSONB)
    user_id = Column(String(100))
    session_id = Column(String(100))
    assertion_detail = Column(JSONB)  # 断言执行结果 {"passed": bool, "score": float, "results": [...]}
    category = Column(String(200))    # 执行时用例所在分类
    priority = Column(String(2))      # 执行时用例优先级 P0/P1/P2
    created_at = Column(DateTime, default=datetime.utcnow)

    history = relationship('TestHistory', back_populates='results')
