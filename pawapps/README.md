# 企业 PawApp 开发规范

每个功能模块必须位于 `pawapps/<app-id>/`，不得继续添加到旧企业后台。

最低结构：`plugin.json`、`backend/main.py`、`ui/index.js`、`migrations/`、`fixtures/`、`tests/`、`README.md`。

## 数据规则

- 通过当前 Agent Workspace 定位 `data/ai-os.sqlite`，禁止使用进程当前目录推断数据位置。
- 表名使用应用前缀，例如 `orders_order`、`knowledge_source`。
- 所有迁移幂等并记录 schema version。
- 正式业务对象不使用 `ctx.storage`。
- 文件和产物只保存 Workspace 相对路径，禁止保存主机绝对路径。

## 执行规则

- 每次应用任务创建唯一 Trace ID。
- 运行态、Tool、完成、失败和停止事件写入 `logs/runtime.jsonl`。
- 高风险变更在执行前调用 `ctx.ui.confirm`，执行后写入 `logs/audit.jsonl`。
- Tool 名称必须在 `plugin.json.meta.tools` 声明，并由安装器为目标 Agent 显式启用。

## 验收规则

应用必须能从桌面打开、从对话调用、重启后恢复，并提供真实数据、失败路径、Artifact 和 Trace 核验脚本。
