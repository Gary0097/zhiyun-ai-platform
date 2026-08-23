# Phase 2 Shared Foundations Acceptance Candidate

Issue: `Gary0097/zhiyun-ai-platform#74`

## Formal external merge

System Integration Center PR #6 added automatic UTF-8, GBK/GB18030 and UTF-16 CSV decoding
on top of the guided Chinese workflow and was manually merged as
`b0297c23dd9865cb6d3f565cc0253f47be223f60` (v0.2.1).
It replaces handwritten connector and mapping JSON with source-specific forms
and automatic field matching. The platform lock uses only this formal SHA.

## Candidate scope

- The system integration center reads real CSV/JSON, HTTPS JSON APIs and SQLite
  in read-only mode, automatically proposes mappings, validates through Data Core, requires confirmation
  before commit, and retains Run/Trace/batch/failure/retry evidence.
- Data Core v0.7.0 records idempotent migrations, reports semantic integrity
  and disk health, creates checksum-verified backups, optionally encrypts them
  with AES-GCM, and creates a safety backup before confirmed recovery.
- Audit v1.3.0 redacts secret-bearing keys and inline credentials/personal
  identifiers, maintains a tamper-evident event chain, and blocks unconfirmed
  external sends/writes in addition to catastrophic operations.
- PawApps can be reconstructed offline from full-SHA Git bundles. Health covers
  the desktop, catalog, Data Core integrity, audit integrity and all three
  installed PawApps with runtime/catalog version comparison.

## Acceptance boundary

Capabilities 29 and 31 remain `testing` at 95%. Automated tests and the full
release gate do not replace live acceptance. Vendor-specific ERP/WMS adapters,
scheduled sync and external-system writes are extensions selected for a real
target system; v0.1 does not claim them generically.

Rollback restores the previous platform commit and PawApp lock. Data Core
recovery always verifies the backup and creates a safety backup first; Workspace
data, Integration Hub run evidence and cached bundles must not be deleted.
