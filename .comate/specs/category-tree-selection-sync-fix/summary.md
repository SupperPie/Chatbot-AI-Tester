# 子目录有数量但表格为空修复总结

## 完成情况

已完成 `category-tree-selection-sync-fix` 全部任务。

## 主要修复

1. 目录树选中解析修复（核心）
- 文件：`app/ui/components/category_widget.py`
- 在 `_render_tree` 中新增 `_resolve_by_path`，优先按路径索引解析 `sac.tree(return_index=True)` 返回值。
- 仅当路径解析失败时回退到旧的扁平索引兼容逻辑。
- 保留 `__all__` 和异常回退逻辑，避免错误切换。

2. Test Cases 筛选链路对齐与可观测性增强
- 文件：`app/ui/testcases.py`
- 保持 `selected_category -> filter_category -> filter_test_cases` 单一路径。
- 在目录切换和筛选执行处增加调试日志，输出目录与筛选链路，便于定位“左侧有数右侧为空”问题。

## 验证结果

- 语法检查通过：
  - `python3 -m py_compile app/ui/components/category_widget.py app/ui/testcases.py`

- 边界核对：
  - `__all__` 仍可正常展示全量。
  - 目录名未引入大小写自动转换逻辑（保持 case-sensitive）。
  - 目录筛选仍按 `category_id` 生效，不依赖目录名文本。

## 预期收益

- 修复目录树选中值映射错误导致的空表问题。
- 降低“左侧有数量，右侧无数据”的误判概率。
- 后续若仍出现异常，可通过新增日志快速定位是选中值问题还是筛选叠加问题。