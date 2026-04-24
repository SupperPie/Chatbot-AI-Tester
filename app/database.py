from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dp_testmate")
DATABASE_SCHEMA = os.getenv("DATABASE_SCHEMA", "ai_chatbot_tester")

engine = create_engine(DATABASE_URL)

# 设置默认 schema
@event.listens_for(engine, "connect")
def set_search_path(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute(f"SET search_path TO {DATABASE_SCHEMA}, public")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# 导出 schema 供模型使用
SCHEMA = DATABASE_SCHEMA

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
