# 多轮对话复合主键 + 迁移脚本修复

- [x] Task 1: DB Schema 变更 — 改 test_cases 主键为 (id, turn_index)
    - 1.1: 清空 test_cases 表中已有的错误迁移数据 (TRUNCATE CASCADE)
    - 1.2: 修改 turn_index 列为 INTEGER NOT NULL DEFAULT 1
    - 1.3: 删除旧主键，添加复合主键 (id, turn_index)
    - 1.4: 删除 test_case_tags 表的 FK 约束（未使用的表）
    - 1.5: 更新 create_tables.sql 脚本保持一致

- [x] Task 2: 更新 TestCase Model — 复合主键定义
    - 2.1: id + turn_index 均设为 primary_key=True
    - 2.2: turn_index 类型从 Float 改为 Integer, default=1

- [x] Task 3: 更新 TestCaseService — 适配复合主键
    - 3.1: upsert_all() 中查找逻辑改为 (id, turn_index) 匹配
    - 3.2: upsert_all() 中 incoming_ids 和删除逻辑适配
    - 3.3: delete_by_ids() 和 update_category() 确认无需改动（按 id 操作所有轮次）

- [x] Task 4: 更新 utils.py — 去掉 _T{n} workaround
    - 4.1: load_data() 移除 __raw_id 和 normalize_case_id 相关逻辑
    - 4.2: save_data() 适配，确保 turn_index 正确传入 upsert_all
    - 4.3: 移除 normalize_case_id() 函数（如无其他引用）

- [x] Task 5: 更新 UI 层 — 清理 __raw_id 引用
    - 5.1: testcases.py 行删除逻辑改用 id 替代 __raw_id
    - 5.2: testcases.py 移动目录、导入检查等处适配
    - 5.3: tester.py AI 生成用例写入时加 turn_index

- [x] Task 6: 重写迁移脚本 — 修复 3 个规则
    - 6.1: 添加预处理阶段：按 ID 分组，标记每条记录的处理方式
    - 6.2: 规则 1：同 ID 全 single 不同 input → 第一条保留原 ID，其余生成新 ID
    - 6.3: 规则 2：混合 single + multi_turn → 修正 turn=1 的 single 为 multi_turn，多余 single 生成新 ID
    - 6.4: 规则 3：多轮对话保持原 ID + turn_index，不加 _T{n} 后缀
    - 6.5: 新 ID 生成逻辑：查 DB 最大 TC 编号递增
    - 6.6: turn_index 统一转 int，None/NaN 默认 1

- [x] Task 7: 执行迁移并验证
    - 7.1: dry-run 验证记录数和处理方式
    - 7.2: 正式迁移
    - 7.3: 验证 DB 数据：总记录数、多轮对话分组正确性、无 _T{n} 后缀
