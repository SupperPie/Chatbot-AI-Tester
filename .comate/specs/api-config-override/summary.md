# API Config Override - 执行总结

## 完成情况

全部 7 个任务已完成，代码已提交并推送到 `release/2.1` (commit `34e77e3`)。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `scripts/create_tables.sql` | 修改 | api_configs 表新增 `token TEXT`, `request_params JSONB` |
| `app/models/api_config.py` | 新增 | ApiConfig ORM Model |
| `app/services/api_config_service.py` | 新增 | ApiConfigService（get_all/save_all/upsert） |
| `chat_client.py` | 修改 | load_api_configs() DB优先；TYPE_DEFAULTS 模板；deep_merge/merge_config_with_defaults；get_chat_response() 参数合并；10个 get_xxx_response() 新增 extra_params |
| `app/ui/settings.py` | 修改 | DB 读写 + JSON 备份双写；新增 Request Params 列 |

## 关键设计决策

1. **payload 构造策略**: 各 `get_xxx_response()` 函数中，基础字段（message/session_id/user_id 等路由相关字段）保留硬编码，可覆盖业务参数通过 `extra_params.update()` 合并。这保证了 extra_params 不会意外覆盖核心字段。

2. **Hotel userMessage 自动填充**: `get_hotel_response()` 的 `ex.semantic_info.userMessage` 在 extra_params 中为空时自动填充当前 message。

3. **Token 同步**: 执行过程中发现 DB 中已有的 10 条配置缺少 token 值（迁移时表还没有该字段），已从 JSON 同步 2 个 dify 类型的 token 到 DB。

## 验证结果

- DB 10 条配置正常读取
- `load_api_configs()` DB 优先生效
- `get_available_apis()` 下拉列表正常
- `merge_config_with_defaults()` 旧配置（无 request_params）回退默认值，与改造前行为一致
- deep_merge 覆盖逻辑正确
- Token "None" 字符串清理正常
