"""测试数据库连接和表结构"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_SCHEMA = os.getenv("DATABASE_SCHEMA", "ai_chatbot_tester")

print(f"连接数据库: {DATABASE_URL}")
print(f"Schema: {DATABASE_SCHEMA}")
print("-" * 50)

try:
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # 设置 schema
    session.execute(text(f"SET search_path TO {DATABASE_SCHEMA}, public"))
    
    # 查询所有表
    result = session.execute(text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = :schema
        ORDER BY table_name
    """), {"schema": DATABASE_SCHEMA})
    
    tables = [row[0] for row in result]
    print(f"✅ 连接成功！找到 {len(tables)} 张表：")
    for t in tables:
        print(f"   - {t}")
    
    print("-" * 50)
    
    # 检查根目录是否存在
    result = session.execute(text("SELECT id, name, path, level FROM categories WHERE id = 'root'"))
    root = result.fetchone()
    if root:
        print(f"✅ 根目录存在: id={root[0]}, name={root[1]}")
    else:
        print("⚠️ 根目录不存在，需要创建")
    
    # 统计各表数据量
    print("-" * 50)
    print("各表数据量：")
    for table in tables:
        try:
            count_result = session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = count_result.scalar()
            print(f"   {table}: {count} 条")
        except Exception as e:
            print(f"   {table}: 查询失败 - {e}")
    
    session.close()
    print("-" * 50)
    print("✅ 数据库连接测试完成！")
    
except Exception as e:
    print(f"❌ 连接失败: {e}")
    import traceback
    traceback.print_exc()
