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
    report_name = Column(String(200))  # 用户自定义的报告名称（Test Report 页显示）
    execution_mode = Column(String(20), default='full')  # 运行时执行模式：full/semantic/assertion（Report 页默认值用）
    max_workers = Column(Integer, default=3)  # 运行时并发线程数（Report 页默认值用）
    total = Column(Integer, default=0)
    passed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    status = Column(String(20), default='pending')
    started_count = Column(Integer, default=0)
    source = Column(String(20), default='local')
    case_ids = Column(JSONB)  # 原始用例 ID 列表 [{"id": "TC0001", "turn_index": 1}, ...]
    error_message = Column(Text)  # 失败/中断的错误信息
    heartbeat = Column(DateTime)  # Job 心跳：每完成一条用例更新一次，用于跨进程判断 Job 是否存活
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
    input_cn = Column(Text)
    actual_output = Column(Text)
    actual_output_cn = Column(Text)
    expected_output = Column(Text)
    expected_output_cn = Column(Text)
    description = Column(Text)
    tags = Column(JSONB)
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
    module = Column(String(100))      # 执行时用例模块标签
    review_comment = Column(Text)     # 人工评审备注
    validation = Column(Text)         # 执行时用例的验证规则（JSON 字符串）
    overall_criteria = Column(Text)   # 执行时用例的全局判定标准
    created_at = Column(DateTime, default=datetime.utcnow)

    history = relationship('TestHistory', back_populates='results')
