# Zhiyun Enterprise AI Agent Platform (`apps/enterprise`)

English | [中文](README.zh.md)

A multi-tenant enterprise AI agent runtime and business execution platform built on DeepSeek Harness. The repository product requirements and `AI-OS-PRD-V3.0.md` define the complete product specification.

## Architecture

```text
Enterprise platform (8390)  ←HTTP envelope API + WebSocket→  DSH Harness (8308)  ←OpenAI compatible→  Model layer
```

- **Enterprise platform**: This directory uses Node.js 24 or later without runtime npm dependencies (`node:http` and `node:sqlite`) and owns tenants, RBAC, business data, dashboards, automatic AI runs, knowledge, scheduling, logs, and audit.
- **DSH Harness**: The repository's Cordis plugin-based Agent Runtime includes the product's neutral branding and workspace-resume customizations.
- **Model layer**: Configurable providers route to local LM Studio or remote OpenAI-compatible gateways.

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

Seed accounts are demonstration data. Their shared password and identifiers are created by `server/db.js`; do not enable them in a production deployment.

## Capabilities

- **Multi-tenancy**: Core records carry `tenant_id`, server context supplies the active tenant, and cross-tenant requests fail with HTTP 403.
- **Automatic AI runs**: Role rotation and feature demonstrations drive real model sessions through the DSH envelope API and record one trace across each run.
- **Knowledge**: Knowledge bases contain entries, `knowledge_search` performs real retrieval, and the harvester writes reviewed results to tenant workspaces for DSH access.
- **Work collaboration**: One-shot AI tasks run asynchronously, expose status and trace replay, and may belong to project containers.
- **Scheduled tasks**: Cron, interval, and condition triggers use `job_lock`, retries, and dead-letter audit records.
- **Data generation**: Runtime and connected business generators create marked demonstration data with coherent order, finance, and inventory relationships.
- **Visualization**: Database browsing, AI runtime dashboards, and Markdown rendering expose platform state without direct database access.
- **Audit**: Runtime, tool, operation, and immutable audit records share trace identifiers; authorized display corrections retain before-and-after values.

## AI-OS V3.1 Phase 0

Phase 0 adds a compatible AI-OS execution baseline while existing V2 APIs, tables, and execution paths remain available:

- `server/os/schema.js` creates the Task, Execution, Process, Checkpoint, Event, Approval, Artifact, and Capability baseline idempotently.
- `server/os/execution-kernel.js` provides one runner-selection and result-normalization boundary for the lightweight enterprise loop and DSH sessions.
- `server/os/adapters/` injects both runners so business code does not bind directly to one execution engine.
- `server/os/contracts.js` owns shared task, process, and execution states and rejects execution requests without a tenant.
- `scripts/verify-phase0.mjs` verifies idempotent SQLite migration, runner routing, and the tenant requirement.

Run the Phase 0 verification:

```sh
pnpm --filter @deepseek-ai/dsh-enterprise run verify:phase0
```

## AI-OS V3.1 Phase 1

Phase 1 migrates one-shot WorkTask execution onto the unified runtime without breaking the existing WorkTask API:

- `server/os/runtime-store.js` persists tenant-scoped Task, Execution, Process, and lifecycle Event records.
- `server/os/task-service.js` idempotently maps each legacy WorkTask to one AI-OS Task and sends every execution through the kernel.
- `GET /api/os/tasks` and `GET /api/os/tasks/:id` expose tenant-scoped task status and execution history.
- The legacy `business_work_task` row remains a compatibility projection for the current UI.
- `scripts/verify-phase1.mjs` covers source idempotency, successful and failed execution persistence, and cross-tenant lookup isolation.

Run the Phase 1 verification:

```sh
pnpm --filter @deepseek-ai/dsh-enterprise run verify:phase1
```

Scheduler, Auto-run, and DSH session persistence remain later migrations. Old and new schedulers must never trigger the same business task concurrently.

## AI-OS V3.1 Phase 2

Phase 2 migrates the existing Scheduler worker path while preserving its trigger and compatibility behavior:

- Cron, interval, condition evaluation, `job_lock`, legacy Job rows, retries, and dead-letter audit stay in `server/scheduler.js`.
- Every scheduler attempt maps to one AI-OS Execution and Process through `TaskService`.
- Retry counts are persisted per Execution, so separate attempts remain traceable.
- Completion and retry decisions persist resumable Checkpoints and emit checkpoint Events.
- `server/os/runtime.js` provides one shared runtime composition for REST and Scheduler callers.
- `scripts/verify-phase2.mjs` covers scheduler source mapping, retry attempts, checkpoints, and tenant isolation.

Run the Phase 2 verification:

```sh
pnpm --filter @deepseek-ai/dsh-enterprise run verify:phase2
```

These Checkpoints capture safe attempt boundaries; resuming inside an interrupted model turn is not part of this phase.

## AI-OS V3.1 Phase 3

Phase 3 mirrors DSH-backed Auto-run work into the unified runtime without changing the DSH transport:

- Role simulation, report generation, feature demonstrations, and multi-Agent turns map persistent DSH Sessions to AI-OS Tasks.
- Every completed or failed DSH turn records a DSH Execution, Process, lifecycle Events, and a `session.turn.completed` Checkpoint.
- The legacy runtime execution, message, tool, model-usage, and dashboard records remain available for the current UI.
- Session identifiers stay in existing `business_setting` keys for cold recovery and are also captured in Checkpoint state.
- `scripts/verify-phase3.mjs` verifies idempotent session mapping, success and failure history, resumable session checkpoints, and tenant isolation.

Run the Phase 3 verification:

```sh
pnpm --filter @deepseek-ai/dsh-enterprise run verify:phase3
```

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

SQLite databases and tenant workspace documents under `data/` are ignored. Startup creates seed records idempotently, and scripts regenerate demonstration datasets. Generated and imported records retain `data_origin` values such as `real`, `simulated`, `imported`, `manual`, `generated`, `auto-simulated`, and `web-research`.
