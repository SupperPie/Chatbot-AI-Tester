import sys
import os

# Add parent directory to path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, Base, engine
from app.models.category import Category
from app.models.test_case import TestCase

def migrate_test_cases_to_root():
    """初始化根目录，并将所有无归属或使用 JSON 数据的测试用例默认归属到根目录"""
    
    # 确保数据库表存在
    print("Creating database tables if not exist...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # 1. 确保根目录存在
        root = db.query(Category).filter(Category.id == 'root').first()
        if not root:
            print("Creating 'root' category...")
            root = Category(
                id='root',
                name='全部用例',
                parent_id=None,
                path='全部用例',
                level=1,
                sort_order=0
            )
            db.add(root)
            db.commit()
        else:
            print("'root' category already exists.")
        
        # 2. 将所有 category_id 为 NULL 的测试用例设置为 'root'
        updated = db.query(TestCase).filter(TestCase.category_id == None).update(
            {'category_id': 'root'},
            synchronize_session=False
        )
        db.commit()
        
        print(f"Migration completed. {updated} test cases assigned to 'root' category.")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Starting category migration...")
    migrate_test_cases_to_root()
    print("Done.")
