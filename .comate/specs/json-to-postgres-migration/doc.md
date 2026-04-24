# JSON 数据存储迁移到 PostgreSQL 方案

## 1. 需求背景

当前系统使用 JSON 文件存储所有数据，存在以下问题：
- 并发读写时可能出现数据冲突
- 数据量增长后查询性能下降
- 缺乏事务支持，数据一致性难以保证
- 无法进行复杂查询和数据分析
- **Tester 页面生成大量测试用例时，JSON 文件可能被截断导致出错**
- **Test Report 数据写入不完整导致页面崩溃**
- **未来需要支持多媒体内容（图片、音频）**

## 2. 迁移范围

### 2.1 需要迁移的数据文件

| 文件 | 用途 | 数据量 |
|------|------|--------|
| `data/test_cases.json` | 测试用例 | ~7800+ 条记录 |
| `data/history.json` | 测试执行历史 | ~950+ 行 |
| `data/blind_reviews.json` | 盲测评审 | ~160 行 |
| `data/api_config.json` | API 配置 | ~92 行 |
| `data/modules.json` | 模块/标签配置 | ~106 行 |

### 2.2 涉及修改的文件

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `app/utils.py` | 重写 | 核心数据操作函数迁移到数据库 |
| `app/ui/blind_review.py` | 重写 | 盲测评审数据操作 |
| `app/routers/cases.py` | 修改 | 调整数据加载/保存方式 |
| `requirements.txt` | 新增依赖 | 添加 psycopg2、sqlalchemy |
| `app/database.py` | 新建 | 数据库连接和模型定义 |
| `app/config.py` | 新建 | 数据库配置管理 |

## 3. 数据库设计

### 3.1 表结构设计

#### 3.1.1 目录分类系统（3级树形结构）

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

-- 示例数据:
-- id: 'safety', name: '安全测试', parent_id: NULL, path: '安全测试', level: 1
-- id: 'prompt_injection', name: '提示词注入', parent_id: 'safety', path: '安全测试/提示词注入', level: 2
-- id: 'direct_attack', name: '直接攻击', parent_id: 'prompt_injection', path: '安全测试/提示词注入/直接攻击', level: 3
```

#### 3.1.2 预定义标签表

```sql
-- 预定义标签表（扁平化设计，不区分分类）
CREATE TABLE tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,  -- 标签名称: P0, P1, Active, Draft, 安全测试 等
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 示例数据:
-- (1, 'P0', 0), (2, 'P1', 1), (3, 'P2', 2), (4, 'P3', 3)
-- (5, 'Active', 0), (6, 'Deprecated', 1), (7, 'Draft', 2)
-- (8, '安全测试', 0), (9, '功能测试', 1)
```

#### 3.1.3 测试用例表（关联分类和标签）

```sql
-- 测试用例表
CREATE TABLE test_cases (
    id VARCHAR(50) PRIMARY KEY,
    type VARCHAR(20) DEFAULT 'single',  -- single/multi_turn
    input TEXT NOT NULL,
    expected_output TEXT,
    retrieval_context TEXT,
    description TEXT,
    turn_index FLOAT,
    validation TEXT,
    overall_criteria TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 分类关联（可关联任意层级的目录）
    category_id VARCHAR(50) REFERENCES categories(id) ON DELETE SET NULL,
    
    -- 标签（JSONB 数组存储，直接引用 tags 表中的标签名）
    tags JSONB DEFAULT '[]'     -- ["P0", "Active", "安全测试"]
);

-- 测试用例-标签关联表（用于建立多对多关系，便于反向查询）
CREATE TABLE test_case_tags (
    test_case_id VARCHAR(50) REFERENCES test_cases(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (test_case_id, tag_id)
);
```

#### 3.1.4 测试历史和结果表

```sql
-- 测试历史表
CREATE TABLE test_history (
    id VARCHAR(50) PRIMARY KEY,  -- 时间戳ID: 20260408191741
    timestamp TIMESTAMP NOT NULL,
    api_name VARCHAR(100),
    total INTEGER DEFAULT 0,
    passed INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    started_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 测试结果表 (与 test_history 关联)
CREATE TABLE test_results (
    id SERIAL PRIMARY KEY,
    history_id VARCHAR(50) REFERENCES test_history(id) ON DELETE CASCADE,
    case_id VARCHAR(50),
    input TEXT,
    actual_output TEXT,
    expected_output TEXT,
    retrieval_context TEXT,
    score FLOAT,
    reason TEXT,
    faithfulness_score FLOAT,
    faithfulness_reason TEXT,
    passed BOOLEAN DEFAULT FALSE,
    thinking TEXT,
    inform_base TEXT,
    raw TEXT,
    latency FLOAT,
    ttft FLOAT,
    type VARCHAR(20),
    total_turns INTEGER,
    passed_turns INTEGER,
    success_rate FLOAT,
    overall_score FLOAT,
    overall_passed BOOLEAN,
    turns JSONB,  -- 多轮对话详情
    user_id VARCHAR(100),
    session_id VARCHAR(100)
);
```

#### 3.1.5 盲测评审表

```sql
-- 盲测评审表
CREATE TABLE blind_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 盲测评审项目表
CREATE TABLE blind_review_items (
    id SERIAL PRIMARY KEY,
    review_id UUID REFERENCES blind_reviews(id) ON DELETE CASCADE,
    input TEXT,
    options JSONB,  -- {"A": "回答A", "B": "回答B"}
    votes JSONB DEFAULT '{"A": 0, "B": 0}'
);
```

#### 3.1.6 API 配置表

```sql
-- API 配置表
CREATE TABLE api_configs (
    name VARCHAR(100) PRIMARY KEY,
    url TEXT NOT NULL,
    description TEXT,
    type VARCHAR(50)
);
```

#### 3.1.7 测试用例草稿表（Tester 页面临时存储）

解决 Tester 页面生成大量测试用例时 JSON 被截断的问题。使用独立的草稿表，支持逐条写入，避免一次性大批量操作。

```sql
-- 测试用例草稿表（临时存储 AI 生成的用例）
CREATE TABLE test_case_drafts (
    id SERIAL PRIMARY KEY,
    batch_id VARCHAR(50) NOT NULL,      -- 批次ID，用于标识一次生成任务
    case_data JSONB NOT NULL,           -- 单条用例数据
    status VARCHAR(20) DEFAULT 'pending', -- pending/confirmed/discarded
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 批次管理表
CREATE TABLE draft_batches (
    id VARCHAR(50) PRIMARY KEY,         -- 批次ID: UUID 或时间戳
    total_count INTEGER DEFAULT 0,      -- 预期总数
    current_count INTEGER DEFAULT 0,    -- 已写入数量
    status VARCHAR(20) DEFAULT 'generating', -- generating/completed/failed/confirmed
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_drafts_batch_id ON test_case_drafts(batch_id);
CREATE INDEX idx_drafts_status ON test_case_drafts(status);
```

**工作流程：**
1. 开始生成 → 创建 `draft_batches` 记录
2. AI 每生成一条用例 → 立即插入 `test_case_drafts`（单条事务，原子性保证）
3. 生成完成 → 更新批次状态为 `completed`
4. 用户确认 → 将草稿批量转移到 `test_cases` 表
5. 用户取消 → 删除该批次的所有草稿

#### 3.1.8 多媒体附件表（支持图片、音频）

支持 input、expected_output、actual_output、retrieval_context 字段包含多媒体内容。

```sql
-- 多媒体附件表
CREATE TABLE attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,     -- image/png, image/jpeg, audio/mp3, audio/wav
    mime_type VARCHAR(100),
    file_size INTEGER,                  -- 文件大小（字节）
    storage_path TEXT NOT NULL,         -- 文件存储路径或对象存储 key
    thumbnail_path TEXT,                -- 缩略图路径（图片用）
    duration FLOAT,                     -- 音频/视频时长（秒）
    metadata JSONB,                     -- 其他元数据（如图片尺寸、音频采样率等）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 测试用例内容表（存储富文本/多媒体内容）
-- 将原有的 TEXT 字段改为结构化内容
CREATE TABLE test_case_contents (
    id SERIAL PRIMARY KEY,
    test_case_id VARCHAR(50) REFERENCES test_cases(id) ON DELETE CASCADE,
    field_name VARCHAR(50) NOT NULL,    -- input/expected_output/retrieval_context
    content_type VARCHAR(20) NOT NULL,  -- text/image/audio/mixed
    text_content TEXT,                  -- 文本内容
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_case_id, field_name)
);

-- 内容-附件关联表（一个内容字段可包含多个附件）
CREATE TABLE content_attachments (
    id SERIAL PRIMARY KEY,
    content_id INTEGER REFERENCES test_case_contents(id) ON DELETE CASCADE,
    attachment_id UUID REFERENCES attachments(id) ON DELETE CASCADE,
    sort_order INTEGER DEFAULT 0,       -- 附件在内容中的顺序
    caption TEXT                        -- 附件说明/标题
);

-- 测试结果内容表（actual_output 的多媒体支持）
CREATE TABLE test_result_contents (
    id SERIAL PRIMARY KEY,
    result_id INTEGER REFERENCES test_results(id) ON DELETE CASCADE,
    field_name VARCHAR(50) NOT NULL,    -- actual_output/thinking 等
    content_type VARCHAR(20) NOT NULL,
    text_content TEXT,
    UNIQUE(result_id, field_name)
);

-- 结果内容-附件关联表
CREATE TABLE result_content_attachments (
    id SERIAL PRIMARY KEY,
    content_id INTEGER REFERENCES test_result_contents(id) ON DELETE CASCADE,
    attachment_id UUID REFERENCES attachments(id) ON DELETE CASCADE,
    sort_order INTEGER DEFAULT 0,
    caption TEXT
);

CREATE INDEX idx_attachments_file_type ON attachments(file_type);
CREATE INDEX idx_test_case_contents_case_id ON test_case_contents(test_case_id);
CREATE INDEX idx_result_contents_result_id ON test_result_contents(result_id);
```

**多媒体内容数据结构示例：**
```json
{
  "content_type": "mixed",
  "text_content": "请看下面这张图片，描述图中的内容：",
  "attachments": [
    {
      "id": "uuid-xxx",
      "type": "image/png",
      "url": "/uploads/images/xxx.png",
      "caption": "测试图片1"
    }
  ]
}
```

### 3.2 索引设计

```sql
-- 分类目录索引
CREATE INDEX idx_categories_parent_id ON categories(parent_id);
CREATE INDEX idx_categories_level ON categories(level);
CREATE INDEX idx_categories_path ON categories(path);

-- 测试用例索引
CREATE INDEX idx_test_cases_category_id ON test_cases(category_id);
CREATE INDEX idx_test_cases_type ON test_cases(type);
CREATE INDEX idx_test_cases_tags ON test_cases USING GIN(tags);

-- 测试历史索引
CREATE INDEX idx_test_history_timestamp ON test_history(timestamp DESC);
CREATE INDEX idx_test_history_api_name ON test_history(api_name);
CREATE INDEX idx_test_results_history_id ON test_results(history_id);
CREATE INDEX idx_test_results_case_id ON test_results(case_id);
```

### 3.3 分类目录常用查询

```sql
-- 获取完整目录树
SELECT * FROM categories ORDER BY path;

-- 获取某节点的所有子节点
SELECT * FROM categories WHERE path LIKE '安全测试/%';

-- 获取某节点的直接子节点
SELECT * FROM categories WHERE parent_id = 'safety';

-- 获取某目录下所有测试用例（包含子目录）
SELECT tc.* FROM test_cases tc
JOIN categories c ON tc.category_id = c.id
WHERE c.path LIKE '功能测试/机场助手%';

-- 获取某目录下直接的测试用例
SELECT * FROM test_cases WHERE category_id = 'lounge_query';

-- 按分类统计测试用例数量
SELECT c.path, COUNT(tc.id) as case_count
FROM categories c
LEFT JOIN test_cases tc ON tc.category_id = c.id
GROUP BY c.id, c.path
ORDER BY c.path;
```

## 4. 技术方案

### 4.1 依赖库
- `psycopg2-binary`: PostgreSQL 驱动
- `sqlalchemy`: ORM 框架
- `python-dotenv`: 环境变量管理

### 4.2 配置管理

使用环境变量配置数据库连接：
```
DATABASE_URL=postgresql://user:password@localhost:5432/chatbot_tester
```

### 4.3 数据库连接层 (`app/database.py`)

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### 4.4 核心函数迁移

#### load_data() 迁移
```python
def load_data(category_id: str = None) -> pd.DataFrame:
    """加载测试用例，支持按分类筛选"""
    with SessionLocal() as db:
        query = db.query(TestCase)
        
        if category_id:
            # 获取该分类及所有子分类的用例
            category = db.query(Category).filter(Category.id == category_id).first()
            if category:
                query = query.join(Category).filter(Category.path.like(f"{category.path}%"))
        
        cases = query.all()
        if not cases:
            return pd.DataFrame(columns=["Select", "id", "turn_index", "input", "expected_output", "tags", "category_path"])
        
        data = [case.to_dict() for case in cases]
        df = pd.DataFrame(data)
        df.insert(0, "Select", False)
        return df
```

#### save_data() 迁移
```python
def save_data(df: pd.DataFrame):
    to_save_df = df.drop(columns=["Select"], errors='ignore').copy()
    # ID 生成逻辑保持不变
    
    with SessionLocal() as db:
        for _, row in to_save_df.iterrows():
            existing = db.query(TestCase).filter(TestCase.id == row["id"]).first()
            if existing:
                # 更新现有记录
                for key, value in row.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
            else:
                # 插入新记录
                case = TestCase(**row.to_dict())
                db.add(case)
        db.commit()
    return to_save_df
```

#### save_history() 迁移
```python
def save_history(results: List[Dict], api_name: str = "Unknown"):
    with SessionLocal() as db:
        history_id = datetime.now().strftime("%Y%m%d%H%M%S")
        passed_count = sum(1 for r in results if r.get("passed", False))
        
        history = TestHistory(
            id=history_id,
            timestamp=datetime.now(),
            api_name=api_name,
            total=len(results),
            passed=passed_count,
            failed=len(results) - passed_count
        )
        db.add(history)
        
        for r in results:
            result = TestResult(history_id=history_id, **r)
            db.add(result)
        
        db.commit()
```

#### 分类目录操作函数（新增）
```python
def get_category_tree() -> List[Dict]:
    """获取完整的分类目录树"""
    with SessionLocal() as db:
        categories = db.query(Category).order_by(Category.path).all()
        
        # 构建树形结构
        tree = []
        lookup = {}
        
        for cat in categories:
            node = {"id": cat.id, "name": cat.name, "path": cat.path, "children": []}
            lookup[cat.id] = node
            
            if cat.parent_id is None:
                tree.append(node)
            else:
                parent = lookup.get(cat.parent_id)
                if parent:
                    parent["children"].append(node)
        
        return tree

def add_category(name: str, parent_id: str = None) -> Category:
    """添加新分类目录"""
    with SessionLocal() as db:
        parent = db.query(Category).filter(Category.id == parent_id).first() if parent_id else None
        
        if parent and parent.level >= 3:
            raise ValueError("最多支持3级目录")
        
        level = (parent.level + 1) if parent else 1
        path = f"{parent.path}/{name}" if parent else name
        cat_id = name.lower().replace(" ", "_")
        
        category = Category(id=cat_id, name=name, parent_id=parent_id, path=path, level=level)
        db.add(category)
        db.commit()
        return category

def move_test_case_to_category(case_id: str, category_id: str):
    """将测试用例移动到指定分类"""
    with SessionLocal() as db:
        case = db.query(TestCase).filter(TestCase.id == case_id).first()
        if case:
            case.category_id = category_id
            db.commit()
```

## 5. 数据迁移脚本

创建 `scripts/migrate_json_to_postgres.py` 用于将现有 JSON 数据导入数据库：

```python
import json
from app.database import SessionLocal
from app.models import Category, Tag, TestCase, TestHistory, TestResult, ...

def migrate_categories():
    """迁移 modules.json 中的分类目录（递归处理树形结构）"""
    with open("data/modules.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    def insert_category(node, parent_id=None, level=1):
        category = Category(
            id=node["id"],
            name=node["name"],
            parent_id=parent_id,
            path=node["path"],
            level=level
        )
        db.add(category)
        
        # 递归处理子节点
        for child in node.get("children", []):
            insert_category(child, parent_id=node["id"], level=level + 1)
    
    with SessionLocal() as db:
        for module in data["modules"]:
            insert_category(module, parent_id=None, level=1)
        db.commit()

def migrate_tags():
    """迁移 modules.json 中的预定义标签（扁平化）"""
    with open("data/modules.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    with SessionLocal() as db:
        sort_order = 0
        for category_name, tag_values in data.get("predefined_tags", {}).items():
            for tag_value in tag_values:
                # 检查是否已存在
                existing = db.query(Tag).filter(Tag.name == tag_value).first()
                if not existing:
                    tag = Tag(name=tag_value, sort_order=sort_order)
                    db.add(tag)
                    sort_order += 1
        db.commit()

def migrate_test_cases():
    """迁移测试用例"""
    with open("data/test_cases.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    with SessionLocal() as db:
        for item in data:
            # 查找对应的 category_id（根据 module 字段）
            category_id = None
            if item.get("module"):
                cat = db.query(Category).filter(Category.path == item["module"]).first()
                if cat:
                    category_id = cat.id
            
            # tags 直接保留原数组格式
            tags = item.get("tags", [])
            
            case = TestCase(
                id=item["id"],
                type=item.get("type", "single"),
                input=item["input"],
                expected_output=item.get("expected_output"),
                retrieval_context=item.get("retrieval_context"),
                description=item.get("description"),
                turn_index=item.get("turn_index"),
                validation=item.get("validation"),
                overall_criteria=item.get("overall_criteria"),
                category_id=category_id,
                tags=tags
            )
            db.add(case)
        db.commit()

def migrate_history():
    """迁移测试历史"""
    with open("data/history.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    with SessionLocal() as db:
        for entry in data:
            history = TestHistory(
                id=entry["id"],
                timestamp=entry["timestamp"],
                api_name=entry.get("api_name"),
                total=entry.get("total", 0),
                passed=entry.get("passed", 0),
                failed=entry.get("failed", 0),
                status=entry.get("status", "completed"),
                started_count=entry.get("started_count", 0)
            )
            db.add(history)
            
            for r in entry.get("results", []):
                result = TestResult(history_id=entry["id"], **r)
                db.add(result)
        db.commit()

def migrate_all():
    """执行全部迁移（顺序重要）"""
    print("1. 迁移分类目录...")
    migrate_categories()
    
    print("2. 迁移预定义标签...")
    migrate_tags()
    
    print("3. 迁移测试用例...")
    migrate_test_cases()
    
    print("4. 迁移测试历史...")
    migrate_history()
    
    print("5. 迁移盲测评审...")
    migrate_blind_reviews()
    
    print("6. 迁移API配置...")
    migrate_api_configs()
    
    print("迁移完成!")

if __name__ == "__main__":
    migrate_all()
```

## 6. Tester 页面测试用例生成方案

### 6.1 问题分析
当前 JSON 方式在生成大量测试用例时，一次性写入可能导致：
- 文件被截断（写入中断）
- 内存溢出
- 进度丢失

### 6.2 解决方案：逐条写入 + 批次管理

```python
import uuid
from app.database import SessionLocal
from app.models import DraftBatch, TestCaseDraft

def start_generation_batch(expected_count: int = None) -> str:
    """开始一个新的生成批次"""
    batch_id = str(uuid.uuid4())[:8]
    with SessionLocal() as db:
        batch = DraftBatch(
            id=batch_id,
            total_count=expected_count or 0,
            status='generating'
        )
        db.add(batch)
        db.commit()
    return batch_id

def save_draft_case(batch_id: str, case_data: dict):
    """保存单条草稿用例（每条独立事务，保证原子性）"""
    with SessionLocal() as db:
        draft = TestCaseDraft(
            batch_id=batch_id,
            case_data=case_data,
            status='pending'
        )
        db.add(draft)
        
        # 更新批次计数
        batch = db.query(DraftBatch).filter(DraftBatch.id == batch_id).first()
        if batch:
            batch.current_count += 1
        
        db.commit()  # 单条提交，失败不影响其他记录

def complete_batch(batch_id: str, success: bool = True, error_msg: str = None):
    """完成生成批次"""
    with SessionLocal() as db:
        batch = db.query(DraftBatch).filter(DraftBatch.id == batch_id).first()
        if batch:
            batch.status = 'completed' if success else 'failed'
            batch.error_message = error_msg
            batch.completed_at = datetime.now()
            db.commit()

def confirm_drafts(batch_id: str) -> int:
    """确认草稿，批量转移到正式表"""
    with SessionLocal() as db:
        drafts = db.query(TestCaseDraft).filter(
            TestCaseDraft.batch_id == batch_id,
            TestCaseDraft.status == 'pending'
        ).all()
        
        count = 0
        for draft in drafts:
            case = TestCase(**draft.case_data)
            db.add(case)
            draft.status = 'confirmed'
            count += 1
        
        db.commit()
        return count

def discard_drafts(batch_id: str):
    """丢弃草稿"""
    with SessionLocal() as db:
        db.query(TestCaseDraft).filter(TestCaseDraft.batch_id == batch_id).delete()
        db.query(DraftBatch).filter(DraftBatch.id == batch_id).delete()
        db.commit()
```

### 6.3 前端交互流程
1. 点击"生成" → 调用 `start_generation_batch()`
2. AI 流式返回 → 每解析出一条用例调用 `save_draft_case()`
3. 页面实时显示已生成数量和内容预览
4. 生成完成 → 用户可预览、编辑草稿
5. 点击"确认导入" → 调用 `confirm_drafts()` 批量写入正式表
6. 点击"取消" → 调用 `discard_drafts()` 清理草稿

## 7. Test Report 数据原子性保证

### 7.1 问题分析
测试结果写入不完整导致：
- history.json 格式损坏
- 页面加载崩溃
- 数据丢失

### 7.2 解决方案：逐条写入 + 实时可见

**核心原则：每执行完一条用例，立即写入数据库并可在页面实时查看。**

```python
def create_test_history(api_name: str, total_cases: int) -> str:
    """创建测试历史记录，立即可见"""
    history_id = datetime.now().strftime("%Y%m%d%H%M%S")
    with SessionLocal() as db:
        history = TestHistory(
            id=history_id,
            timestamp=datetime.now(),
            api_name=api_name,
            total=total_cases,
            passed=0,
            failed=0,
            status='running',
            started_count=0
        )
        db.add(history)
        db.commit()
    return history_id

def save_test_result_atomic(history_id: str, result: dict):
    """
    原子性保存单条测试结果
    - 每条结果独立事务，立即提交
    - 写入成功即可在页面看到
    - 单条失败不影响其他结果
    """
    with SessionLocal() as db:
        try:
            test_result = TestResult(history_id=history_id, **result)
            db.add(test_result)
            
            # 同步更新 history 统计（同一事务内）
            history = db.query(TestHistory).filter(TestHistory.id == history_id).first()
            if history:
                history.started_count += 1
                if result.get('passed'):
                    history.passed += 1
                else:
                    history.failed += 1
            
            db.commit()  # 立即提交，页面刷新即可看到
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"保存测试结果失败: {e}")
            return False

def finalize_test_history(history_id: str, status: str = 'completed'):
    """测试结束，更新最终状态"""
    with SessionLocal() as db:
        history = db.query(TestHistory).filter(TestHistory.id == history_id).first()
        if history:
            history.status = status
            db.commit()
```

### 7.3 状态机设计

```
TestHistory.status:
  running → completed
         ↘ failed
         ↘ cancelled
```

- **running**: 测试执行中（页面显示进度：已完成 X / 总数 Y）
- **completed**: 全部完成
- **failed**: 执行过程出错中断
- **cancelled**: 用户取消

### 7.4 页面实时显示

**页面支持所有状态的报告查看：**

| 状态 | 页面显示 |
|------|----------|
| running | 显示已完成的结果 + 进度条（X/Y），自动刷新 |
| completed | 显示完整报告 |
| failed | 显示已完成的结果 + 错误提示 |
| cancelled | 显示已完成的结果 + 取消提示 |

```python
def get_test_report(history_id: str) -> dict:
    """获取测试报告（支持实时查看进行中的报告）"""
    with SessionLocal() as db:
        history = db.query(TestHistory).filter(TestHistory.id == history_id).first()
        if not history:
            return None
        
        results = db.query(TestResult).filter(
            TestResult.history_id == history_id
        ).order_by(TestResult.id).all()
        
        return {
            "id": history.id,
            "timestamp": history.timestamp,
            "api_name": history.api_name,
            "total": history.total,
            "passed": history.passed,
            "failed": history.failed,
            "started_count": history.started_count,
            "status": history.status,
            "progress": f"{history.started_count}/{history.total}",
            "results": [r.to_dict() for r in results]  # 返回已有的所有结果
        }
```

### 7.5 数据完整性保证

- **每条结果独立事务**：单条写入失败不影响已写入的数据
- **history 和 result 同事务**：统计数据始终准确
- **无 JSON 截断风险**：数据库保证写入要么成功要么回滚
- **断点恢复**：running 状态的报告可继续执行或标记为 failed

## 8. 数据迁移与合并方案

### 8.1 迁移策略概述

**场景：**
- 本地环境有一套 JSON 数据
- 服务器环境有一套 JSON 数据
- 两套数据需要分别迁移到 PostgreSQL，并支持后续合并

**迁移原则：**
1. 迁移前备份原始 JSON 文件
2. 迁移过程可中断、可恢复
3. 迁移后校验数据完整性
4. 支持增量迁移和全量迁移

### 8.2 测试用例去重策略

**去重规则：input（问题）相同即为同一条测试用例**

```sql
-- 添加 input 哈希字段用于快速去重
ALTER TABLE test_cases ADD COLUMN input_hash VARCHAR(64);

-- 哈希计算方式：仅基于 input 字段
-- hash = SHA256(input)
```

```python
import hashlib

def compute_input_hash(case: dict) -> str:
    """计算测试用例 input 哈希（用于去重判断）"""
    input_text = str(case.get("input", "")).strip()
    return hashlib.sha256(input_text.encode('utf-8')).hexdigest()
```

**去重策略选项：**
| 策略 | 说明 |
|------|------|
| 保留本地 | 相同 input 保留本地版本，跳过服务器版本 |
| 保留服务器 | 相同 input 保留服务器版本，跳过本地版本 |
| 保留最新 | 根据 created_at/updated_at 保留最新版本 |
| 合并字段 | 相同 input 时，合并两边的其他字段（如标签、分类等） |

### 8.3 测试报告合并策略

**测试报告不去重，全部保留。**

- 不同环境的测试报告独立存储
- 可通过 `source` 字段区分来源

```sql
-- 测试历史表增加来源字段
ALTER TABLE test_history ADD COLUMN source VARCHAR(50) DEFAULT 'local';
-- source: 'local', 'server', 'merged' 等
```

### 8.4 迁移脚本增强

```python
# scripts/migrate_json_to_postgres.py

import json
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from app.database import SessionLocal
from app.models import TestCase, TestHistory, ...

class DataMigrator:
    def __init__(self, data_dir: str, backup_dir: str = None):
        self.data_dir = Path(data_dir)
        self.backup_dir = Path(backup_dir or f"{data_dir}_backup_{datetime.now().strftime('%Y%m%d%H%M%S')}")
        self.migration_log = []
        
    def backup_json_files(self):
        """迁移前备份所有 JSON 文件"""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        json_files = [
            "test_cases.json",
            "history.json", 
            "blind_reviews.json",
            "api_config.json",
            "modules.json"
        ]
        
        for f in json_files:
            src = self.data_dir / f
            if src.exists():
                shutil.copy2(src, self.backup_dir / f)
                self.log(f"备份: {f} -> {self.backup_dir / f}")
        
        return self.backup_dir
    
    def log(self, message: str):
        """记录迁移日志"""
        entry = f"[{datetime.now().isoformat()}] {message}"
        self.migration_log.append(entry)
        print(entry)
    
    def migrate_test_cases(self, dedup: bool = True) -> dict:
        """
        迁移测试用例
        返回: {"total": 总数, "migrated": 迁移数, "skipped": 跳过数, "errors": 错误数}
        """
        stats = {"total": 0, "migrated": 0, "skipped": 0, "errors": 0}
        
        json_path = self.data_dir / "test_cases.json"
        if not json_path.exists():
            self.log(f"文件不存在: {json_path}")
            return stats
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        stats["total"] = len(data)
        
        with SessionLocal() as db:
            for i, item in enumerate(data):
                try:
                    input_hash = compute_input_hash(item)
                    
                    # 去重检查（基于 input 相同）
                    if dedup:
                        existing = db.query(TestCase).filter(
                            TestCase.input_hash == input_hash
                        ).first()
                        
                        if existing:
                            self.log(f"跳过重复用例: {item.get('id')} (input相同, hash={input_hash[:8]}...)")
                            stats["skipped"] += 1
                            continue
                    
                    # 处理 ID 冲突
                    case_id = item.get("id", f"TC{i+1:04d}")
                    id_conflict = db.query(TestCase).filter(TestCase.id == case_id).first()
                    if id_conflict:
                        # 生成新 ID
                        case_id = f"{case_id}_{datetime.now().strftime('%H%M%S')}"
                    
                    case = TestCase(
                        id=case_id,
                        type=item.get("type", "single"),
                        input=item.get("input", ""),
                        expected_output=item.get("expected_output"),
                        retrieval_context=item.get("retrieval_context"),
                        description=item.get("description"),
                        turn_index=item.get("turn_index"),
                        validation=item.get("validation"),
                        overall_criteria=item.get("overall_criteria"),
                        tags=item.get("tags", []),
                        input_hash=input_hash
                    )
                    db.add(case)
                    stats["migrated"] += 1
                    
                    # 每 100 条提交一次，避免内存溢出
                    if stats["migrated"] % 100 == 0:
                        db.commit()
                        self.log(f"已迁移 {stats['migrated']} 条...")
                        
                except Exception as e:
                    self.log(f"迁移失败 [{item.get('id')}]: {e}")
                    stats["errors"] += 1
            
            db.commit()
        
        self.log(f"测试用例迁移完成: 总数={stats['total']}, 迁移={stats['migrated']}, 跳过={stats['skipped']}, 错误={stats['errors']}")
        return stats
    
    def verify_migration(self) -> dict:
        """校验迁移数据完整性"""
        results = {}
        
        # 校验测试用例
        with open(self.data_dir / "test_cases.json", "r", encoding="utf-8") as f:
            json_count = len(json.load(f))
        
        with SessionLocal() as db:
            db_count = db.query(TestCase).count()
        
        results["test_cases"] = {
            "json_count": json_count,
            "db_count": db_count,
            "match": json_count == db_count  # 如果有去重则不一定相等
        }
        
        # 校验其他表...
        
        return results
    
    def save_migration_log(self):
        """保存迁移日志"""
        log_path = self.backup_dir / "migration.log"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.migration_log))
        return log_path

def migrate_local(data_dir: str = "data"):
    """迁移本地数据"""
    migrator = DataMigrator(data_dir)
    migrator.backup_json_files()
    migrator.migrate_categories()
    migrator.migrate_tags()
    migrator.migrate_test_cases(dedup=True)
    migrator.migrate_history()
    migrator.migrate_blind_reviews()
    migrator.migrate_api_configs()
    migrator.verify_migration()
    migrator.save_migration_log()
```

### 8.5 多环境数据合并

```python
# scripts/merge_data.py

class DataMerger:
    def __init__(self, case_strategy: str = "keep_local"):
        """
        case_strategy (测试用例合并策略): 
          - keep_local: 相同 input 保留本地版本
          - keep_remote: 相同 input 保留服务器版本
          - keep_newest: 保留最新版本
          - merge_fields: 合并两边的标签、分类等字段
        
        测试报告：全部保留，不去重
        """
        self.case_strategy = case_strategy
        self.merge_log = []
    
    def merge_test_cases_from_json(self, json_path: str, source_name: str = "remote") -> dict:
        """
        合并测试用例（基于 input 去重）
        """
        stats = {"total": 0, "added": 0, "skipped": 0, "updated": 0, "errors": 0}
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        stats["total"] = len(data)
        
        with SessionLocal() as db:
            for item in data:
                try:
                    input_hash = compute_input_hash(item)
                    existing = db.query(TestCase).filter(
                        TestCase.input_hash == input_hash
                    ).first()
                    
                    if existing:
                        # 相同 input，处理重复
                        if self.case_strategy == "keep_local":
                            stats["skipped"] += 1
                            continue
                        elif self.case_strategy == "keep_remote":
                            # 更新为远程版本（保留本地 ID）
                            for key, value in item.items():
                                if hasattr(existing, key) and key not in ["id", "input_hash"]:
                                    setattr(existing, key, value)
                            stats["updated"] += 1
                        elif self.case_strategy == "keep_newest":
                            remote_time = item.get("updated_at") or item.get("created_at")
                            local_time = existing.updated_at or existing.created_at
                            if remote_time and local_time and remote_time > str(local_time):
                                for key, value in item.items():
                                    if hasattr(existing, key) and key not in ["id", "input_hash"]:
                                        setattr(existing, key, value)
                                stats["updated"] += 1
                            else:
                                stats["skipped"] += 1
                        elif self.case_strategy == "merge_fields":
                            # 合并标签
                            local_tags = set(existing.tags or [])
                            remote_tags = set(item.get("tags", []))
                            existing.tags = list(local_tags | remote_tags)
                            # 如果本地无分类，使用远程分类
                            if not existing.category_id and item.get("category_id"):
                                existing.category_id = item["category_id"]
                            stats["updated"] += 1
                    else:
                        # 新增
                        case = TestCase(
                            **item,
                            input_hash=input_hash
                        )
                        db.add(case)
                        stats["added"] += 1
                        
                except Exception as e:
                    self.merge_log.append(f"合并失败 [{item.get('id')}]: {e}")
                    stats["errors"] += 1
            
            db.commit()
        
        return stats
    
    def merge_test_history_from_json(self, json_path: str, source_name: str = "server") -> dict:
        """
        合并测试报告（全部保留，不去重）
        """
        stats = {"total": 0, "added": 0, "errors": 0}
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        stats["total"] = len(data)
        
        with SessionLocal() as db:
            for entry in data:
                try:
                    # 检查 ID 冲突，冲突则生成新 ID
                    history_id = entry["id"]
                    if db.query(TestHistory).filter(TestHistory.id == history_id).first():
                        history_id = f"{history_id}_{source_name}"
                    
                    history = TestHistory(
                        id=history_id,
                        timestamp=entry["timestamp"],
                        api_name=entry.get("api_name"),
                        total=entry.get("total", 0),
                        passed=entry.get("passed", 0),
                        failed=entry.get("failed", 0),
                        status=entry.get("status", "completed"),
                        source=source_name  # 标记来源
                    )
                    db.add(history)
                    
                    # 保存所有结果
                    for r in entry.get("results", []):
                        result = TestResult(history_id=history_id, **r)
                        db.add(result)
                    
                    stats["added"] += 1
                    
                except Exception as e:
                    self.merge_log.append(f"合并报告失败 [{entry.get('id')}]: {e}")
                    stats["errors"] += 1
            
            db.commit()
        
        return stats
    
    def export_to_json(self, output_path: str, data_type: str = "test_cases"):
        """导出数据库数据到 JSON"""
        with SessionLocal() as db:
            if data_type == "test_cases":
                items = db.query(TestCase).all()
            elif data_type == "history":
                items = db.query(TestHistory).all()
            else:
                raise ValueError(f"Unknown data_type: {data_type}")
            
            data = [item.to_dict() for item in items]
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return len(data)

# 使用示例
def merge_server_data():
    """合并服务器数据到本地"""
    merger = DataMerger(case_strategy="keep_local")
    
    # 1. 合并测试用例（去重）
    case_stats = merger.merge_test_cases_from_json(
        json_path="server_export/test_cases.json",
        source_name="server"
    )
    print(f"测试用例合并: 总数={case_stats['total']}, 新增={case_stats['added']}, 跳过={case_stats['skipped']}")
    
    # 2. 合并测试报告（全部保留）
    history_stats = merger.merge_test_history_from_json(
        json_path="server_export/history.json",
        source_name="server"
    )
    print(f"测试报告合并: 总数={history_stats['total']}, 新增={history_stats['added']}")
```

### 8.6 迁移检查清单

| 步骤 | 操作 | 检查点 |
|------|------|--------|
| 1 | 备份 JSON 文件 | 备份目录存在，文件完整 |
| 2 | 创建数据库表 | 所有表创建成功 |
| 3 | 迁移分类目录 | categories 表记录数正确 |
| 4 | 迁移标签 | tags 表记录数正确 |
| 5 | 迁移测试用例 | test_cases 记录数 + 去重数 = JSON 记录数 |
| 6 | 迁移测试历史 | test_history 和 test_results 记录数正确 |
| 7 | 迁移盲测评审 | blind_reviews 记录数正确 |
| 8 | 迁移 API 配置 | api_configs 记录数正确 |
| 9 | 功能验证 | UI 页面正常显示、CRUD 操作正常 |
| 10 | 保存迁移日志 | migration.log 文件完整 |

### 8.7 回滚方案

如迁移出现问题，可通过备份恢复：

```bash
# 恢复 JSON 文件
cp -r data_backup_20260414120000/* data/

# 清空数据库表（谨慎操作）
psql -d chatbot_tester -c "TRUNCATE test_cases, test_history, test_results, ... CASCADE;"
```

## 9. 边界条件和异常处理

- 数据库连接失败时，记录错误日志并返回空数据/抛出友好错误
- 事务回滚：写操作失败时自动回滚
- 连接池管理：使用 SQLAlchemy 连接池，避免连接泄漏
- 向后兼容：保留 JSON 文件作为备份，迁移期间可回退
- **草稿清理**：定期清理超过 24 小时未确认的草稿
- **文件上传**：限制单文件大小（如 10MB），支持的格式白名单
- **迁移中断恢复**：基于 content_hash 去重，支持重复执行迁移脚本

## 10. 预期结果

- 所有数据存储迁移到 PostgreSQL
- API 和 UI 功能保持不变
- 支持并发访问，数据一致性提升
- 查询性能提升，支持复杂查询
- **Tester 页面生成大量用例时不再出错，支持断点续传**
- **Test Report 数据写入原子性保证，页面不再崩溃**
- **支持图片、音频等多媒体内容作为测试输入/输出**
- **3 级树形目录分类管理测试用例**
