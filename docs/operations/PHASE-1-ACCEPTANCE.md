# Phase 1 PawApp Acceptance Candidate

Issue: `Gary0097/zhiyun-ai-platform#68`

## Formal external merges

1. Data Studio PR #14 merged as
   `4a586269e30d591295c1348a042479adeb570540` (v0.9.0).
2. Order Studio PR #11 merged as
   `e35312d35e5e306fa288d60ef7464294a1fef0a7` (v0.7.0).
3. The main platform lock and catalog are updated only to those formal SHAs.

Both external PRs passed `verify (ubuntu-24.04)` and
`verify (windows-2022)` before manual merge.

## Candidate scope

Data Studio features 1–6 use persisted Data Core records and now produce
traceable, reviewable risk, fusion, daily-brief and trend artifacts. Order
Studio features 7–11 cover real order input, templates, contract evidence,
consistency differences, and a persisted exception workflow with explicit
human decisions, retry/recovery and accepted-only export.

Online ERP/WMS connectors remain owned by the later Integration Hub. Other
business-domain daily summaries become available when their owning PawApps
publish stable Data Core contracts. Those dependencies are not represented as
available Phase 1 behavior.

## Acceptance state

Features 1–11 remain `testing` below 100%. Automated checks prove the versioned
contracts, persistence rules, interfaces, empty/error behavior and platform
gates; they do not replace the user's real-data acceptance. Only after that
acceptance may a follow-up change mark individual features `delivered`.

Rollback restores the previous full SHA for each PawApp. The PawApp databases
and Workspace content are retained and must not be deleted during rollback.
