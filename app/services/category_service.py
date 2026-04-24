from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.category import Category
from app.models.test_case import TestCase
import uuid

class CategoryService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_tree(self) -> List[dict]:
        """获取完整目录树结构"""
        categories = self.db.query(Category).order_by(Category.level, Category.sort_order).all()
        return self._build_tree(categories)
    
    def _build_tree(self, categories: List[Category]) -> List[dict]:
        """构建树形结构"""
        id_map = {c.id: {'id': c.id, 'name': c.name, 'level': c.level, 'path': c.path, 'children': []} for c in categories}
        tree = []
        for c in categories:
            node = id_map[c.id]
            if c.parent_id and c.parent_id in id_map:
                id_map[c.parent_id]['children'].append(node)
            else:
                tree.append(node)
        return tree
    
    def create(self, name: str, parent_id: Optional[str] = None) -> Category:
        """创建目录"""
        # 验证父目录
        if parent_id:
            parent = self.db.query(Category).filter(Category.id == parent_id).first()
            if not parent:
                raise ValueError("父目录不存在")
            if parent.level >= 3:
                raise ValueError("目录层级不能超过3级")
            level = parent.level + 1
            path = f"{parent.path}/{name}"
        else:
            # 顶级目录（level=1），挂在 root 下？
            # 需求中只有三级，所有的都属于分类树
            # 实际设计是 parent_id=None 的都是顶级目录
            level = 1
            path = name
            parent_id = None
        
        # 检查同名
        existing = self.db.query(Category).filter(Category.parent_id == parent_id, Category.name == name).first()
        if existing:
            raise ValueError("同级目录下已存在同名文件夹")
            
        # 生成唯一 ID
        cat_id = f"cat_{uuid.uuid4().hex[:8]}"
        
        # 计算排序
        max_order = self.db.query(Category).filter(Category.parent_id == parent_id).count()
        
        category = Category(
            id=cat_id,
            name=name,
            parent_id=parent_id,
            path=path,
            level=level,
            sort_order=max_order
        )
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category
    
    def update(self, cat_id: str, name: str) -> Category:
        """更新目录名称"""
        if cat_id == 'root':
            raise ValueError("根目录不可修改")
        
        category = self.db.query(Category).filter(Category.id == cat_id).first()
        if not category:
            raise ValueError("目录不存在")
            
        existing = self.db.query(Category).filter(Category.parent_id == category.parent_id, Category.name == name, Category.id != cat_id).first()
        if existing:
            raise ValueError("同级目录下已存在同名文件夹")
        
        old_path = category.path
        new_path = f"{'/'.join(old_path.rsplit('/', 1)[:-1])}/{name}" if '/' in old_path else name
        
        # 更新当前目录
        category.name = name
        category.path = new_path
        
        # 更新所有子目录的 path
        children = self.db.query(Category).filter(Category.path.like(f"{old_path}/%")).all()
        for child in children:
            child.path = child.path.replace(old_path, new_path, 1)
        
        self.db.commit()
        self.db.refresh(category)
        return category
    
    def delete(self, cat_id: str) -> int:
        """删除目录（如果有测试用例则禁止删除）"""
        if cat_id == 'root':
            raise ValueError("根目录不可删除")
        
        category = self.db.query(Category).filter(Category.id == cat_id).first()
        if not category:
            raise ValueError("目录不存在")
        
        # 检查该目录及子目录下是否有测试用例
        case_count = self.db.query(TestCase).filter(
            TestCase.category_id.in_(
                self.db.query(Category.id).filter(
                    (Category.id == cat_id) | (Category.path.like(f"{category.path}/%"))
                )
            )
        ).count()
        
        if case_count > 0:
            raise ValueError(f"该目录下有 {case_count} 个测试用例，请先移除或转移用例后再删除目录")
        
        # 检查是否有子目录
        child_count = self.db.query(Category).filter(Category.parent_id == cat_id).count()
        if child_count > 0:
            raise ValueError(f"该目录下有 {child_count} 个子目录，请先删除子目录")
        
        self.db.delete(category)
        self.db.commit()
        
        return 0
    
    def get_case_count(self, cat_id: str) -> int:
        """获取目录下的测试用例数量（含子目录）"""
        category = self.db.query(Category).filter(Category.id == cat_id).first()
        if not category:
            return 0
        
        return self.db.query(TestCase).filter(
            TestCase.category_id.in_(
                self.db.query(Category.id).filter(
                    (Category.id == cat_id) | (Category.path.like(f"{category.path}/%"))
                )
            )
        ).count()
    
    def get_total_case_count(self) -> int:
        """获取所有测试用例的总数"""
        return self.db.query(TestCase).count()
