# 智造云 AIOS Development Rules

These rules apply to the entire repository. Read the PRD in
`docs/product/PRD-V7.0-AIOS-2.2.0.md` before changing product behavior.

## Architecture

- 智造云 AIOS 2.2.0 is a branded build of vanilla QwenPaw 2.2.0 plus
  QwenPaw Hub (product decision 2026-09-04). This repository contains only
  launchers, branding assets, setup scripts, docs, and the runtime version
  lock — no bundled business applications.
- All business apps (PawApps, vendored plugins, the Studio suite) have been
  decoupled from this tree. They live in their own repositories and may return
  later as standalone optional add-ons; do not re-vendor them here.
- Login uses QwenPaw 2.2.0 native auth: the single-user console enforces
  `QWENPAW_AUTH_ENABLED=true` (first user registers from the console; the
  documented reset is deleting `auth.json` under the secret dir). Multi-user
  login uses QwenPaw Hub accounts (`start-hub.cmd`, port 8000). Do not
  reintroduce custom auth plugins.
- Port 8088 is the single-user console; port 8000 is the Hub. Model provider
  accounts (API keys) are managed centrally on the Hub server via its
  credential vault and projected into user runtimes as environment variables.
- Branding: user-visible QwenPaw strings in the console (single-user and Hub)
  are replaced with 智造云 AIOS by `patch-console-ui.mjs`; brand assets live in
  `branding/`. Protected technical identifiers (URLs, host APIs, paths) must
  never be rebranded.
- QwenPaw 2.2.0 is the only runtime (lock: `apps/zhizaoyunAIOS/qwenpaw.lock.json`);
  lock entries must move in lockstep with product decisions.
- Do not restore DeepSeek Harness, the enterprise service, or port 8390.

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

- Run `node scripts/verify-release.mjs` before delivery. All lock, entry,
  syntax, and branding checks invoked by that gate must pass.
- Add focused backend, frontend-state, tool, database, and runtime-interface
  tests when the changed behavior needs them. A test count alone is not proof of
  business acceptance.
- Preserve valid Windows (`.cmd`) and Linux (`.sh`) launch and maintenance
  entries. Report the impact on both platforms.
- Keep manifest and lock versions consistent (system version 2.2.0).
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
