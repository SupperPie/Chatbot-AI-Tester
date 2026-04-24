import sys
from app.database import SessionLocal
from app.models.category import Category
from app.models.test_case import TestCase

try:
    db = SessionLocal()
    categories = db.query(Category).all()
    print("CATEGORIES IN DB:")
    for c in categories:
        print(f"ID: {c.id}, Name: {c.name}, Parent: {c.parent_id}")
    db.close()
except Exception as e:
    print(f"Error: {e}")
