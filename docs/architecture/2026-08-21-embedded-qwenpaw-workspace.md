# ADR：以 QwenPaw 为系统主体并将业务数据内聚到 Workspace

- 状态：Accepted
- 日期：2026-08-21
- 上游：`agentscope-ai/QwenPaw@e4995dcf516d27400fbc33891aa3dcbcf79acc7a`

## 决策

智造云 AI-OS 采用 QwenPaw 下游发行版形态。企业能力以 PawApp 交付，业务 SQLite、运行日志、审计日志、文件、知识和产物保存在 Agent Workspace。

## 原因

外置企业后台造成两套导航、两套会话/任务状态、两套部署和额外 Gateway 身份边界。PawApp 与 Workspace 已提供应用容器、Agent 上下文、文件、会话、备份和扩展接口，继续保留外置控制面只会增加演示失败点。

## 数据布局

主 Workspace 是首期企业边界：

```text
<workspace>/
  data/ai-os.sqlite
  logs/runtime.jsonl
  logs/audit.jsonl
  files/
  knowledge/
  artifacts/
  sessions/
  memory/
```

业务库不得放在插件安装目录，因为插件升级、重装和卸载不应影响企业数据。

## 上游维护

- 保留 Apache-2.0 LICENSE、NOTICE 与上游归属。
- 智造云修改优先使用 PawApp、Plugin、Slot 和配置。
- 上游源代码以固定 commit 导入，升级采用显式同步 PR，不跟随浮动分支。
- 核心补丁单独记录，确保可以重新应用和回归验证。

## 后果

- 旧 `apps/enterprise` 进入只读迁移状态。
- PR #22 的 HTTP Tool Gateway 不进入目标架构。
- 多企业首期通过独立 Workspace/实例隔离，而不是在同一 SQLite 中依赖浏览器身份切租户。
