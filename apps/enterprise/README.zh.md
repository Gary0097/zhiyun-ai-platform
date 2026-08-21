# 智造云企业 AI 智能体平台（`apps/enterprise`）

[English](README.md) | 中文

基于 DeepSeek Harness 的多租户企业 AI 智能体运行与业务执行平台。仓库产品需求文档与 `AI-OS-PRD-V3.0.md` 定义完整产品规格。

## Architecture

```text
Enterprise platform (8390)  ←HTTP envelope API + WebSocket→  DSH Harness (8308)  ←OpenAI compatible→  Model layer
```

- **企业平台**：本目录使用 Node.js 24 或更高版本且无 npm 运行时依赖（`node:http` 和 `node:sqlite`），负责租户、RBAC、业务数据、看板、AI 自动运行、知识、调度、日志和审计。
- **DSH Harness**：仓库内基于 Cordis 插件的 Agent Runtime，包含产品的中性品牌和工作区续接定制。
- **模型层**：可配置 Provider 路由到本地 LM Studio 或远程 OpenAI 兼容网关。

## Quick start

```sh
# 1. Configure model credentials in an ignored local file.
cp config/secrets.example.env config/secrets.local.env

# 2. Start DSH Web on 8308. Provider credentials live in the DSH credentials layer.
node ../cli/lib/bin.js web --no-open --port 8308

# 3. Start the enterprise platform on 8390. The launcher loads secrets.local.env.
node start.mjs

# 4. Optionally generate the historical runtime dataset.
node server/cli.js simulate
```

种子账号仅用于演示，其共用密码和标识由 `server/db.js` 创建；生产部署不得启用这些账号。

## Capabilities

- **多租户**：核心记录包含 `tenant_id`，服务端上下文提供当前租户，跨租户请求返回 HTTP 403。
- **AI 自动运行**：角色轮转和功能演示通过 DSH 信封 API 驱动真实模型 Session，并为每次运行记录统一 Trace。
- **知识**：知识库包含条目，`knowledge_search` 执行真实检索，收割器把审核后的结果写入租户工作区供 DSH 访问。
- **工作协同**：一次性 AI 任务异步运行，提供状态和 Trace 回放，并可归属项目容器。
- **定时任务**：Cron、Interval 和 Condition 触发器使用 `job_lock`、重试和死信审计记录。
- **数据生成**：运行数据和关联业务生成器创建带来源标记的演示数据，并保持订单、财务和库存关系一致。
- **可视化**：数据库浏览、AI 运行看板和 Markdown 渲染无需直接访问数据库即可展示平台状态。
- **审计**：运行、Tool、操作和不可变审计记录共享 Trace 标识；获授权的展示修正保留修改前后值。

## AI-OS V3.1 Phase 0

Phase 0 以兼容方式加入 AI-OS 统一执行基线，现有 V2 API、表和执行路径继续可用：

- `server/os/schema.js` 幂等创建 Task、Execution、Process、Checkpoint、Event、Approval、Artifact 和 Capability 基线。
- `server/os/execution-kernel.js` 为平台轻量循环与 DSH Session 提供统一 Runner 选择和结果标准化边界。
- `server/os/adapters/` 通过依赖注入封装两类 Runner，避免业务代码直接绑定单一执行引擎。
- `server/os/contracts.js` 负责统一任务、进程和执行状态，并拒绝缺少租户的执行请求。
- `scripts/verify-phase0.mjs` 验证 SQLite 幂等迁移、Runner 路由和租户要求。

运行 Phase 0 验证：

```sh
pnpm --filter @deepseek-ai/dsh-enterprise run verify:phase0
```

Phase 0 不迁移 WorkTask、Scheduler、Auto-run 或 DSH Session 持久化。后续通过适配器逐步迁移，且新旧调度器不得同时触发同一个业务任务。

## Directory map

```text
server/
├── index.js               HTTP service entry
├── db.js                  V2 schema, seeds, and idempotent migrations
├── routes.js              REST API and permission guards
├── auto-run.js            Automatic role and feature runs
├── function-catalog.js    Product feature catalog
├── knowledge-harvester.js Knowledge harvesting pipeline
├── business-generator.js  Coherent enterprise demonstration data
├── harness.js             Existing bounded enterprise Agent loop
├── llm.js                 OpenAI-compatible model adapter
├── tools.js               Enterprise Tool implementations
├── scheduler.js           Existing scheduled-task runner
├── os/                    AI-OS contracts, schema, kernel, and runner adapters
└── auth.js                Authentication, authorization, and operation logs
public/index.html          Current single-file enterprise SPA
scripts/                   Verification, import, and orchestration scripts
start.mjs                  Launcher and local credentials loader
config/model.json          Model configuration without credentials
```

## Data

`data/` 下的 SQLite 数据库和租户工作区文档不会入库。启动过程幂等创建种子记录，脚本可重新生成演示数据。生成和导入记录保留 `real`、`simulated`、`imported`、`manual`、`generated`、`auto-simulated` 和 `web-research` 等 `data_origin` 值。
