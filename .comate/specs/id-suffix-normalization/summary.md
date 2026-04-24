# ID 后缀清理与 Session 分组一致性总结

## 已完成任务
`tasks.md` 中 4 个顶层任务全部完成。

## 实施结果

### 1) 数据加载链路：引入规范化业务ID + 原始唯一ID
- 文件：`app/utils.py`
- 新增：`normalize_case_id(case_id)`
  - 规则：仅去掉末尾 `_T数字`，例如：
    - `TC012345_T1 -> TC012345`
    - `GEN_001_T11 -> GEN_001`
    - `GEN_001` 保持不变
- `load_data()` 现在会：
  - 保留 `__raw_id`（原始唯一ID）
  - 将 `id` 转为规范化业务ID（用于显示与session分组）

### 2) 页面操作改用内部唯一键，避免重复业务ID误操作
- 文件：`app/ui/testcases.py`
- 关键改动：
  - 删除、移动操作从按 `id` 匹配改为优先按 `__raw_id` 匹配。
  - 运行用例组装时剔除内部字段：`__raw_id`、`__row_key`。
  - DataEditor 隐藏 `__raw_id` 列。

### 3) 持久化策略：保存使用原始唯一ID，不改后端结构
- 文件：`app/ui/testcases.py` + `app/utils.py`
- 新增辅助函数：
  - `prepare_df_for_persistence(df)`：保存前用 `__raw_id` 回填真实 `id`，并剔除内部字段。
  - `rebuild_internal_ids(df)`：保存后重建 `__raw_id`、`__row_key`，并重新规范化展示 `id`。
- `save_data()` 也增加了内部字段剔除保护（`__raw_id` / `__row_key`）。

### 4) Session 分组逻辑满足你的要求
- 执行引擎按 `id` 分组：`app/test_engine.py:376-388`
- 由于传入执行引擎的 `id` 现在是规范化后的业务ID，
  同一会话（如 `GEN_001_T1/T2/T11`）会被归并为同一组 `GEN_001`。

## 验证
- 编译检查通过：
  - `app/utils.py`
  - `app/ui/testcases.py`
- lints 检查通过：上述文件无报错。

## 结论
你要求的“去掉最后一个 `_T数字` 后缀，并让同一个ID按同一个session处理”已满足；同时保留原始唯一ID避免破坏数据库主键与现有数据结构。