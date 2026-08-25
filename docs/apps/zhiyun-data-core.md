# 统一数据中心（zhiyun-data-core）

> 分类：系统组件 ｜ 版本：0.8.0 ｜ 路由：/apps/zhiyun-data-core
> 仓库：平台内置（无独立仓库）

## 1. 需求概述

统一数据中心是智云 AI-OS 的数据底座，提供数据建模、schema 校验、批量导入/导出、数据集管理、备份/恢复与现场数据模拟（orders/production）；所有业务应用共享此数据源。

## 2. 功能清单

- 数据建模与 Schema 校验
- 批量导入/导出与预览
- 数据集管理与备份恢复
- 现场模拟数据生成（orders / production）
- demo / production 与 real / simulated 环境隔离
- 智能体对话板块（应用内与默认智能体对话）
- 问数能力（默认智能体通过 Skill/Tool 执行自然语言问数并返回可溯源结论）

## 3. 数据路径

同时支持“真实导入”（Excel/CSV/连接器）与“模拟数据”（generate_orders/generate_production）。所有数据带 data_mode（demo/production）与 source_type（real/simulated），写入默认 demo，上下文接口支持 env_id/data_mode/start_date/end_date。

## 4. API 端点

- `GET/POST /health`
- `GET/POST /backups`
- `GET/POST /context`
- `GET/POST /entities`
- `GET/POST /parse`
- `GET/POST /schemas`
- `GET/POST /schemas/{entity}`
- `GET/POST /schemas/{entity}/fields`
- `GET/POST /schemas/{entity}/fields/{field_name}`
- `GET/POST /imports/{entity}/preview`
- `GET/POST /imports/{entity}/commit`
- `GET/POST /simulate/orders`
- `GET/POST /simulate/production`
- `GET/POST /records/{entity}`
- `GET/POST /orders`
- `GET/POST /batches`
- `GET/POST /batches/{batch_id}/rollback`

## 5. Agent / Skill 接入与问数

本应用对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。

- **Skill / Tool 暴露**：应用把「企业数据查询、Schema 建模、批量导入与模拟数据」等能力以 Skill 形式暴露给默认智能体，作为其可调用的问数与业务工具。
- **问数路径**：用户在对话中提出自然语言问题 → 默认智能体调用应用（或 Data Core）的查询工具 → 返回可溯源结论（含 `record_id` + `source_type` + `data_mode`）。
- **可审阅工件**：问数结果与业务分析必须能生成可接受/驳回/导出的 Artifact，不能只有临时文本。

已登记的 Agent 可调用工具（部分）：`/context`、`/schemas`、`/parse`、`/imports`、`/records`、`/simulate`。

作为数据底座向上暴露「查询/建模/导入/模拟」Skill，供全平台默认智能体做企业数据问数并始终携带 `record_id`、`source_type` 与 `data_mode`。

## 6. UI 入口

“我的应用 → 系统组件 → 统一数据中心”，路由 /apps/zhiyun-data-core。

应用内需提供「智能体对话」板块入口（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），可直接与默认智能体对话并查看问数结果。

## 7. 验收标准

- schema 与实体必须可创建、校验、导入/导出。
- data_mode 与 source_type 必须贯穿所有读写。
- 备份/恢复与回滚必须可用且不丢失用户数据。
- 模拟数据必须明确标识，禁止冒充真实数据。
- 应用内「智能体对话」板块可用，能直接与默认智能体对话并查看问数结果。
- 问数结果必须可追溯到底层记录（`record_id` + `source_type`），demo / production 严格隔离。
- 无权限的问数或操作必须被阻断并写入审计，禁止跨环境读取或修改数据。

---

> 本文件由 `docs/apps/README.md` 索引；产品级 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。
