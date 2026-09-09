# 制造云 AI-OS Project Plan

## Purpose

This plan turns the V6.4 PRD and the application-discovery progress ledger into
an executable delivery order. It does **not** reinterpret an entry marked
`planned`, `in_progress`, or `testing` as complete. The machine-readable source
of feature status remains
`plugins/zhiyun-app-discovery/feature_progress.json`.

The complete product spans multiple repositories. This repository owns the
QwenPaw runtime integration, system plugins, cross-platform launchers, release
verification, catalog, and external PawApp locks. Data Studio and Order Studio
implementation changes belong in their respective repositories and are brought
into this repository only through pinned commits.

## Detected Baseline

As of the ledger date, the plan contains 31 capabilities:

- 13 completed;
- 17 in testing at 90%; and
- 1 in development.

Therefore the product is not complete. Percentages are planning indicators, not
acceptance evidence. A capability becomes `completed` only at 100% after its
real-data path, UI, backend, Agent tools, persistence, error/empty states,
platform checks, and issue acceptance criteria have passed.
An entry marked `testing` is available on the running platform for user
acceptance but is not yet claimed as delivered.

## Repository Ownership

| Area | Owning repository | Integration into AI-OS |
| --- | --- | --- |
| QwenPaw runtime, launchers, Data Core, audit, app discovery | `Gary0097/zhiyun-ai-platform` | Direct release gate |
| Features 1–6 | `Gary0097/zhiyun-data-studio` | Update `pawapps.lock.json` after its PR is merged |
| Features 7–11 | `Gary0097/zhiyun-order-studio` | Update `pawapps.lock.json` after its PR is merged |
| Features 12–15 | `Gary0097/zhiyun-service-studio` | Published as a PawApp and pinned by full SHA in `pawapps.lock.json` |
| Features 16 and 30 | `Gary0097/zhiyun-supply-studio` | Published as a PawApp and pinned by full SHA in `pawapps.lock.json` |
| Features 17–19 | `Gary0097/zhiyun-sales-studio` | Published as a PawApp and pinned by full SHA in `pawapps.lock.json` |
| Features 20–22 | `Gary0097/zhiyun-finance-studio` | Published as a PawApp and pinned by full SHA in `pawapps.lock.json` |
| Features 23, 24, 26–28 | `Gary0097/zhiyun-people-studio` | Published as a PawApp and pinned by full SHA in `pawapps.lock.json` |

Generated runtime copies under `apps/qwenpaw-embedded/runtime/pawapps` are never
development sources.

## Delivery Sequence

### Phase 0 — Continuous-development controls

1. Keep repository rules, issue forms, the PR template, and the Windows/Linux
   release gate enabled.
2. Configure the three existing repositories in Codex Cloud and enable review.
3. Create the `codex-ready`, priority, and repository labels in GitHub.

Cloud environment authorization and GitHub repository settings require an
administrator and cannot be represented by a source commit.

### Phase 1 — Accept the two existing PawApps

1. Data Studio features 1–6 were accepted against real Data Core records.
2. Order Studio features 7–11 were accepted against real order and contract
   samples, including the exception workflow.
3. Both PawApps were merged first, pinned by formal merge SHA, and passed the
   main repository release gate on Windows and Linux.

### Phase 2 — Complete shared platform foundations

1. Complete Data Core connectors and the existing-system integration hub.
2. Complete audit UI, encryption, leakage prevention, and safety acceptance.
3. Validate application discovery, offline fallback, dependency health, data
   backup/recovery, migrations, and semantic runtime health end to end.

The accepted Phase 2 implementation uses the system integration center v0.2.1,
Data Core v0.7.0 and Audit v1.3.0. Capabilities 29 and 31 passed live user
acceptance on 2026-08-23 and are available; installed state alone still does not
make any other capability available.

### Phase 3 — Publish and exercise the five studio PawApps

The five business studios are published as installable PawApps and pinned by
full SHA in `pawapps.lock.json`, so a fresh launch materializes and registers
them:

1. Service Studio (features 12–15), version 0.1.0.
2. Supply Studio (features 16 and 30), version 0.1.0.
3. Sales Studio (features 17–19), version 0.1.0.
4. Finance Studio (features 20–22), version 0.1.0.
5. People Studio (features 23, 24, and 26–28), version 0.1.0.
6. Workspace knowledge workflow (feature 25) remains in development.

Each studio has its own repository, manifest, tests, application card, health
contract, versioned data contract, rollback method, and locked full SHA. They
are currently `testing` because they await user machine acceptance before being
marked `completed`.

## Phase 4 — Continuous Simulation & Dual-State

The user direction (2026-08-24) upgrades the project from "populate demo data" to a
long-running **Demo / Production dual-state verification system**. This is a new
product track above the 31-capability ledger and is **not** folded into
`plugins/zhiyun-app-discovery/feature_progress.json`; it is tracked in:

- `docs/product/AI-OS-SIMULATION-DUAL-STATE-VISION.md` (requirements, naming, data flow, isolation)
- `docs/product/DEMO-PRODUCTION-EPICS.md` (independent 6-Epic ledger)

### Phase 4 Epics

| Epic | Name | Scope |
| --- | --- | --- |
| 1 | Enterprise Seeder | One command generates enterprise, departments, users, roles, permissions, agents, apps, data sources, sessions, tasks, tokens, logs |
| 2 | Agent Factory | Templates generate full agent config (prompt/model/skill/tool/knowledge/permission/token/frequency/success-rate/latency) and link real model calls |
| 3 | Simulation Runtime | Local model drives business events through Agent → Skill → Tool → result → log → token → user behavior → stats |
| 4 | Time Machine | Generates 2025-12-01→today, daily growth, and supports any time-range switch across all dashboards |
| 5 | Data Platform | Unified Excel/CSV Import/Export SDK + `data_mode=demo|production` + DataContext + tenant/environment isolation |
| 6 | Data Integrity | Cross-module consistency, anomaly detection, safe auto-repair, `Data Integrity Report` |

### Phase 4 Product rules

1. Frontend must not show "模拟 / Mock / 测试". Use "数据环境 / Demo / Live"; the underlying field is `data_mode`.
2. All queries go through a unified `DataContext` (`User → App → DataContext → Demo/Production dataset → DB`).
3. Demo and Production are isolated (`tenant_id` / `environment_id` / `data_source`); production must never read demo records.
4. Stats must be traceable to records (usage ↔ conversations, token ↔ executions, files ↔ downloads, permissions ↔ accessible agents).
5. A capability counts as `completed` only when it is runnable with persisted evidence in `docs/qa` and status reflects the same Definition of Done below.


### Phase 4 verification note (2026-08-25)

Epic 1 (Enterprise Seeder) and the first pass of Epic 4 (Time Machine) and Epic 6
(Data Integrity) are now runnable with persisted evidence:

- `zhiyun-enterprise-seeder` ships a real GUI (`/apps/zhiyun-enterprise-seeder`),
  one-command `/seed`, multi-environment `/records` isolation by `env_id +
  data_mode`, and Bearer auth (config/summary/records require token, `/seed` is
  admin-only). GUI regression 22/22 pass.
- `/summary` now reports `files / downloads / logins` in addition to
  sessions/tasks/Token, and honors `start_date / end_date` for every time-based
  entity, so the Time Machine "switch any time range" behavior is in place.
- `files.created_at` was fixed to be distributed across
  `2025-12-01..2026-08-25` (230 distinct days) instead of all landing on the
  seed date; a narrow range query returns a partial file count as expected.
- `/integrity` produces a 14-check `Data Integrity Report`
  (`total=14 passed=14 failed=0 healthy=true`) in about 1.1s after adding 5
  covering indexes; the 14th check (`business_event_scope`) closes the
  business-event chain.
- Epic 6 closed: safe auto-repair (`POST /integrity/repair`, admin-only, written to
  `integrity_repair_log`), daily snapshot (`GET /integrity/daily`, idempotent
  per-day update persisted to `integrity_reports`), and history
  (`GET /integrity/history`). Live evidence 14/14 on demo and production;
  unit tests 3/3; `verify-release.mjs` passes.
- Frontend regression fixed: the seeder page crashed ("页面出现异常") because of a
  missing comma in `statItems`; the file/download/login stat cards and the 14
  entity chips now render, evidence at
  `docs/qa/screenshots/seeder-spread-stats.png`.

Live service: `http://127.0.0.1:8088`, QwenPaw 2.1.0, health 13/13. The model
provider `kilo/kilo-auto/free` is unreachable (agent chat may report model
unavailable), independent of platform health.
## Per-Capability Definition of Done

A feature may be changed to `completed` only when all of the following are true:

- its linked issue acceptance criteria pass with reproducible evidence;
- real persisted data is used, with simulation explicitly labeled and optional;
- empty, loading, validation, authorization, dependency, and failure states work;
- the UI, backend, Agent tool, Data Core access, artifacts, audit, and review flow
  form the applicable end-to-end path;
- focused tests and `node scripts/verify-release.mjs` pass;
- Windows and Linux behavior and version consistency are verified;
- migrations preserve existing Workspace data and have a tested rollback; and
- the progress entry contains an evidence-based note and is set to 100% only
  with status `completed`.

## Plan Integrity Check

Run the fast, offline plan check while editing the ledger:

```bash
node scripts/verify-project-plan.mjs
```

The full release gate also runs this check. It rejects duplicate or invalid
features, inconsistent status/progress combinations, missing evidence notes,
and loss of the required Data Studio or Order Studio locks/catalog entries.

### Full-platform GUI/function verification note (2026-08-25)

The logged-in full-platform acceptance pass is complete across all 11 installed
apps / Studio. Evidence:
`docs/qa/qa-report-full-gui-functional-2026-08-25.md`,
`docs/qa/ui-post-login-probe.json`,
`docs/qa/functional-interaction-probe.json`,
`docs/qa/screenshots/{post-login,functional}/*.png`.

- Real login (`admin` / `ZhizaoYun@2026`) via `/api/zhiyun-auth/login`; JWT lands in
  `localStorage.zhiyun_token` and the login layer disappears.
- 11/11 apps render structured GUI (no bare JSON, no `<pre>` leak); 11/11 run
  their core flow (load sample -> run -> non-empty result, no execution error);
  11/11 expose a usable in-app "问 Agent" drawer with an input.
- Backend unit tests all pass: 207 tests across 51 test files.
- No P0/P1/P2 defects found this pass. Two P3 polish items noted (host
  "桌面模式" onboarding toast repeats on each visit; shared Agent-dock placeholder
  text is supply-flavored in all 5 template Studio). The "功能只有 JSON / 无 GUI"
  P0 is fixed and regression-clean.
- The 17 `testing` capabilities remain `testing` pending user acceptance; the
  implementation/GUI/run path is now verified end-to-end via automation.
