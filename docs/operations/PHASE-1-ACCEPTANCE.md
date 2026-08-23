# Phase 1 PawApp Acceptance Record

Issue: `Gary0097/zhiyun-ai-platform#68`

## Formal external merges

1. Data Studio PR #14 merged as
   `4a586269e30d591295c1348a042479adeb570540` (v0.9.0).
2. Order Studio PR #11 merged as
   `e35312d35e5e306fa288d60ef7464294a1fef0a7` (v0.7.0).
3. The main platform lock and catalog are updated only to those formal SHAs.

The accepted capabilities were later upgraded without changing their delivery
status: Data Studio PR #15 merged as
`de291fed581e5c8d684379682351011a4be4c73a` (v0.9.1), and Order Studio PR #12
merged as `612b2a2b48ee8321da208b4aa7ebdbce22e6f939` (v0.7.1). These releases add
Chinese titles and in-app guidance while preserving the accepted data paths.

Both external PRs passed `verify (ubuntu-24.04)` and
`verify (windows-2022)` before manual merge.

## Accepted scope

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

The user completed live acceptance on 2026-08-23 with Data Studio v0.9.0,
Order Studio v0.7.0 and all six runtime health checks passing. Features 1–11
are therefore recorded as `completed` at 100%. Automated checks continue to
verify their versioned contracts, persistence rules, interfaces, empty/error
behavior and platform gates.

The accepted scope does not claim ERP/WMS online connectors or additional
business-domain daily summaries. Those remain later capabilities and do not
block acceptance of the Phase 1 scope described above.

Rollback restores the previous full SHA for each PawApp. The PawApp databases
and Workspace content are retained and must not be deleted during rollback.

Future changes follow [PawApp Upgrade Policy](./PAWAPP-UPGRADE-POLICY.md). They
create a new version and acceptance record; they do not rewrite this baseline.
