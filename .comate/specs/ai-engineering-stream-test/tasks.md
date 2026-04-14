# AI Engineering 流式接口测试实现任务计划

- [x] Task 1: 在 chat_client.py 中添加 get_ai_engineering_response 函数
    - 1.1: 实现请求构造（payload、headers）
    - 1.2: 实现 SSE 流式响应解析
    - 1.4: 实现 type=done 时提取 content
    - 1.5: 实现超时和异常处理

- [x] Task 2: 修改 get_chat_response 函数添加 ai_engineering 类型路由
    - 2.1: 在类型判断中添加 ai_engineering 分支
    - 2.2: 支持从配置读取 lob 参数

- [x] Task 3: 在 api_config.json 中添加 AI Engineering 配置
    - 3.1: 添加 url、type、lob 等配置项
