# Architecture Decision: Pivot the AI-OS runtime to QwenPaw 2.1.0

- Status: Accepted
- Date: 2026-08-21
- Upstream: `agentscope-ai/QwenPaw`, branch `release/v2.1.0`, commit `e4995dcf516d27400fbc33891aa3dcbcf79acc7a`

## Decision

The enterprise AI-OS will use QwenPaw as its Agent runtime, primary chat, session/memory system, file workspace, plugin host, PawApp runtime, scheduler integration and OS shell.

The current enterprise Node service remains the business control plane. It owns tenant identity, business records, enterprise validation, high-risk write controls, audit and reporting. QwenPaw reaches it through a dedicated Tool/MCP gateway and PawApp backends.

DeepSeek Harness is frozen as a legacy migration source. No new product capability may depend on its HTTP envelope, event mux, iframe UI or workspace convention.

## Why

The current architecture has a working enterprise data plane but its primary chat and feature demonstrations do not meet product acceptance. Continuing to expand the custom runtime would duplicate capabilities already provided by QwenPaw 2.1.0: long-running sessions, memory, files, Skills, Plugins, MCP, multi-agent execution, scheduled work, checkpoints, sandboxing, Tool Guard and PawApps.

QwenPaw also exposes branding and application extension points. Header logo/title and primary color can be replaced through plugin slots, while PawApps can register routes, backend APIs and OS applications without turning the enterprise product into a long-lived fork of the upstream console.

## Integration rules

1. Prefer configuration, plugins, PawApps, slots and public APIs over upstream source edits.
2. Pin the upstream version and record its commit in every release.
3. Preserve Apache-2.0 licensing and upstream notices.
4. Never trust a tenant identifier supplied by PawApp browser code; resolve tenant identity server-side.
5. Keep system safety in QwenPaw Sandbox/Tool Guard and business safety in the enterprise gateway.
6. Every business action must carry Session, Task, Execution and Trace correlation where applicable.
7. Do not run DSH and QwenPaw consumers for the same scheduled task.
8. A module is migrated only when its real input-to-artifact E2E passes; a menu entry or static demonstration is not migration.

## Target repository shape

```text
apps/
  enterprise/                 Existing business control plane
  qwenpaw-enterprise/         QwenPaw integration and launch assets
    branding/                 Tenant-safe brand configuration adapter
    gateway/                  Enterprise Tool/MCP bridge
    plugins/
      zhiyun-brand/           Header, title, theme and OS brand plugin
      task-center/            P0 PawApp
      knowledge-assistant/    P0 PawApp
      ai-os-monitor/          P0 PawApp
    tests/                    Contract and E2E acceptance
docs/product/
  AI-OS-PRD-V4.0-QwenPaw.md
```

## Migration impact

Reusable assets:

- enterprise tenant and business records;
- Task, Execution, Process, Checkpoint and Artifact projections;
- high-risk Tool controls and immutable audit;
- business tools, generators and monitor queries.

Replaced assets:

- DSH iframe chat;
- DSH session adapter and runner path;
- the custom lightweight loop as the primary interactive runtime;
- feature chips and static demonstrations;
- hardcoded product branding.

## First implementation slice

Phase Q0 delivers a reproducible QwenPaw 2.1.0 launch, a version/health contract, a brand-plugin proof, an enterprise gateway skeleton and tests that fail if DSH becomes a new dependency. Phase Q1 then makes QwenPaw chat the accepted primary interaction path.

