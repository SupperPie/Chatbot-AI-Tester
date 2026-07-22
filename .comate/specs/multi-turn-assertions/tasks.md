# 多轮对话断言组件执行功能实现任务

- [ ] Task 1: 修改 run_batch 方法，传递 assertions 到 conversation_turns
    - 1.1: 在 test_engine.py:636-644 的 conversation_turns.append 中添加 assertions 字段
    - 1.2: 从 row.get("assertions") 获取断言配置并传递

- [ ] Task 2: 修改 run_batch 调用 run_multi_turn_case 时传递 execution_mode
    - 2.1: 在 test_engine.py:653 调用时添加 execution_mode=execution_mode 参数

- [ ] Task 3: 修改 run_multi_turn_case 方法签名，接收 execution_mode 参数
    - 3.1: 在 test_engine.py:662 方法签名中添加 execution_mode: str = "full" 参数
    - 3.2: 更新方法文档字符串，说明 execution_mode 参数

- [ ] Task 4: 在 run_multi_turn_case 中为每轮执行断言组件（正常流程）
    - 4.1: 在 test_engine.py:771 行（turn_results.append 之前）插入断言执行逻辑
    - 4.2: 从 turn.get("assertions") 获取断言配置
    - 4.3: 兼容字符串格式的 assertions（JSON 解析）
    - 4.4: 根据 execution_mode 和 assertion_refs 判断是否需要执行断言
    - 4.5: 调用 self._extract_assertion_response 构建响应对象
    - 4.6: 调用 AssertionEngine().run 执行断言
    - 4.7: 构建 turn_assertion_detail 字典，格式与单轮测试一致
    - 4.8: 异常处理：捕获断言执行错误并返回错误信息
    - 4.9: 在 turn_results.append 的字典中添加 assertion_detail 字段

- [ ] Task 5: 在 run_multi_turn_case 中为错误流程添加 assertion_detail 字段
    - 5.1: 在 test_engine.py:745-757 错误处理的 turn_results.append 中添加 assertion_detail: None

- [ ] Task 6: 在 run_multi_turn_case 返回结果前实现综合 passed 判定
    - 6.1: 在 test_engine.py:844 之前（return 之前）计算是否有任何一轮执行了断言
    - 6.2: 遍历 turn_results，检查所有有断言的轮次是否都通过
    - 6.3: 根据 execution_mode 实现三种判定逻辑：
        - execution_mode == "assertion": 只看断言
        - execution_mode == "full": 语义 AND 断言（如果有断言）
        - execution_mode == "semantic": 只看语义
    - 6.4: 将返回字典中的 passed 字段改为使用 final_passed

- [ ] Task 7: 测试验证
    - 7.1: 创建多轮对话测试用例，为部分轮次绑定断言组件
    - 7.2: 执行测试，验证每轮的 assertion_detail 是否正确
    - 7.3: 验证 execution_mode="full" 时的 passed 判定（语义+断言）
    - 7.4: 验证 execution_mode="assertion" 时只看断言
    - 7.5: 验证 execution_mode="semantic" 时只看语义
    - 7.6: 验证无断言时的行为（passed 只看语义）
