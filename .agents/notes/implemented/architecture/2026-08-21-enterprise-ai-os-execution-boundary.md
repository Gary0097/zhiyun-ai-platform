# Agent Note: Enterprise AI-OS execution boundary

Status: implemented

English | [中文](2026-08-21-enterprise-ai-os-execution-boundary.zh.md)

## Problem

The enterprise application starts AI work through a local bounded agent loop and through DSH sessions. Scheduled tasks, interactive work tasks, automatic demonstrations, and long-running orchestration call those paths directly, so each caller would otherwise define its own routing, status translation, and tenant requirements.

The AI-OS task model needs one stable execution boundary before existing callers migrate. Replacing either runner immediately would couple the migration to user-visible behavior and prevent the existing V2 paths from remaining available during compatibility work.

## Decision

`apps/enterprise/server/os` owns transport-neutral AI-OS execution contracts. Every execution request requires a task identifier, tenant identifier, and instruction. The execution kernel selects a registered runner and normalizes runner-specific success states into the AI-OS execution status set.

The lightweight runner adapts the existing enterprise `runAgent` operation. The DSH runner adapts a supplied session operation. Both adapters use dependency injection, so the kernel does not import either runtime and does not create a second model or session protocol.

The enterprise database initializes additive Task, Plan, Context Snapshot, Execution, Process, Checkpoint, Event, Approval, Artifact, Capability, and Capability Policy tables. Source-backed tasks have one tenant-scoped source mapping. Existing V2 tables and APIs remain available as compatibility projections while callers migrate explicitly.

WorkTask is the first migrated caller. `TaskService` maps each legacy WorkTask idempotently to one AI-OS Task, runs it through the kernel, and persists a new Execution, Process, and lifecycle Events for every attempt. The legacy WorkTask row continues to receive its former status, trace, output, and latency fields so the existing UI and API contract do not change during this phase.

The existing Scheduler is the second migrated caller. Cron, interval, condition evaluation, job locking, legacy Job records, retries, and dead-letter behavior remain in `scheduler.js`; only the worker execution boundary changes. Each scheduler attempt becomes a separate AI-OS Execution and Process, records its retry count, and saves a resumable completion Checkpoint. A retry decision saves an additional `retry.scheduled` Checkpoint before the next attempt.

## Alternatives considered

**Replace the enterprise agent loop with DSH immediately.** The local loop supports current API and scheduled-task behavior. Immediate replacement would combine contract migration with runtime migration and make regressions harder to isolate.

**Keep independent execution records for every caller.** This preserves local simplicity but prevents one task, process, event, and audit model from spanning interactive, scheduled, and DSH work.

**Make the kernel call concrete runtimes directly.** Direct imports would make the shared contract depend on DSH transport and enterprise database details. Injected adapters keep those dependencies at the edge.

## Consequences

New AI-OS work has one place for tenant validation, runner selection, result normalization, and durable task lifecycle state while existing behavior remains available. The Task query API is tenant-scoped and exposes executions, processes, events, and artifacts without exposing another tenant's records.

Auto-run and DSH session persistence still require incremental migration. Scheduler policy remains in the existing scheduler instead of introducing a competing scheduler, so `job_lock` continues to be the single concurrency guard. Checkpoints now capture attempt boundaries but do not yet resume an interrupted model turn; approval orchestration, event delivery, and business-result verification remain later consumers. Deleting a legacy WorkTask does not erase its AI-OS runtime history.
