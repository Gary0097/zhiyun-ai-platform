# 智造云 AI-OS Workspace 约定

该目录是版本化模板，不存放真实运行数据。当前阶段只启用日志审计，不安装业务应用。

正式数据目录：

- `data/ai-os.sqlite`：Tool 调用审计索引
- `logs/runtime.jsonl`：运行事件原始日志
- `logs/audit.jsonl`：Tool 调用审计日志

审计不保存模型思维链；Tool 参数中的密码、令牌、Cookie 等敏感字段会被脱敏。

禁止将真实 Workspace、数据库、日志、密钥或客户文件提交到 Git。
