"""
断言组件功能 - 数据库迁移脚本

执行内容:
1. 创建 assertion_components 表（如果不存在）
2. 为 test_cases 表添加 assertions 列（如果不存在）

安全性:
- 所有操作都是 IF NOT EXISTS，可重复执行
- 不修改、不删除任何现有数据
- 新列默认值为空数组 '[]'
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, engine, SCHEMA
from app.models.assertion_component import AssertionComponent
from sqlalchemy import text


def migrate():
    # 1. 创建 assertion_components 表
    print("[1/2] Creating 'assertion_components' table if not exists...")
    Base.metadata.create_all(bind=engine)
    print("      Done.")

    # 2. 为 test_cases 添加 assertions 列
    print("[2/2] Adding 'assertions' column to test_cases if not exists...")
    with engine.connect() as conn:
        # 检查列是否已存在
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = 'test_cases' AND column_name = 'assertions'"
        ), {"schema": SCHEMA})
        
        if result.fetchone() is None:
            conn.execute(text(
                f"ALTER TABLE {SCHEMA}.test_cases ADD COLUMN assertions JSONB DEFAULT '[]'"
            ))
            conn.commit()
            print("      Column 'assertions' added successfully.")
        else:
            print("      Column 'assertions' already exists, skipping.")

    print("\nMigration complete. No existing data was modified.")


if __name__ == "__main__":
    migrate()
