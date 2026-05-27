from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from app.database import Base, SCHEMA


class AssertionComponent(Base):
    __tablename__ = 'assertion_components'
    __table_args__ = {'schema': SCHEMA}

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(30), nullable=False)  # field / structure / status_code / composite
    condition = Column(String(30), nullable=False)  # equals / contains / required_fields / all_pass etc.
    config = Column(JSONB, nullable=False)
    tags = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
