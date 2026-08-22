# Zhiyun AI-OS Development Rules

These rules apply to the entire repository. Read the PRD in
`docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`, the architecture documents,
and the applicable progress ledger before changing product behavior.

## Architecture

- QwenPaw 2.1.0 is the only runtime, desktop shell, and Agent container.
- Do not restore DeepSeek Harness, the enterprise service, or port 8390.
- Port 8088 is the only service port.
- Business features must be delivered as PawApps. This repository contains only
  system plugins, launchers, the shared Workspace contract, and version locks.
- Data Studio and Order Studio are independent repositories. Update their lock
  entries here only after the corresponding external commit is available.
- Creator is reference-only and must not be loaded as a product application.
- Do not edit generated installations under
  `apps/qwenpaw-embedded/runtime/pawapps`; change the owning repository instead.

## Branch and Scope Policy

- Never commit directly to `master`, merge automatically, or force-push shared
  branches. Use one issue, one task branch, and one pull request per change.
- Work on only one `codex-ready` issue at a time, choosing the highest declared
  priority. Confirm current `master` and merged pull requests before coding.
- Keep the implementation within the issue acceptance criteria. Stop after the
  pull request is opened and wait for human review and merge.
- Do not claim a PRD capability is available unless its real data path, Agent
  tool, backend, and user-facing flow form a demonstrable end-to-end result.
- Do not use hard-coded or fabricated demo data as evidence of implementation.
  Empty data must remain visibly empty unless the user explicitly selects a
  clearly labeled simulation mode.

## Required Validation

- Run `node scripts/verify-release.mjs` before delivery. All existing Python
  tests, runtime semantic-health checks, lock checks, and maintenance checks
  invoked by that gate must pass.
- Add focused backend, frontend-state, tool, database, and runtime-interface
  tests when the changed behavior needs them. A test count alone is not proof of
  business acceptance.
- Preserve valid Windows (`.cmd`) and Linux (`.sh`) launch and maintenance
  entries. Report the impact on both platforms.
- Keep manifest, catalog, lock, and progress-ledger versions consistent.
- If the full gate cannot run because of an external service or network limit,
  run all unaffected checks and report the exact limitation; do not report the
  gate as passed.

## Data and Operational Safety

- Never delete user Workspace data or overwrite a database during an upgrade.
- Database migrations must be backward-aware, tested against existing data, and
  include an explicit rollback or recovery method.
- Move incompatible third-party plugins only to recoverable backups. Do not
  silently destroy user-installed content.
- Never expose credentials, tokens, customer data, or other secrets in source,
  fixtures, logs, commits, issues, or pull requests.
- Preserve audit coverage and catastrophic-operation blocking. Never weaken a
  safety control merely to make a test pass.
- Avoid destructive Git operations and do not rewrite published history.

## Review Rules

Review pull requests for runtime regressions, fake implementations, hard-coded
demo data, incomplete end-to-end paths, missing tests, Windows/Linux drift,
version drift, database or Workspace safety, secret exposure, weakened audit or
catastrophic-operation controls, and gaps against the linked issue and PRD.
Treat an unsupported claim of completion as a defect.

## Delivery Contract

Every pull request must identify:

- the issue and implemented capability;
- changed files and important design decisions;
- exact tests executed and their results;
- known limitations and remaining PRD gaps;
- Windows and Linux impact;
- data, deployment, and security risks; and
- a practical rollback method.
