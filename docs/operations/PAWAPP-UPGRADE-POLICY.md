# PawApp Upgrade Policy

This policy applies to upgrades of accepted features 1–11 and later PawApps.
The Phase 1 acceptance record is an immutable release baseline: an upgrade
creates new versioned evidence instead of rewriting the historical result.

## Version meaning

- Patch: backward-compatible defect, security or reliability fixes.
- Minor: backward-compatible feature or workflow improvements.
- Major: breaking API, Data Core schema, artifact, Workspace or behavior changes.

Every release states its compatibility range, migration, rollback and retained
data behavior. Database migrations are additive where practical, preserve user
data, and are tested in both forward and rollback paths.

## Required merge order

1. Create one issue and use the same task number/name on every involved repo.
2. Develop and test the owning external PawApp on a task branch. Never develop
   directly on `master` or `main`.
3. Pass focused tests plus Windows and Linux checks, then request manual review
   and merge of the external PawApp PR.
4. Obtain the formal merge commit SHA. Unmerged branch SHAs are never locked.
5. In a separate main-repository branch, update the PawApp semantic version,
   catalog metadata and `pawapps.lock.json` to that formal SHA.
6. Materialize the locked PawApp, run the complete main release gate, then
   request manual review and merge of the platform PR.

Automatic merge is prohibited. A release is not marked available merely
because it is installed. New or expanded capabilities remain `testing` until
their acceptance criteria and user test pass; already accepted capabilities
remain `completed` unless a verified regression is reported. Regressions are
tracked as defects and reflected in runtime health rather than silently
rewriting historical acceptance.

Patch releases that do not change accepted behavior may retain the capability's
`completed` state when regression evidence passes. Minor or major releases with
new user-visible behavior add separately testable acceptance evidence; breaking
major releases also require an explicit migration rehearsal and rollback test.
