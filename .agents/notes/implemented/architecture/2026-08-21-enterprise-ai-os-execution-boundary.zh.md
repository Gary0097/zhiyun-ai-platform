# Agent Note: 企业 AI-OS 统一执行边界

Status: implemented

[English](2026-08-21-enterprise-ai-os-execution-boundary.md) | 中文

## Problem

企业应用同时通过平台内受限 Agent 循环和 DSH Session 启动 AI 工作。定时任务、交互式工作任务、自动演示和长任务编排直接调用不同执行路径，因此各调用方可能分别定义路由、状态转换和租户要求。

AI-OS 任务模型需要先建立稳定的统一执行边界，再迁移现有调用方。立即替换任一 Runner 会把迁移与用户可见行为绑定，也会让现有 V2 路径无法在兼容改造期间继续工作。

## Decision

`apps/enterprise/server/os` 负责与传输方式无关的 AI-OS 执行约定。每个执行请求必须包含任务标识、租户标识和指令。Execution Kernel 选择已注册的 Runner，并把不同 Runner 的成功状态统一转换为 AI-OS 执行状态。

轻量 Runner 适配现有企业平台 `runAgent` 操作，DSH Runner 适配外部注入的 Session 操作。两个适配器均使用依赖注入，因此 Kernel 不导入任一运行时，也不建立第二套模型或 Session 协议。

企业数据库以增量方式初始化 Task、Plan、Context Snapshot、Execution、Process、Checkpoint、Event、Approval、Artifact、Capability 和 Capability Policy 表。在调用方明确迁移前，现有 V2 表和 API 继续作为权威来源。新表要求租户范围内的记录必须绑定租户，并通过幂等的 `CREATE TABLE IF NOT EXISTS` 完成迁移。

## Alternatives considered

**立即用 DSH 替换企业平台 Agent 循环。** 本地循环承载现有 API 和定时任务行为；立即替换会把执行约定迁移和运行时迁移合并，增加回归定位难度。

**让各调用方继续维护独立执行记录。** 这种方式局部简单，但无法用统一的任务、进程、事件和审计模型覆盖交互任务、定时任务与 DSH 工作。

**让 Kernel 直接调用具体运行时。** 直接导入会让共享约定依赖 DSH 传输细节和企业数据库实现；注入式适配器把这些依赖保留在边缘。

## Consequences

新的 AI-OS 工作拥有统一的租户校验、Runner 选择和结果标准化入口，同时现有行为继续可用。Schema 创建和适配器路由无需模型 Provider 或运行中的 HTTP 服务即可验证。

该边界本身不会迁移 WorkTask、Scheduler、Auto-run 或 DSH Session 持久化。调用方需要逐步接入 Kernel，且新旧调度器不得同时触发同一个业务任务。Checkpoint 持久化、审批编排、事件投递和业务结果验证将在后续阶段使用这些基线表。
