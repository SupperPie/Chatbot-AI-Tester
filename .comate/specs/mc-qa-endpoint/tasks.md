# MC问答 API 端点配置任务

- [x] Task 1: 在 chat_client.py 中添加 get_dify_workflow_response() 函数
    - 1.1: 定义函数签名和文档字符串
    - 1.2: 解析 token（x-app-code|x-app-passport 格式）
    - 1.3: 构建请求 payload 和 headers
    - 1.4: 实现流式响应解析，从 workflow_finished 事件提取 outputs.answer 作为 Actual output
    - 1.5: 返回的消息体 放到test report中的Raw Data
    - 1.6: 返回标准格式响应

- [x] Task 2: 在 get_chat_response() 中添加 dify_workflow 类型路由
    - 2.1: 添加 elif 分支调用 get_dify_workflow_response()

- [x] Task 3: 在 Settings 页面添加 dify_workflow 类型选项
    - 3.1: 修改 app/ui/settings.py 中的 options 列表
