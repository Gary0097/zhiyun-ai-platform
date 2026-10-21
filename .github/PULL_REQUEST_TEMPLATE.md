## Linked issue

Closes #

## Implemented capability

<!-- Describe the user-visible end-to-end result. Do not claim incomplete PRD work. -->

## Changed files and design

<!-- Summarize important files, interfaces, real-data paths, and design decisions. -->

## Acceptance evidence

<!-- Map each issue acceptance criterion to a test, screenshot, API result, or other reproducible evidence. -->

## Tests executed

| Command | Platform | Result |
| --- | --- | --- |
| `node scripts/verify-release.mjs` | Windows / Linux | Not run |

## Known limitations and PRD gaps

<!-- Write "None" only after checking the linked issue and applicable PRD/progress ledger. -->

## Windows and Linux impact

- Windows:
- Linux:

## Risk and data safety

<!-- Cover Workspace/database preservation, migrations, audit controls, security, deployment, and secrets. -->

## Rollback

<!-- Give exact, non-destructive recovery steps. Never propose deleting the user Workspace. -->

## Author checklist

- [ ] This pull request addresses one issue and does not merge or deploy itself.
- [ ] No hard-coded or fabricated data is presented as a completed feature.
- [ ] Real-data, empty, error, persistence, and end-to-end paths were considered.
- [ ] Versions, manifests, catalog entries, locks, and progress ledgers are consistent.
- [ ] Focused tests and the release gate were run, or exact limitations are documented.
- [ ] Windows and Linux launch/maintenance impact was checked.
- [ ] Workspace/database data is preserved and rollback is recoverable.
- [ ] Audit and catastrophic-operation blocking remain intact.
- [ ] No secrets or customer data appear in code, logs, fixtures, or this PR.
