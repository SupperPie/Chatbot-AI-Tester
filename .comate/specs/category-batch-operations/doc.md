# 测试用例多维度筛选与批量操作优化

## 1. 需求背景

### 1.1 当前痛点
1. **筛选能力不足**：仅支持标签筛选，缺少目录筛选、ID范围筛选
2. **批量操作不便**：需要逐个勾选用例，无法按条件批量选择
3. **导入无目录选项**：Import 导入时无法指定目标目录

### 1.2 目标
构建多维度筛选 + 批量操作的测试用例管理界面，提升用例查找效率与管理便捷性

## 2. 功能设计

### 2.1 多维度筛选功能

| 筛选类型 | 控件 | 说明 |
|---------|------|------|
| 目录筛选 | 下拉选择 | 选择目录，显示该目录及子目录下的用例 |
| 标签筛选 | 多选下拉 | 选择标签，筛选包含任一标签的用例 |
| ID范围筛选 | 两个输入框 | From TC / To TC，支持范围查询 |
| 关键词搜索 | 文本输入 | 搜索 input 字段包含关键词的用例 |

#### UI 布局
```
┌─────────────────────────────────────────────────────────────────────┐
│ 🔍 筛选区                                                           │
│ [📂目录▼] [🏷️标签▼] [From TC___] [To TC___] [🔎关键词...]          │
├─────────────────────────────────────────────────────────────────────┤
│ ☑ 全选当前页  │ 已选: 25 条  │ [▶执行] [📂移动] [🗑️删除]          │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 用例选择机制

1. **单选**：点击行首复选框选中单条用例
2. **多选**：连续点击多个复选框
3. **全选当前页**：一键选中当前分页的所有用例
4. **选中计数**：实时显示已选中数量

### 2.3 批量操作功能

| 操作 | 触发条件 | 确认机制 | 说明 |
|------|---------|---------|------|
| 执行 | 选中≥1条 | 无需确认 | 对选中用例发起测试执行 |
| 移动 | 选中≥1条 | 弹窗选择目标目录 | 将用例移动到指定目录 |
| 删除 | 选中≥1条 | 二次确认弹窗 | 删除选中的用例 |

### 2.4 涉及文件

| 文件 | 修改类型 | 说明 |
|------|---------|------|
| `app/ui/testcases.py` | 修改 | 主页面，添加筛选控件、批量操作 |
| `app/ui/components/category_selector.py` | 新建 | 通用目录选择器组件 |
| `app/services/test_case_service.py` | 新建 | 测试用例 CRUD 服务层 |

### 2.5 导入时指定目录

在 Import 对话框中添加目标目录选择：

```
┌──────────────────────────────────────┐
│ ### Import Test Cases                │
│ 📂 目标目录: [选择目录 ▼]            │
│ 📄 Download Template                 │
│ ─────────────────────────────        │
│ 📤 上传文件 (CSV/JSON)               │
│ ☑ Update existing by ID             │
│ [Confirm Import]                     │
└──────────────────────────────────────┘
```

### 2.6 新建用例时指定目录

新增"➕新建"按钮，弹出对话框创建用例：

```
┌──────────────────────────────────────┐
│ ### 新建测试用例                      │
│ 📂 所属目录: [选择目录 ▼]            │
│ 📝 输入(input): [________________]   │
│ 📋 期望输出: [________________]      │
│ 🏷️ 标签: [多选 ▼]                   │
│ [取消] [✅ 创建]                     │
└──────────────────────────────────────┘
```

## 3. 核心代码逻辑

### 3.1 筛选逻辑 (Python)

```python
def filter_test_cases(df, category_id=None, tags=None, id_from=None, id_to=None, keyword=None):
    """多维度筛选测试用例"""
    filtered = df.copy()
    
    # 目录筛选（含子目录）
    if category_id and category_id != 'all':
        category_ids = get_category_ids_with_children(category_id)
        filtered = filtered[filtered['category_id'].isin(category_ids)]
    
    # 标签筛选（OR 逻辑）
    if tags:
        mask = filtered['tags'].apply(lambda t: any(tag in t for tag in tags) if isinstance(t, list) else False)
        filtered = filtered[mask]
    
    # ID 范围筛选
    if id_from:
        filtered = filtered[filtered['id'] >= id_from]
    if id_to:
        filtered = filtered[filtered['id'] <= id_to]
    
    # 关键词搜索
    if keyword:
        filtered = filtered[filtered['input'].str.contains(keyword, case=False, na=False)]
    
    return filtered
```

### 3.2 批量操作数据流

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ 筛选用例    │ ──▶ │ 选中用例    │ ──▶ │ 批量操作    │
└─────────────┘     └─────────────┘     └─────────────┘
                           │                   │
                           ▼                   ▼
                    ┌─────────────┐     ┌─────────────┐
                    │ session_    │     │ PostgreSQL  │
                    │ state.df    │ ◀── │ UPDATE      │
                    └─────────────┘     └─────────────┘
```

## 4. 实现细节

### 4.1 目录选择器组件复用

创建通用目录选择器组件供多处复用：

```python
# app/ui/components/category_selector.py

def render_category_selector(key: str, label: str = "选择目录", include_root: bool = True) -> str:
    """渲染目录选择下拉框，返回选中的 category_id"""
    from app.services.category_service import CategoryService
    from app.database import SessionLocal
    
    db = SessionLocal()
    service = CategoryService(db)
    tree = service.get_tree()
    db.close()
    
    options = []
    def build_options(nodes):
        for node in nodes:
            indent = "　" * (node['level'] - 1)
            options.append((node['id'], f"{indent}📁 {node['name']}"))
            if node.get('children'):
                build_options(node['children'])
    build_options(tree)
    
    if not options:
        return 'root'
    
    return st.selectbox(
        label,
        options=[o[0] for o in options],
        format_func=lambda x: next((o[1] for o in options if o[0] == x), x),
        key=key
    )
```

### 4.2 筛选逻辑

```python
def filter_dataframe(df, category_id=None, tags=None, keyword=None):
    """根据条件筛选 DataFrame"""
    filtered = df.copy()
    
    # 按目录筛选
    if category_id and category_id != 'root':
        # 获取目录及其子目录的所有 ID
        category_ids = get_category_ids_with_children(category_id)
        filtered = filtered[filtered['category_id'].isin(category_ids)]
    
    # 按标签筛选
    if tags:
        def has_tag(row_tags):
            if not isinstance(row_tags, list):
                return False
            return any(t in row_tags for t in tags)
        filtered = filtered[filtered['tags'].apply(has_tag)]
    
    # 按关键词筛选
    if keyword:
        mask = filtered['input'].str.contains(keyword, case=False, na=False)
        filtered = filtered[mask]
    
    return filtered
```

## 5. UI 布局调整

### 调整后的 testcases.py 布局

```
┌─────────────────────────────────────────────────────────────────────┐
│ 📋 Test Cases Management                                            │
├─────────────────────────────────────────────────────────────────────┤
│ [API▼] [Tags▼] [📂Move] [🗑️Delete] [➕New] [📤Import]              │
├─────────────────────────────────────────────────────────────────────┤
│ 筛选: [目录▼] [标签▼] [关键词...] │ ☑全选当前页 │ 已选: 5条        │
├─────────────────────────────────────────────────────────────────────┤
│ ☑ │ ID     │ Input          │ Expected    │ Tags     │ Category   │
│ ☐ │ TC001  │ 测试问题1      │ 期望回答    │ [F1]     │ 机场礼遇   │
│ ☑ │ TC002  │ 测试问题2      │ 期望回答    │ [Safety] │ AI_Lab     │
│ ...                                                                 │
├─────────────────────────────────────────────────────────────────────┤
│ ⬅️上一页  [1/28]  下一页➡️  │ 共28页，总计707条                    │
└─────────────────────────────────────────────────────────────────────┘
```

## 6. 边界条件处理

1. **空目录处理**：筛选结果为空时显示提示
2. **移动到当前目录**：检测并提示"已在该目录下"
3. **数据库连接失败**：graceful degradation，显示警告但不影响其他功能
4. **大批量操作**：显示进度条，分批提交数据库

## 7. 预期成果

1. 用户可通过筛选条件快速定位目标用例
2. 一键全选当前页，批量移动到指定目录
3. 导入测试用例时可选择目标目录
4. 新建用例时可直接指定所属目录
