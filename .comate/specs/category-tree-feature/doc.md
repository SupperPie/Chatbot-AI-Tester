# Test Cases 目录树功能设计文档

## 1. 需求概述

在 Test Cases 页面实现最多三级的目录树结构，完成数据定义、数据迁移默认处理，并提供目录的增删改 UI 操作能力。

### 1.1 核心需求
- **数据结构**：支持最多 3 级深度的目录树
- **数据归属**：所有 Test Case 必须归属于一个目录节点
- **数据迁移**：现有数据默认归属到"根目录"节点
- **UI 功能**：目录树展示 + 增删改操作界面

### 1.2 约束条件
- 目录层级严格限制为最多 3 级
- 删除目录时：**级联删除关联的 Test Cases**（确认后执行）

## 2. 数据库设计

### 2.1 目录表（categories）

复用 `json-to-postgres-migration/doc.md` 中的设计：

```sql
-- 测试用例分类目录表（支持3级树形结构）
-- 采用邻接表 + 路径枚举组合方案
CREATE TABLE categories (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    parent_id VARCHAR(50) REFERENCES categories(id) ON DELETE CASCADE,
    path VARCHAR(500) NOT NULL,        -- 完整路径: "安全测试/提示词注入/直接攻击"
    level INTEGER NOT NULL DEFAULT 1,  -- 层级: 1, 2, 3
    sort_order INTEGER DEFAULT 0,      -- 同级排序
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_level CHECK (level >= 1 AND level <= 3)
);

-- 创建索引
CREATE INDEX idx_categories_parent ON categories(parent_id);
CREATE INDEX idx_categories_level ON categories(level);
CREATE INDEX idx_categories_path ON categories(path);
```

### 2.2 根目录定义

系统初始化时创建一个特殊的根目录节点：

```sql
INSERT INTO categories (id, name, parent_id, path, level, sort_order) 
VALUES ('root', '全部用例', NULL, '全部用例', 1, 0);
```

**说明**：
- `root` 是系统保留的根目录 ID
- 所有未分类的测试用例都归属于此节点
- 该节点不可删除、不可修改名称

### 2.3 测试用例表（test_cases）关联

```sql
-- 测试用例表中的目录关联字段
category_id VARCHAR(50) REFERENCES categories(id) ON DELETE CASCADE DEFAULT 'root'
```

**ON DELETE CASCADE**：删除目录时，关联的测试用例也会被删除。

## 3. SQLAlchemy 模型定义

### 3.1 Category 模型

```python
# app/models/category.py
from sqlalchemy import Column, String, Integer, ForeignKey, CheckConstraint, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Category(Base):
    __tablename__ = 'categories'
    
    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(String(50), ForeignKey('categories.id', ondelete='CASCADE'), nullable=True)
    path = Column(String(500), nullable=False)
    level = Column(Integer, nullable=False, default=1)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    parent = relationship('Category', remote_side=[id], backref='children')
    test_cases = relationship('TestCase', back_populates='category', cascade='all, delete-orphan')
    
    __table_args__ = (
        CheckConstraint('level >= 1 AND level <= 3', name='chk_level'),
    )
    
    @property
    def is_root(self):
        return self.id == 'root'
    
    def can_add_child(self):
        """检查是否可以添加子目录（不超过3级）"""
        return self.level < 3
```

### 3.2 TestCase 模型更新

```python
# 在 TestCase 模型中添加
category_id = Column(String(50), ForeignKey('categories.id', ondelete='CASCADE'), default='root')
category = relationship('Category', back_populates='test_cases')
```

## 4. 数据服务层

### 4.1 目录服务 (CategoryService)

```python
# app/services/category_service.py
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.category import Category
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
            # 顶级目录（level=1），挂在 root 下
            level = 1
            path = name
            parent_id = None  # 顶级目录 parent_id 为 None
        
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
        return category
    
    def update(self, cat_id: str, name: str) -> Category:
        """更新目录名称"""
        if cat_id == 'root':
            raise ValueError("根目录不可修改")
        
        category = self.db.query(Category).filter(Category.id == cat_id).first()
        if not category:
            raise ValueError("目录不存在")
        
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
        return category
    
    def delete(self, cat_id: str) -> int:
        """删除目录（级联删除关联的测试用例）"""
        if cat_id == 'root':
            raise ValueError("根目录不可删除")
        
        category = self.db.query(Category).filter(Category.id == cat_id).first()
        if not category:
            raise ValueError("目录不存在")
        
        # 统计将要删除的测试用例数量
        from app.models.test_case import TestCase
        affected_count = self.db.query(TestCase).filter(
            TestCase.category_id.in_(
                self.db.query(Category.id).filter(
                    (Category.id == cat_id) | (Category.path.like(f"{category.path}/%"))
                )
            )
        ).count()
        
        self.db.delete(category)  # CASCADE 会删除子目录和关联测试用例
        self.db.commit()
        
        return affected_count
    
    def get_case_count(self, cat_id: str) -> int:
        """获取目录下的测试用例数量（含子目录）"""
        category = self.db.query(Category).filter(Category.id == cat_id).first()
        if not category:
            return 0
        
        from app.models.test_case import TestCase
        return self.db.query(TestCase).filter(
            TestCase.category_id.in_(
                self.db.query(Category.id).filter(
                    (Category.id == cat_id) | (Category.path.like(f"{category.path}/%"))
                )
            )
        ).count()
```

## 5. 数据迁移处理

### 5.1 迁移脚本

```python
# scripts/migrate_categories.py

def migrate_test_cases_to_root(db: Session):
    """将现有测试用例迁移到根目录"""
    
    # 1. 确保根目录存在
    root = db.query(Category).filter(Category.id == 'root').first()
    if not root:
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
    
    # 2. 将所有 category_id 为 NULL 的测试用例设置为 'root'
    from app.models.test_case import TestCase
    db.query(TestCase).filter(TestCase.category_id == None).update(
        {'category_id': 'root'},
        synchronize_session=False
    )
    db.commit()
    
    print(f"Migration completed. All test cases assigned to root category.")
```

### 5.2 从 JSON 迁移时的处理

在 `json-to-postgres-migration` 的迁移脚本中，所有测试用例的 `category_id` 默认设为 `'root'`。

## 6. UI 设计与实现

### 6.1 页面布局

```
+------------------+----------------------------------------+
|   目录树面板     |              测试用例列表               |
|  (Sidebar 25%)   |              (Main 75%)                |
+------------------+----------------------------------------+
|  [+ 新建目录]    |  [筛选器] [标签] [API选择] [导入]      |
|                  |                                        |
|  📁 全部用例 (100)|  +------------------------------------+|
|    📁 安全测试   |  |        Data Editor Table          ||
|      📁 注入攻击 |  |                                    ||
|      📁 越狱测试 |  +------------------------------------+|
|    📁 功能测试   |                                        |
|      📁 问答     |                                        |
|      📁 总结     |                                        |
+------------------+----------------------------------------+
```

### 6.2 目录树组件

```python
# app/ui/components/category_tree.py
import streamlit as st
from app.services.category_service import CategoryService

def render_category_tree(db_session):
    """渲染目录树组件"""
    service = CategoryService(db_session)
    tree = service.get_tree()
    
    # 新建目录按钮
    if st.button("➕ 新建目录", use_container_width=True):
        st.session_state.show_create_dialog = True
    
    # 渲染树
    selected_id = st.session_state.get('selected_category', 'root')
    
    def render_node(node, indent=0):
        prefix = "　" * indent
        icon = "📁" if node['children'] else "📄"
        count = service.get_case_count(node['id'])
        
        col1, col2 = st.columns([4, 1])
        with col1:
            if st.button(f"{prefix}{icon} {node['name']} ({count})", 
                        key=f"cat_{node['id']}", 
                        use_container_width=True,
                        type="primary" if node['id'] == selected_id else "secondary"):
                st.session_state.selected_category = node['id']
                st.rerun()
        
        with col2:
            if node['id'] != 'root':
                with st.popover("⋯"):
                    if st.button("✏️ 重命名", key=f"rename_{node['id']}"):
                        st.session_state.rename_category = node['id']
                    if node['level'] < 3:
                        if st.button("➕ 添加子目录", key=f"addchild_{node['id']}"):
                            st.session_state.add_child_to = node['id']
                    if st.button("🗑️ 删除", key=f"delete_{node['id']}"):
                        st.session_state.delete_category = node['id']
        
        for child in node.get('children', []):
            render_node(child, indent + 1)
    
    for node in tree:
        render_node(node)
    
    return selected_id
```

### 6.3 对话框组件

```python
# app/ui/components/category_dialogs.py
import streamlit as st

@st.dialog("新建目录")
def create_category_dialog(service, parent_id=None):
    name = st.text_input("目录名称", max_chars=100)
    
    if parent_id:
        parent = service.db.query(Category).filter(Category.id == parent_id).first()
        st.info(f"将创建在: {parent.path}")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("取消", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("创建", type="primary", use_container_width=True):
            if name.strip():
                try:
                    service.create(name.strip(), parent_id)
                    st.toast(f"✅ 目录 '{name}' 创建成功!")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

@st.dialog("确认删除")
def delete_category_dialog(service, cat_id):
    category = service.db.query(Category).filter(Category.id == cat_id).first()
    count = service.get_case_count(cat_id)
    
    st.warning(f"确定要删除目录 **{category.name}** 吗？")
    if count > 0:
        st.error(f"⚠️ 这将同时删除该目录下的 **{count}** 个测试用例！此操作不可撤销！")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("取消", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("🗑️ 确认删除", type="primary", use_container_width=True):
            affected = service.delete(cat_id)
            st.toast(f"✅ 已删除目录及 {affected} 个测试用例")
            st.session_state.selected_category = 'root'
            st.rerun()

@st.dialog("重命名目录")
def rename_category_dialog(service, cat_id):
    category = service.db.query(Category).filter(Category.id == cat_id).first()
    name = st.text_input("新名称", value=category.name, max_chars=100)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("取消", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("保存", type="primary", use_container_width=True):
            if name.strip() and name.strip() != category.name:
                try:
                    service.update(cat_id, name.strip())
                    st.toast(f"✅ 目录已重命名为 '{name}'")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
```

### 6.4 testcases.py 页面改造

```python
# app/ui/testcases.py 主要修改点

def render_testcases_page():
    # ...existing code...
    
    # 创建两列布局：左侧目录树，右侧内容
    tree_col, content_col = st.columns([1, 3])
    
    with tree_col:
        st.markdown("### 📂 目录")
        from app.ui.components.category_tree import render_category_tree
        from app.database import get_db
        
        with get_db() as db:
            selected_category = render_category_tree(db)
            
            # 处理对话框状态
            if st.session_state.get('show_create_dialog'):
                create_category_dialog(CategoryService(db))
                st.session_state.show_create_dialog = False
            # ... 其他对话框处理
    
    with content_col:
        # 原有的测试用例列表内容
        # 但需要根据 selected_category 过滤数据
        
        # 修改数据加载逻辑
        if selected_category == 'root':
            # 显示所有用例
            df = load_data()
        else:
            # 显示该目录及子目录下的用例
            df = load_data_by_category(selected_category)
        
        # ...existing table and actions code...
```

## 7. 涉及修改的文件

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `app/models/category.py` | 新建 | Category 模型定义 |
| `app/models/test_case.py` | 修改 | 添加 category_id 字段 |
| `app/services/category_service.py` | 新建 | 目录 CRUD 服务 |
| `app/ui/testcases.py` | 修改 | 集成目录树，调整布局 |
| `app/ui/components/category_tree.py` | 新建 | 目录树组件 |
| `app/ui/components/category_dialogs.py` | 新建 | 增删改对话框组件 |
| `app/utils.py` | 修改 | 添加 `load_data_by_category()` 函数 |
| `scripts/migrate_categories.py` | 新建 | 数据迁移脚本 |

## 8. 验收标准

1. ✅ 数据库中存在 categories 表，约束 level <= 3
2. ✅ 根目录 (id='root') 存在且不可删除/修改
3. ✅ 所有现有测试用例的 category_id 默认为 'root'
4. ✅ UI 左侧显示目录树，可展开/折叠
5. ✅ 可创建、重命名、删除目录
6. ✅ 创建目录时，层级限制为 3 级
7. ✅ 删除目录时，提示将删除的测试用例数量，确认后级联删除
8. ✅ 点击目录可筛选显示该目录下的测试用例
