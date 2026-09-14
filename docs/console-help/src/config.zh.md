# 配置与工作目录

上游技术参考中的 ~/.qwenpaw 是直接使用原生 CLI 的默认值，不是本发行版启动器的数据位置。

| 内容 | 本发行版默认位置 |
| --- | --- |
| 单机工作区 | <安装目录>/apps/zhizaoyunAIOS/workspace |
| 单机凭据 | <安装目录>/apps/zhizaoyunAIOS/workspace/secret |
| 单机账号 | <安装目录>/apps/zhizaoyunAIOS/workspace/secret/auth.json |
| Hub 数据 | <安装目录>/apps/zhizaoyunAIOS/workspace/hub |
| Hub 配置 | <安装目录>/hub.yaml |
| 派生配置 | <安装目录>/hub.runtime.yaml，自动生成 |
| 运行时 | <安装目录>/apps/zhizaoyunAIOS/runtime |
| 启动日志 | <安装目录>/launcher-service.log |

QWENPAW_WORKING_DIR 是当前运行环境的工作区。Hub 用户使用自己的隔离工作区，不应套用另一用户目录。QWENPAW_SECRET_DIR 如显式自定义，应按实际位置备份。

## 备份与修改

停止服务后备份整个工作区、Hub 数据及 hub.yaml；自定义凭据目录也需备份。备份含敏感信息，应限制访问。

运行时可重建，用户工作区不是可随意清理的缓存。不要用删除工作区、清空数据库或强制初始化解决普通启动故障。

优先使用控制台设置；Hub 配置修改 hub.yaml，不编辑自动生成的 hub.runtime.yaml。命令 qwenpaw、环境变量和 Python 导入名称保持原样。反馈日志时不要包含密码和 API Key。
