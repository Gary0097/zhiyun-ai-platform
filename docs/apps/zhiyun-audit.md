# 安全审计中心（zhiyun-audit）

> 分类：系统组件 ｜ 版本：1.3.0 ｜ 路由：/apps/zhiyun-audit
> 仓库：平台内置（无独立仓库）

## 1. 需求概述

安全审计中心面向安全与运维，提供 Tool 调用审计的可视化、成功/失败/重试统计与灾难性操作阻断，支撑安全审查、问题追踪与高风险操作防护。

## 2. 功能清单

- Tool 调用审计与可视化
- 成功/失败/重试统计
- Trace 下钻
- 灾难性操作阻断与留痕
- 智能体对话板块（应用内与默认智能体对话）
- 问数能力（默认智能体通过 Skill/Tool 执行自然语言问数并返回可溯源结论）

## 3. 数据路径

数据来自真实 Agent Tool 调用记录，包含状态、Trace、执行元数据。审计统计必须由底层调用记录聚合，禁止静态数字。

## 4. API 端点

- `GET/POST /integrity`
- `GET/POST /events`

## 5. Agent / Skill 接入与问数

本应用对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。

- **Skill / Tool 暴露**：应用把「Tool 调用审计、成功/失败/重试统计与 Trace 下钻」等能力以 Skill 形式暴露给默认智能体，作为其可调用的问数与业务工具。
- **问数路径**：用户在对话中提出自然语言问题 → 默认智能体调用应用（或 Data Core）的查询工具 → 返回可溯源结论（含 `record_id` + `source_type` + `data_mode`）。
- **可审阅工件**：问数结果与业务分析必须能生成可接受/驳回/导出的 Artifact，不能只有临时文本。

已登记的 Agent 可调用工具（部分）：`/integrity`、`/events`。

作为横向能力向各业务工具有偿提供调用记录、阻断与审计查询，供默认智能体做审计问数并满足 Data Integrity。

## 6. UI 入口

“我的应用 → 系统组件 → 安全审计中心”，路由 /apps/zhiyun-audit。

应用内需提供「智能体对话」板块入口（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），可直接与默认智能体对话并查看问数结果。

## 7. 验收标准

- Tool 调用统计必须与底层记录一致。
- 失败/重试需可下钻到单条 Trace。
- 灾难性操作必须被阻断并留痕。
- 统计结果只能在真实数据范围内展示。
- 应用内「智能体对话」板块可用，能直接与默认智能体对话并查看问数结果。
- 问数结果必须可追溯到底层记录（`record_id` + `source_type`），demo / production 严格隔离。
- 无权限的问数或操作必须被阻断并写入审计，禁止跨环境读取或修改数据。

---

> 本文件由 `docs/apps/README.md` 索引；产品级 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。
