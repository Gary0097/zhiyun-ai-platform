# Agent Note: Enterprise AI-OS execution boundary

Status: implemented

English | [中文](2026-08-21-enterprise-ai-os-execution-boundary.zh.md)

## Problem

The enterprise application starts AI work through a local bounded agent loop and through DSH sessions. Scheduled tasks, interactive work tasks, automatic demonstrations, and long-running orchestration call those paths directly, so each caller would otherwise define its own routing, status translation, and tenant requirements.

The AI-OS task model needs one stable execution boundary before existing callers migrate. Replacing either runner immediately would couple the migration to user-visible behavior and prevent the existing V2 paths from remaining available during compatibility work.

## Decision

`apps/enterprise/server/os` owns transport-neutral AI-OS execution contracts. Every execution request requires a task identifier, tenant identifier, and instruction. The execution kernel selects a registered runner and normalizes runner-specific success states into the AI-OS execution status set.

The lightweight runner adapts the existing enterprise `runAgent` operation. The DSH runner adapts a supplied session operation. Both adapters use dependency injection, so the kernel does not import either runtime and does not create a second model or session protocol.

The enterprise database initializes additive Task, Plan, Context Snapshot, Execution, Process, Checkpoint, Event, Approval, Artifact, Capability, and Capability Policy tables. Existing V2 tables and APIs remain authoritative until their callers migrate explicitly. The new tables require tenant ownership for tenant-scoped records and use idempotent `CREATE TABLE IF NOT EXISTS` migrations.

## Alternatives considered

**Replace the enterprise agent loop with DSH immediately.** The local loop supports current API and scheduled-task behavior. Immediate replacement would combine contract migration with runtime migration and make regressions harder to isolate.

**Keep independent execution records for every caller.** This preserves local simplicity but prevents one task, process, event, and audit model from spanning interactive, scheduled, and DSH work.

**Make the kernel call concrete runtimes directly.** Direct imports would make the shared contract depend on DSH transport and enterprise database details. Injected adapters keep those dependencies at the edge.

## Consequences

New AI-OS work has one place for tenant validation, runner selection, and result normalization while existing behavior remains available. Schema creation and adapter routing are verified without requiring a model provider or running HTTP service.

The boundary does not migrate WorkTask, Scheduler, Auto-run, or DSH session persistence by itself. Those callers must adopt the kernel incrementally, and old and new schedulers must not trigger the same business task concurrently. Checkpoint persistence, approval orchestration, event delivery, and business-result verification remain later consumers of the baseline tables.
