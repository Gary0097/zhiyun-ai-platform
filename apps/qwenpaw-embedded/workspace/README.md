# 智造云 AI-OS Workspace 约定

该目录是版本化模板，不存放真实运行数据。安装时将 `template/` 内容初始化到 QwenPaw 当前 Agent Workspace。

正式数据目录：

- `data/ai-os.sqlite`：业务与执行索引
- `logs/runtime.jsonl`：运行事件原始日志
- `logs/audit.jsonl`：高风险与数据变更日志
- `files/`：业务原件
- `knowledge/`：知识源文件
- `artifacts/`：应用产物

禁止将真实 Workspace、数据库、日志、密钥或客户文件提交到 Git。
