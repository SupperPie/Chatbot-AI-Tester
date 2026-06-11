# Summary: 意图驱动测试用例生成

## 完成内容

### 新增文件
| 文件 | 用途 |
|---|---|
| `app/ui/prompts/__init__.py` | 包初始化 |
| `app/ui/prompts/intent_prompts.py` | Prompt 模板、意图常量、构造函数 |

### 修改文件
| 文件 | 改动 |
|---|---|
| `app/ui/tester.py` | 新增意图下拉组件 + 自动填充回调 + 调用 `build_prompt` 替换内联 prompt + 生成后注入 intent tags |

## 功能验证结果
- `intent_prompts.py` 模块导入成功
- 三种意图对应的 prompt 构建逻辑正确：
  - 默认：纯 schema 约束，无额外片段
  - 咨询意图：注入"产品信息咨询"子 prompt
  - 购买意图：注入 AIDA 分层 + 购买信号词 + 商品特性命中 + Few-shot 占位
- `tester.py` 语法验证通过
- 多轮对话 ID 共享逻辑未受影响

## 使用方式
1. 打开 Tester 页面，顶部出现"🎯 测试用例模板"下拉
2. 选择"咨询意图"或"购买意图"后 Test Requirements 自动填充模板文案
3. 在 Knowledge Base 中粘贴产品信息（越详细越好）
4. 点击 Generate，用例将按对应意图策略生成并自动标记 Tag

## 后续扩展点
- Few-shot 示例注入：`build_prompt()` 已预留 `few_shot` 参数
- 新增意图类型：只需在 `intent_prompts.py` 中添加常量 + 模板 + 子 prompt
- Prompt 可视化编辑：将模板迁入 DB，UI 支持在线编辑
