# 系统集成中心（zhiyun-integration-hub）

> 分类：系统集成 ｜ 版本：0.2.1 ｜ 路由：/apps/zhiyun-integration-hub
> 仓库：https://github.com/Gary0097/zhiyun-integration-hub

## 1. 需求概述

系统集成中心面向实施与运维，通过 CSV/JSON/HTTPS API/只读 SQLite 连接器接入外部系统，提供字段映射预览、同步 Run/Trace/错误/重试，并将同步结果提交到 Data Core 记账。

## 2. 功能清单

- 现有系统数据接口开发（能力 29）
- 智能体对话板块（应用内与默认智能体对话）
- 问数能力（默认智能体通过 Skill/Tool 执行自然语言问数并返回可溯源结论）

## 3. 数据路径

数据来自真实外部源（连接器）或用户明确提供的文件/API。同步过程包含解析、字段映射、预览, 提交/回滚；每次 Run 都有 Trace，可重试。

## 4. API 端点

- `GET/POST /health`
- `GET/POST /connectors`
- `GET/POST /connectors/health`
- `GET/POST /files/parse`
- `GET/POST /sources/read`
- `GET/POST /sync/preview`
- `GET/POST /sync/{run_id}/commit`
- `GET/POST /sync/{run_id}/retry`

## 5. Agent / Skill 接入与问数

本应用对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。

- **Skill / Tool 暴露**：应用把「连接器健康、字段映射、同步 Run/Trace 与重试」等能力以 Skill 形式暴露给默认智能体，作为其可调用的问数与业务工具。
- **问数路径**：用户在对话中提出自然语言问题 → 默认智能体调用应用（或 Data Core）的查询工具 → 返回可溯源结论（含 `record_id` + `source_type` + `data_mode`）。
- **可审阅工件**：问数结果与业务分析必须能生成可接受/驳回/导出的 Artifact，不能只有临时文本。

已登记的 Agent 可调用工具（部分）：`/connectors`、`/files/parse`、`/sources/read`、`/sync/preview`、`/sync/{run_id}/commit`、`/sync/{run_id}/retry`。

把「连接器管理」「文件解析」「字段映射预览」「同步提交/重试」等能力封装为 Skill，供默认智能体做同步/集成问数并保留 Trace。

## 6. UI 入口

“我的应用 → 系统集成 → 系统集成中心”，路由 /apps/zhiyun-integration-hub。

应用内需提供「智能体对话」板块入口（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），可直接与默认智能体对话并查看问数结果。

## 7. 验收标准

- 连接器必须支持真实字段识别与映射预览。
- 每次同步必须产生可追溯的 Run/Trace 与错误记录。
- 同步提交到 Data Core 需记录 data_mode 与 source_type。
- 失败允许重试，不允许静默丢失数据。
- 应用内「智能体对话」板块可用，能直接与默认智能体对话并查看问数结果。
- 问数结果必须可追溯到底层记录（`record_id` + `source_type`），demo / production 严格隔离。
- 无权限的问数或操作必须被阻断并写入审计，禁止跨环境读取或修改数据。

---

> 本文件由 `docs/apps/README.md` 索引；产品级 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。
