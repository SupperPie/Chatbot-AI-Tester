from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.category import Category
from app.models.test_case import TestCase
from app.database import SessionLocal, DATABASE_SCHEMA
from sqlalchemy import text
import uuid

class CategoryService:
    def __init__(self, db: Optional[Session] = None):
        self.db = db if db is not None else SessionLocal()
        self.db.execute(text(f"SET search_path TO {DATABASE_SCHEMA}, public"))
    
    def get_tree(self) -> List[dict]:
        """获取完整目录树结构"""
        categories = self.db.query(Category).order_by(Category.level, Category.sort_order).all()
        return self._build_tree(categories)
    
    def get_by_id(self, cat_id: str) -> Optional[Category]:
        """根据 ID 获取目录对象"""
        return self.db.query(Category).filter(Category.id == cat_id).first()

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

    def _normalize_parent_id(self, parent_id: Optional[str]) -> Optional[str]:
        if parent_id in (None, '', 'root', '__all__'):
            return None
        return parent_id

    def reorder_siblings(self, parent_id: Optional[str], ordered_ids: List[str]) -> int:
        """按给定顺序重排同级节点 sort_order。"""
        if not ordered_ids:
            raise ValueError("ordered_ids 不能为空")

        normalized_parent = self._normalize_parent_id(parent_id)
        siblings = self.db.query(Category).filter(Category.parent_id == normalized_parent).order_by(Category.sort_order, Category.id).all()
        sibling_ids = [c.id for c in siblings]

        if not sibling_ids:
            raise ValueError("未找到同级目录")

        ordered_set = set(ordered_ids)
        sibling_set = set(sibling_ids)
        if ordered_set != sibling_set:
            missing = list(sibling_set - ordered_set)
            extra = list(ordered_set - sibling_set)
            raise ValueError(f"ordered_ids 与同级目录不一致，missing={missing}, extra={extra}")

        order_map = {cat_id: idx for idx, cat_id in enumerate(ordered_ids)}
        for cat in siblings:
            cat.sort_order = order_map[cat.id]

        self.db.commit()
        return len(siblings)

    def move_node(self, cat_id: str, new_parent_id: Optional[str]) -> Category:
        """移动节点到新父目录，并递归修正子树 path/level。"""
        if cat_id == 'root':
            raise ValueError("根目录不可移动")

        category = self.db.query(Category).filter(Category.id == cat_id).first()
        if not category:
            raise ValueError("目录不存在")

        normalized_parent = self._normalize_parent_id(new_parent_id)
        if normalized_parent == cat_id:
            raise ValueError("不能将目录移动到自身")

        new_parent = None
        if normalized_parent is not None:
            new_parent = self.db.query(Category).filter(Category.id == normalized_parent).first()
            if not new_parent:
                raise ValueError("目标父目录不存在")
            if new_parent.level >= 3:
                raise ValueError("目录层级不能超过3级")

        old_parent = self._normalize_parent_id(category.parent_id)
        if old_parent == normalized_parent:
            return category

        old_path = category.path

        # 防循环：禁止移动到自己的子孙节点
        descendants = self.db.query(Category).filter(Category.path.like(f"{old_path}/%")).all()
        descendant_ids = {c.id for c in descendants}
        if normalized_parent in descendant_ids:
            raise ValueError("不能将目录移动到其子目录下")

        new_level = 1 if new_parent is None else new_parent.level + 1
        level_delta = new_level - category.level

        max_level_in_subtree = category.level
        if descendants:
            max_level_in_subtree = max(c.level for c in descendants + [category])
        if max_level_in_subtree + level_delta > 3:
            raise ValueError("移动后目录层级将超过3级")

        # 计算新 path 与同级 sort_order
        if new_parent is None:
            new_path = category.name
        else:
            new_path = f"{new_parent.path}/{category.name}"

        sibling_count = self.db.query(Category).filter(Category.parent_id == normalized_parent).count()

        category.parent_id = normalized_parent
        category.level = new_level
        category.path = new_path
        category.sort_order = sibling_count

        for child in descendants:
            child.path = child.path.replace(old_path, new_path, 1)
            child.level = child.level + level_delta

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
