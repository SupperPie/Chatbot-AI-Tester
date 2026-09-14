# 统一 testcase 口径、字段对齐与运行弹窗修复任务清单
- [x] Task 1: 盘点并统一全链路统计口径为 testcase id
    - 1.1: 梳理 testcases/report/tester 与目录树中的总数、执行数、通过率计算入口
    - 1.2: 定义统一统计函数与口径（total/passed/failed/pass_rate 全部按 testcase id）
    - 1.3: 替换页面内按行统计逻辑（移除直接以 len(df) 作为业务统计）
    - 1.4: 校准 report 侧历史统计读取与展示，确保多轮场景不出现口径偏差
    - 1.5: 增加最小回归校验（多轮case下总数、通过率、执行数一致）

- [x] Task 2: 完成 TestCase 页面、导入模板与 Report 页字段矩阵对齐
    - 2.1: 输出字段矩阵（TestCase显示/导入支持/Report显示/来源/是否必填）
    - 2.2: 确认并落地“业务关键字段 turn_index”在三页一致语义
    - 2.3: 调整 TestCase 列配置与导入解析，保证与字段矩阵一致
    - 2.4: 调整 Report 列配置与映射，去除不一致或无来源字段
    - 2.5: 同步更新 import_template 与相关读取逻辑

- [x] Task 3: 新增 Actual_Output_CN 结果字段与翻译落库链路
    - 3.1: 设计翻译策略（中文直通、非中文翻译、失败回退不阻断）
    - 3.2: 增加 test_results.actual_output_cn 字段（迁移、ORM、service输出）
    - 3.3: 在结果生成/落库链路接入语言判断与翻译写入
    - 3.4: 在 report 展示层增加 Actual_Output_CN 列与兼容老数据空值
    - 3.5: 增加开关或最小防护，控制翻译成本与异常日志

- [x] Task 4: 修复 Run 触发后 report name 弹窗确认不自动关闭
    - 4.1: 统一三个运行入口的对话框触发流程
    - 4.2: 调整 confirmed_run 状态为单次消费并及时清理临时态
    - 4.3: 修复 rerun 后重复命中 dialog 条件的问题
    - 4.4: 验证 Confirm/Cancel/重复点击场景下弹窗与任务启动行为

- [x] Task 5: 完成联调与回归验证
    - 5.1: 构造单轮+多轮混合数据验证统计口径一致
    - 5.2: 验证 TestCase 与 Report 列位对齐且 turn_index 逻辑正确
    - 5.3: 验证 Actual_Output_CN 生成、回退与展示
    - 5.4: 验证 report name 弹窗确认后自动关闭且只触发一次任务
