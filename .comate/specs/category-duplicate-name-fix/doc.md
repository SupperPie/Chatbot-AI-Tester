# 同名分类节点保存错位修复

## 现象

分类树中存在两个同名节点（例如两处"转人工"，分别属于不同父节点）。用户在保存/导入测试用例时选择其中一个，但用例被保存到了另一个分支下。

## 根因

DB 层没有问题——`test_cases.category_id` 引用 `categories.id`（唯一），保存路径正确。

问题在 UI 层的下拉框构造：

`app/ui/components/category_selector.py:get_category_options` (第 7-30 行)：
```python
def flatten_tree(nodes, prefix=""):
    for node in nodes:
        indent = "　" * (node['level'] - 1)
        display_name = f"{indent}{node['name']}"    # ← 只用 name + 缩进
        options.append((node['id'], display_name))
```

- 同层级、同名的两个节点在下拉里显示完全相同，用户视觉上无法区分
- Streamlit `selectbox` 通过 `format_func` 依赖 label 展示，用户实际点到的可能是 list 中先出现的那个
- 因此看起来"存到了错误的节点下"

同文件 `render_category_selector` (第 44-68 行) 还存在潜在缺陷：
```python
selected_index = option_names.index(selected_name)  # 同名 label 只返回第一个
selected_id = option_ids[selected_index]
```
此函数目前 save 流程未直接调用，但为避免未来踩坑一并修复。

## 修改方案

### 影响文件

- `/Users/duyufei/Documents/Workspace_Sophy/AI_Test/chatbot-ai-tester/app/ui/components/category_selector.py`

### 改动 1：`get_category_options` 显示改用完整 path

```python
def flatten_tree(nodes, prefix=""):
    for node in nodes:
        # 用完整 path，避免同名不同父节点在下拉中不可区分
        display_name = f"📁 {node['path']}"
        options.append((node['id'], display_name))
        if node.get('children'):
            flatten_tree(node['children'])
```

优点：
- 显示 `分类A/转人工` 与 `分类B/转人工`，完全消歧
- 与 `move_to_category_dialog`（`testcases.py:263-326`）保持一致

### 改动 2：`render_category_selector` 通过 id 而非 label 匹配（防御性）

利用 `st.selectbox` 的 `options=option_ids` + `format_func` 直接返回 id，避免通过 label 反查 index：

```python
def render_category_selector(...):
    cat_opts = get_category_options()  # [(id, label)]
    option_ids = [c[0] for c in cat_opts]
    id_to_label = {c[0]: c[1] for c in cat_opts}
    selected_id = st.selectbox(
        label,
        options=option_ids,
        format_func=lambda x: id_to_label.get(x, x),
        key=key,
    )
    return selected_id
```

## 影响面

- 使用 `get_category_options()` 的两个 save 入口自动修复：
  - `app/ui/tester.py:206-268`（保存生成用例）
  - `app/ui/testcases.py:404-414, 480-593`（导入 CSV/JSON）
- 不改动 DB / Service / 分类树渲染逻辑

## 边界与验证

- 分类不同层级都能显示完整 path
- 长 path 在下拉里不会异常截断（Streamlit 自身处理）
- 同名节点视觉可区分，选择后 `category_id` 与用户预期匹配

## 不改动

- `Category` / `TestCase` 模型
- `CategoryService.get_tree`
- 侧边栏 `category_widget.py`（已用 id 索引）
- 移动对话框（已用 path）
