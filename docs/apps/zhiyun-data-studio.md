# 企业数据分析中心（zhiyun-data-studio）

> 分类：数据分析 ｜ 版本：0.9.1 ｜ 路由：/apps/zhiyun-data-studio
> 仓库：https://github.com/Gary0097/zhiyun-data-studio

## 1. 需求概述

企业数据分析中心是智云 AI-OS 的数据消费与洞察入口，承接统一数据中心（Data Core）的真实业务数据，面向管理人员与业务分析师提供客户/订单风险、指标预警、跨域融合分析、经营日报等可追溯的洞察结论。

## 2. 功能清单

- 实时客户订单进度看板（能力 1）
- 客户交付风险智能预警（能力 2）
- 多源数据自动采集（能力 3）
- 跨部门数据融合加工（能力 4）
- 企业关键数据日看板（能力 5）
- 关键指标趋势分析（能力 6）
- 智能体对话板块（应用内与默认智能体对话）
- 问数能力（默认智能体通过 Skill/Tool 执行自然语言问数并返回可溯源结论）

## 3. 数据路径

唯一数据源为 Data Core。用户可在“统一数据中心”真实导入（Excel/CSV）或明确选择“模拟数据”生成订单与生产数据；每次分析都携带来源标识（real / simulated）与 data_mode（demo / production），分析结果作为 Artifact 落库，可与 Data Core 记录逐条追溯。空数据时显示空状态，不渲染占位图表。

## 4. API 端点

- `GET/POST /health`
- `GET/POST /parse`
- `GET/POST /risk/analyze`
- `GET/POST /orders/normalize`
- `GET/POST /agent/context`
- `GET/POST /trends/analyze`
- `GET/POST /brief/daily`
- `GET/POST /fusion/analyze`
- `GET/POST /artifacts`
- `GET/POST /artifacts/{id}`
- `GET/POST /artifacts/{id}/reviews`
- `GET/POST /artifacts/{id}/export`

## 5. Agent / Skill 接入与问数

本应用对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。

- **Skill / Tool 暴露**：应用把「客户/订单交付风险、关键指标趋势与经营日报」等能力以 Skill 形式暴露给默认智能体，作为其可调用的问数与业务工具。
- **问数路径**：用户在对话中提出自然语言问题 → 默认智能体调用应用（或 Data Core）的查询工具 → 返回可溯源结论（含 `record_id` + `source_type` + `data_mode`）。
- **可审阅工件**：问数结果与业务分析必须能生成可接受/驳回/导出的 Artifact，不能只有临时文本。

已登记的 Agent 可调用工具（部分）：`/agent/context（上下文）`、`/fusion/analyze`、`/trends/analyze`、`/brief/daily`。

把「订单交付风险分析」「关键指标趋势」「经营日报」等能力封装为 Skill，供默认智能体在对话中按自然语言问数并返回可追溯结论。

## 6. UI 入口

“我的应用 → 数据分析 → 企业数据分析中心”，路由 /apps/zhiyun-data-studio。

应用内需提供「智能体对话」板块入口（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），可直接与默认智能体对话并查看问数结果。

## 7. 验收标准

- 所有图表与数字必须来自 Data Core 底层记录，禁止硬编码。
- 支持按时间范围切换，趋势/风险/日报随底层数据同步变化。
- 分析结果必须可生成 Artifact，支持接受/驳回与导出。
- demo 与 production 数据严格隔离，来源可追溯。
- 应用内「智能体对话」板块可用，能直接与默认智能体对话并查看问数结果。
- 问数结果必须可追溯到底层记录（`record_id` + `source_type`），demo / production 严格隔离。
- 无权限的问数或操作必须被阻断并写入审计，禁止跨环境读取或修改数据。

---

> 本文件由 `docs/apps/README.md` 索引；产品级 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。
