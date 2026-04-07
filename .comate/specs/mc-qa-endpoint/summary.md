# MC问答 API 端点配置 - 完成总结

## 完成的任务

1. **添加 get_dify_workflow_response() 函数** (`chat_client.py:744-841`)
   - 支持 `x-app-code|x-app-passport` 格式的 token 解析
   - 从 `workflow_finished` 事件中提取 `outputs.answer` 作为 Actual output
   - 完整响应体保存到 Raw Data

2. **添加路由分支** (`chat_client.py:873-875`)
   - 在 `get_chat_response()` 中添加 `dify_workflow` 类型路由

3. **更新 Settings 页面** (`app/ui/settings.py:43-47`)
   - 添加 `dify_workflow` 类型选项
   - 更新 Token 字段说明

## 配置方式

在 Settings 页面添加新端点：

| 字段 | 值 |
|------|-----|
| Name | MC问答 |
| URL | https://ai-flow-app-uk.dp-svc.com/api/chat-messages |
| Type | dify_workflow |
| Token | ZdbUw8IngEi4CwZD\|eyJhbGciOiJIUzI1NiIs... |

**注意**: Token 格式为 `{x-app-code}|{x-app-passport}`，中间用 `|` 分隔。

## 文件变更

| 文件 | 变更 |
|------|------|
| `chat_client.py` | +98 行（新函数 + 路由） |
| `app/ui/settings.py` | 修改 3 行（类型选项 + 帮助文本） |
