# 旧架构移除记录

本次发布候选版本永久移除以下运行源码：

- `apps/enterprise`：DeepSeek Harness / 8390企业服务及其数据库、页面、调度器和测试。
- `pawapps/zhiyun-orders`：已由独立 `zhiyun-order-studio` 替代。
- `pawapps/_shared`：旧内置PawApp共享层，已由Workspace/Data Core替代。
- `cleanup-legacy.py`：依赖QwenPaw Python包，不适用于Windows Desktop版；统一使用Node等价脚本。
- QwenPaw转向过程中的V4/V5和阶段性架构文档。

迁移不是删除用户数据。Node清理器只会将旧插件移动到 `~/.qwenpaw/disabled_plugins`，并从Agent配置移除已废弃工具；Workspace数据库、日志和知识文件保留。

如需查阅旧实现，应通过Git历史访问，不应把旧服务重新复制回当前发布树。
