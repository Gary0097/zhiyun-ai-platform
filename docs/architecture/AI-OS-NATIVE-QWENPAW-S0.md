# AI-OS 原生 QwenPaw 收口方案（S0）

## 当前范围

本阶段以 QwenPaw 2.1.0 为唯一运行内核和界面。暂停订单等业务应用开发，不覆盖 QwenPaw Logo，不启动独立企业服务，只保留 Workspace 内的日志审计能力。

| 项目 | 当前约定 |
| --- | --- |
| UI 与 Logo | 使用 QwenPaw 原生实现 |
| 进程 | `qwenpaw app` 单进程 |
| Web 地址 | `http://127.0.0.1:8088` |
| 8390 企业服务 | 停用，不属于当前运行方案 |
| 业务 PawApp | 暂停安装与启动 |
| 日志 | `<workspace>/logs/runtime.jsonl` |
| 审计 | `<workspace>/logs/audit.jsonl`、`<workspace>/data/ai-os.sqlite` |

## 启动

首次安装 QwenPaw 2.1.0 并完成 `qwenpaw init` 后：

- Windows：双击仓库根目录 `start-ai-os.cmd`
- macOS/Linux：执行 `./start-ai-os.sh`

启动器会重复安全地执行以下动作：停用旧 `zhiyun-brand`、`zhiyun-orders` 插件；从 Agent 配置移除旧企业与订单 Tool；安装无界面的 `zhiyun-audit`；启动原生 QwenPaw。

被停用的旧插件会移动到 QwenPaw 工作目录下的 `disabled_plugins`，不会直接删除。

## 边界

`apps/enterprise` 仅作为历史代码保留，不在默认部署链路内。后续若恢复业务应用，必须通过独立阶段重新评审，不得让 Agent 依赖一个未随系统启动的端口或服务。
