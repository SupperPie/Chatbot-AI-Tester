# testcase 日期刷新增强（多语言）与保存报错修复任务清单
- [x] Task 1: 增强 Refresh Dates 规则，支持同条记录多日期与多语言无年份日期识别
    - 1.1: 扩展日期解析模式，覆盖同一文本内多个日期全部识别
    - 1.2: 支持中文/英文/葡语无年份日期解析，并保持原语言格式输出
    - 1.3: 无年份日期不补年份展示，统一刷新到未来3个月内
    - 1.4: 保留并校准 check-in/check-out 顺序约束（out > in）
    - 1.5: 保持过去日期与远未来日期替换策略一致，避免误匹配非日期数字

- [x] Task 2: 将日期刷新从 input 扩展到 retrieval_context 与 expected_output，并保证三字段一致
    - 2.1: 调整刷新入口，统一处理 input / retrieval_context / expected_output 三个字段
    - 2.2: 对同一条 case 的三字段应用同一日期映射，确保替换结果一致
    - 2.3: 处理 retrieval_context 的字符串/列表形态，写回时保持类型兼容
    - 2.4: 校验多轮场景下按 (id, turn_index) 精确回写，不串行不串轮

- [x] Task 3: 修复 testcase 保存时报错（save_records free variable）
    - 3.1: 定位并移除 render_testcases_page 内部重复导入的 save_records
    - 3.2: 统一使用模块顶部导入，避免嵌套函数闭包变量未绑定
    - 3.3: 校验保存路径（编辑保存、刷新日期后保存）均无作用域异常

- [x] Task 4: 联调与回归验证
    - 4.1: 验证同一文本含多个日期时全部替换成功
    - 4.2: 验证中文/英文/葡语无年份日期可被正确刷新到未来3个月内
    - 4.3: 验证 input/retrieval_context/expected_output 三字段日期替换一致
    - 4.4: 验证保存 testcase 不再出现 free variable 报错
