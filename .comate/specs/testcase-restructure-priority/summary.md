# Test Case 重构与 Priority 体系实施总结

## 已完成项

- 完成 `priority` 全链路接入：模型、服务、生成流程、Test Cases 页面、加载/保存兼容。
- 完成 Test Cases 页面 Priority 能力：
  - 表格新增 `priority` 列（`P0/P1/P2` 下拉编辑）
  - 新增 Priority 多选筛选（含`(空)`）
  - 新增批量设置 Priority（支持清空）
  - 历史空值保持为空，不做自动回填
- 完成目录结构能力：
  - `CategoryService.reorder_siblings(parent_id, ordered_ids)`
  - `CategoryService.move_node(cat_id, new_parent_id)`
  - 节点换父时递归更新子树 `path/level`，并校验防循环与 3 级层级上限
- 完成目录 UI 操作：
  - 在目录组件增加“上移/下移”同级排序入口
  - 增加“换父目录”入口与对话框
- 完成“批量移动目录”入口规范化：仅基于选中行触发移动。
- 完成 `app/utils.py` 兼容：
  - `load_data` 增加 `priority` 读取/默认列
  - Priority 值统一规范化为 `P0/P1/P2/None`

## 关键变更文件

- `app/ui/testcases.py`
- `app/services/category_service.py`
- `app/ui/components/category_widget.py`
- `app/utils.py`
- `.comate/specs/testcase-restructure-priority/tasks.md`

## 回归与校验

已执行语法校验：

- `python3 -m py_compile app/models/test_case.py`
- `python3 -m py_compile app/services/test_case_service.py`
- `python3 -m py_compile app/services/category_service.py`
- `python3 -m py_compile app/ui/tester.py`
- `python3 -m py_compile app/ui/testcases.py`
- `python3 -m py_compile app/ui/components/category_widget.py`
- `python3 -m py_compile app/utils.py`

结果：全部通过。

## 需求对齐说明

- 历史测试用例 Priority 为空时保持为空，仅在人工批量设置或手工编辑时更新。
- 目录名称未引入任何自动大小写转换逻辑，保持输入大小写原样（case-sensitive）。
- 同级排序使用人工调整顺序（上移/下移）并持久化到 `sort_order`。