# Phase 2 Shared Foundations Acceptance Candidate

Issue: `Gary0097/zhiyun-ai-platform#74`

## Formal external merge

Integration Hub PR #4 fixed the route-isolation defect found during live
browser testing and was manually merged as
`a3d90c2dba77e1d85f5c089957152bc7688e5707` (v0.1.1). The platform lock uses
only this latest formal SHA; the superseded v0.1.0 SHA is not shipped.

## Candidate scope

- Integration Hub reads real CSV/JSON, HTTPS JSON APIs and SQLite in read-only
  mode, previews mappings, validates through Data Core, requires confirmation
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
