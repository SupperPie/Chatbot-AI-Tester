# Testcase Table Operations Fix

## 需求 1：恢复表格行内新增功能

### 现状
`st.data_editor` 已配置 `num_rows="dynamic"`（`testcases.py:699`），UI 上可以新增行。但新增行 **无法被保存**。

### 根因
自动保存逻辑（`testcases.py:740-751`）通过 `__row_key` 匹配 `edited_page_df` 和 `st.session_state.df`：
```python
rk = row['__row_key']
main_idx = st.session_state.df.index[st.session_state.df['__row_key'] == rk]
```
新增行没有预分配的 `__row_key`（值为 `NaN`），在 `st.session_state.df` 中找不到匹配行，导致新增数据被静默丢弃。

### 修复方案
在自动保存逻辑中，检测 `edited_page_df` 中是否有新增行（`len(edited_page_df) > len(page_df)` 或 `__row_key` 为 NaN 的行）。对于新增行：
1. 为其分配 `__row_key`
2. 设置默认值（`category_id` 使用当前筛选目录，`type` 默认 `single`）
3. 追加到 `st.session_state.df`
4. 随后的 `save_data()` 会自动分配 TC ID 并写入 DB

### 涉及文件
| 文件 | 修改位置 | 说明 |
|------|----------|------|
| `app/ui/testcases.py` | line 734-774 (auto-save block) | 增加新增行检测与追加逻辑 |

### 实现细节
在现有的 `page_edited` 判断之前，先检测新增行：
```python
# 检测新增行（__row_key 为空或不在原 page_df 中的行）
original_keys = set(page_df['__row_key'].tolist()) if '__row_key' in page_df.columns else set()
new_rows = []
for i, row in edited_page_df.iterrows():
    rk = row.get('__row_key')
    if pd.isna(rk) or rk == '' or rk not in original_keys:
        new_rows.append(row)

if new_rows:
    max_rk = max(
        (int(k.split('_')[1]) for k in st.session_state.df['__row_key'] if isinstance(k, str) and k.startswith('rk_')),
        default=-1
    )
    for row in new_rows:
        max_rk += 1
        new_row_dict = row.to_dict()
        new_row_dict['__row_key'] = f'rk_{max_rk}'
        new_row_dict['__raw_id'] = ''  # save_data 会自动分配 TC ID
        new_row_dict.setdefault('category_id', filter_category if filter_category not in ('__all__', '') else 'root')
        new_row_dict.setdefault('type', 'single')
        new_row_dict.setdefault('Select', False)
        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row_dict])], ignore_index=True)
    
    # 新增后触发保存
    save_df = prepare_df_for_persistence(st.session_state.df)
    saved_df_clean = save_data(save_df)
    if "Select" not in saved_df_clean.columns:
        saved_df_clean.insert(0, "Select", False)
    saved_df_clean = rebuild_internal_ids(saved_df_clean)
    st.session_state.df = saved_df_clean
    st.session_state.df_content_sig = get_content_signature(st.session_state.df)
    st.toast("✅ New row(s) added and saved!", icon="➕")
    st.rerun()
```

### 边界条件
- 新增行无 `input` 内容时仍保存（允许先新增空行再编辑）
- 多行同时新增时批量处理
- 新增行与现有编辑同时发生时，先处理新增再处理编辑

---

## 需求 2：Move 操作后清除选中状态

### 现状
`move_to_category_dialog`（`testcases.py:257-276`）成功移动后，DB 操作（更新 `category_id`）和本地 DataFrame 更新均已正确。唯一的问题是 **UI 状态**：`Select` 列未重置，导致移动完成后选中计数仍然不为 0。

这是纯 UI 级别的 bug，与数据库无关。

### 修复方案
在 `st.rerun()` 之前，重置 `st.session_state.df['Select']` 为 False：

### 涉及文件
| 文件 | 修改位置 | 说明 |
|------|----------|------|
| `app/ui/testcases.py` | line 275 (`move_to_category_dialog` 成功分支，`st.rerun()` 之前) | 加一行 `st.session_state.df['Select'] = False` |

---

## 需求 3：对话分组及轮数逻辑验证

### 检查结论：逻辑正确，无需修改

各层均遵循 "ID 相同 + type=multi_turn → 同一对话, turn_index → 轮数" 规则：

| 层面 | 文件 | 行为 |
|------|------|------|
| **生成 Prompt** | `app/ui/tester.py:68-96` | 要求 AI 输出 `type: "multi_turn"` + 递增 `turn_index` |
| **生成后解析** | `app/ui/tester.py:137-144` | `turn_index == 1` 分配新 ID，`> 1` 复用上一个 ID |
| **数据加载** | `app/utils.py:106-122` | 同样的 multi_turn ID 继承逻辑 |
| **UI 排序** | `app/ui/testcases.py:571-573` | 按 `[id, turn_index]` 排序，同对话行相邻 |
| **测试执行** | `app/test_engine.py:373-449` | 按 ID 分组 multi_turn，按 turn_index 排序后顺序执行 |

description 字段当前置空是有意设计，不影响分组逻辑。

---

## 附：与 save-perf-and-range-fix 的关系
之前的 `save-perf-and-range-fix` spec（upsert_all 性能优化 + ID Range Filter 修复）仍待执行，与本次修复独立，不冲突。本次修复的 `save_data()` 调用仍会走 `upsert_all()`，性能优化后效果更好。
