# Phase 0 Continuous-development Controls

Issue: `Gary0097/zhiyun-ai-platform#66`

## Implemented controls

All three repositories now carry repository-specific `AGENTS.md` rules, a
Codex-ready issue form, a pull-request template, and a release workflow that
runs on Ubuntu 24.04 and Windows 2022. The two PawApp repositories also expose
`python scripts/verify_release.py` as their local full gate.

The shared task branch is `codex/issue-66-phase0-controls`. Data Studio PR #13
merged as `c0b80dffd3f4d89855958ce95fb346c39d3e2392`; Order Studio PR #10 merged as
`4cb728637ef22ee01e9bb5528a18fe9375ca8e09`. Both PRs passed their Ubuntu and
Windows checks before manual merge.

GitHub labels created in each repository are `codex-ready`, `priority-p0`,
`priority-p1`, `priority-p2`, plus its repository ownership label. Issue #66 is
marked `codex-ready`, `priority-p0`, and `repo-platform`.

## Administrator-managed verification

GitHub branch protection was enabled and API-verified on 2026-08-23 for
`zhiyun-ai-platform:master`, `zhiyun-data-studio:main`, and
`zhiyun-order-studio:main`. Each protected branch:

1. requires a pull request and an up-to-date branch before merge;
2. requires `verify (ubuntu-24.04)` and `verify (windows-2022)`;
3. requires all review conversations to be resolved;
4. applies the rules to administrators; and
5. blocks force pushes and branch deletion.

Required approving reviews are intentionally set to zero because the current
repository owner cannot approve their own pull request. A pull request and a
manual human merge are still mandatory; no automation may merge a change.
Codex Cloud repository access and review permissions remain hosting settings
that an administrator must periodically verify.

Source validation cannot prove remote hosting settings from a clean checkout. Run
`node scripts/verify-phase0-controls.mjs` after PawApps are materialized to
verify the versioned portion of Phase 0.

## Merge order and rollback

External PawApp PRs merge first. Only their formal merge SHAs are written to
`pawapps.lock.json`; the main platform PR merges last. Roll back by reverting
the relevant PR and restoring the previous full SHA in the main lock. No
Workspace or database content is deleted by these controls.
