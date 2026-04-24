from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base, SCHEMA


class ApiConfig(Base):
    __tablename__ = 'api_configs'
    __table_args__ = {'schema': SCHEMA}

    name = Column(String(100), primary_key=True)
    url = Column(Text, nullable=False)
    description = Column(Text)
    type = Column(String(50))
    token = Column(Text)
    request_params = Column(JSONB, default=dict)
