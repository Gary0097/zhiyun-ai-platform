# Agent Note: 企业 AI-OS 统一执行边界

Status: implemented

[English](2026-08-21-enterprise-ai-os-execution-boundary.md) | 中文

## Problem

企业应用同时通过平台内受限 Agent 循环和 DSH Session 启动 AI 工作。定时任务、交互式工作任务、自动演示和长任务编排直接调用不同执行路径，因此各调用方可能分别定义路由、状态转换和租户要求。

AI-OS 任务模型需要先建立稳定的统一执行边界，再迁移现有调用方。立即替换任一 Runner 会把迁移与用户可见行为绑定，也会让现有 V2 路径无法在兼容改造期间继续工作。

## Decision

`apps/enterprise/server/os` 负责与传输方式无关的 AI-OS 执行约定。每个执行请求必须包含任务标识、租户标识和指令。Execution Kernel 选择已注册的 Runner，并把不同 Runner 的成功状态统一转换为 AI-OS 执行状态。

轻量 Runner 适配现有企业平台 `runAgent` 操作，DSH Runner 适配外部注入的 Session 操作。两个适配器均使用依赖注入，因此 Kernel 不导入任一运行时，也不建立第二套模型或 Session 协议。

企业数据库以增量方式初始化 Task、Plan、Context Snapshot、Execution、Process、Checkpoint、Event、Approval、Artifact、Capability 和 Capability Policy 表。来自业务来源的任务在租户范围内只保留一个来源映射。现有 V2 表和 API 在调用方逐步迁移期间继续作为兼容投影。

WorkTask 是首个完成迁移的调用方。`TaskService` 将每个旧 WorkTask 幂等映射到一个 AI-OS Task，通过 Kernel 执行，并为每次尝试持久化新的 Execution、Process 和生命周期 Event。旧 WorkTask 行继续回写原有状态、Trace、输出和耗时字段，因此本阶段不会改变既有 UI 与 API 约定。

现有 Scheduler 是第二个完成迁移的调用方。Cron、Interval、Condition 判断、Job Lock、旧 Job 记录、重试和死信行为继续保留在 `scheduler.js`，仅替换 Worker 执行边界。每次调度尝试都会成为独立的 AI-OS Execution 与 Process，记录重试次数，并保存可恢复的完成 Checkpoint；准备重试时，在下一次尝试前额外保存 `retry.scheduled` Checkpoint。

Auto-run 是第三个完成迁移的调用方。现有 DSH HTTP 信封、复用 WebSocket 审批处理、持久化 Session Key 和旧可观测记录保持不变。每个角色、报告、功能演示或多 Agent Session 映射为一个有来源的 AI-OS Task，每个 DSH Turn 成为独立 Execution 与 Process，并与旧执行记录共享 Trace 标识；`session.turn.completed` Checkpoint 保存 Session 标识用于冷恢复。

高风险 Tool 控制独立于可选的 Capability 和 Approval 模型。无人值守执行禁止敏感写入；交互写入保留现有轻量确认约定，之后还需经过租户熔断开关、分钟级写入限流、参数结构限制和具体业务校验。高风险放行和拒绝决策都会形成与执行 Trace 关联的审计记录。

## Alternatives considered

**立即用 DSH 替换企业平台 Agent 循环。** 本地循环承载现有 API 和定时任务行为；立即替换会把执行约定迁移和运行时迁移合并，增加回归定位难度。

**让各调用方继续维护独立执行记录。** 这种方式局部简单，但无法用统一的任务、进程、事件和审计模型覆盖交互任务、定时任务与 DSH 工作。

**让 Kernel 直接调用具体运行时。** 直接导入会让共享约定依赖 DSH 传输细节和企业数据库实现；注入式适配器把这些依赖保留在边缘。

## Consequences

新的 AI-OS 工作拥有统一的租户校验、Runner 选择、结果标准化和持久化任务生命周期入口，同时现有行为继续可用。Task 查询 API 按租户隔离，可读取 Execution、Process、Event 和 Artifact，且不会暴露其他租户的数据。

Auto-run 与 DSH Session 历史现已投影到统一运行时。本阶段不新增与现有 Scheduler 竞争的调度器，调度策略继续由旧 Scheduler 管理，`job_lock` 仍是唯一并发保护。Checkpoint 已能记录尝试和 Session Turn 边界，但尚不能从模型 Turn 中间恢复。Capability 管理和 Approval 审批编排明确不在当前产品范围内；事件投递和业务结果验证仍留待后续。删除旧 WorkTask 不会擦除其 AI-OS 运行历史。
