# Zhiyun AI-OS Project Plan

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
- 1 in development;
- 0 in testing; and
- 17 planned.

Therefore the product is not complete. Percentages are planning indicators, not
acceptance evidence. A capability becomes `completed` only at 100% after its
real-data path, UI, backend, Agent tools, persistence, error/empty states,
platform checks, and issue acceptance criteria have passed.

## Repository Ownership

| Area | Owning repository | Integration into AI-OS |
| --- | --- | --- |
| QwenPaw runtime, launchers, Data Core, audit, app discovery | `Gary0097/zhiyun-ai-platform` | Direct release gate |
| Features 1–6 | `Gary0097/zhiyun-data-studio` | Update `pawapps.lock.json` after its PR is merged |
| Features 7–11 | `Gary0097/zhiyun-order-studio` | Update `pawapps.lock.json` after its PR is merged |
| Future business studios | A dedicated PawApp repository per studio | Add catalog metadata and a full-SHA lock only after an installable release exists |

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

### Phase 3 — Add future PawApps by business value

Build one installable PawApp and one accepted capability at a time:

1. Service Studio (features 12–15).
2. Supply Studio (features 16 and 30).
3. Sales Studio (features 17–19).
4. Finance Studio (features 20–22).
5. People Studio (features 23, 24, and 26–28).
6. Complete the Workspace knowledge workflow (feature 25).

Each new studio requires its own repository, manifest, tests, application card,
health contract, versioned data contract, rollback method, and locked full SHA.

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
