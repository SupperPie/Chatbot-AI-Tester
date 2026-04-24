# API 配置 DB 持久化 + 同 Type 多配置参数覆盖

- [x] Task 1: 扩展数据库表结构并新增 ORM Model
    - 1.1: 在 `scripts/create_tables.sql` 的 `api_configs` 表中新增 `token TEXT` 和 `request_params JSONB` 字段
    - 1.2: 新增 `app/models/api_config.py`，定义 `ApiConfig` ORM 类映射到扩展后的表
    - 1.3: 执行 ALTER TABLE 使已有数据库生效

- [x] Task 2: 新增 ApiConfigService 服务层
    - 2.1: 新增 `app/services/api_config_service.py`，提供 `get_all()` / `save_all()` / `upsert()` 方法
    - 2.2: `get_all()` 返回 dict 格式（与现有 JSON 结构一致，key=name）

- [x] Task 3: 改造 `load_api_configs()` 为 DB 优先 + JSON 回退
    - 3.1: 修改 `chat_client.py` 中的 `load_api_configs()`，优先从 DB 读取
    - 3.2: DB 不可用或为空时回退到 JSON 文件读取
    - 3.3: `get_available_apis()` 无需改动（已依赖 `load_api_configs()`，自动生效）

- [x] Task 4: 新增 TYPE_DEFAULTS 默认模板与合并逻辑
    - 4.1: 在 `chat_client.py` 中定义 `TYPE_DEFAULTS` 常量，提取各 Type 的默认 request_params
    - 4.2: 实现 `deep_merge()` 和 `merge_config_with_defaults()` 函数

- [x] Task 5: 改造 `get_chat_response()` 及各 `get_xxx_response()` 函数
    - 5.1: `get_chat_response()` 中调用 `merge_config_with_defaults()` 获取合并后参数
    - 5.2: 各 `get_xxx_response()` 函数签名新增 `extra_params=None`
    - 5.3: payload 构造从硬编码改为基础字段 + `extra_params` 合并
    - 5.4: Response 解析逻辑保持不变

- [x] Task 6: 改造 Settings 页面（UI + 存储）
    - 6.1: 读取数据源从 JSON 改为通过 Service 从 DB 加载
    - 6.2: `st.data_editor` 新增 `Request Params` 列（JSON 文本编辑）
    - 6.3: 保存逻辑改为 DB 写入 + JSON 备份双写
    - 6.4: Token 为 `"None"` 字符串时视为空值处理

- [ ] Task 7: 功能验证与收尾
    - 7.1: 在 Settings Debug 面板发送测试请求验证参数覆盖生效
    - 7.2: 确认 Testcases / Report 页面下拉列表正常加载
    - 7.3: 验证旧配置数据（无 request_params）的向后兼容性
    - 7.4: 提交代码到 release/2.1
