# 销售客户中心（zhiyun-sales-studio）

> 分类：销售客户 ｜ 版本：0.1.0 ｜ 路由：/apps/zhiyun-sales-studio
> 仓库：https://github.com/Gary0097/zhiyun-sales-studio

## 1. 需求概述

销售客户中心面向销售管理与 CRM，提供销售 BI（收入/销量/AOV/趋势/品类/地区/Top 产品/异常）、客户价值分层（RFM）与销售业绩统计（目标达成率/排名）。

## 2. 功能清单

- 销售BI智能分析（能力 17）
- 客户价值评估（能力 18）
- 销售业绩智能统计（能力 19）
- 智能体对话板块（应用内与默认智能体对话）
- 问数能力（默认智能体通过 Skill/Tool 执行自然语言问数并返回可溯源结论）

## 3. 数据路径

数据来自真实订单、客户与销售目标数据，或用户明确标记的模拟数据。BI、RFM 分层与业绩统计均基于真实记录计算，可用时间范围切换。

## 4. API 端点

- `GET/POST /health`
- `GET/POST /bi/analyze`
- `GET/POST /customers/segment`
- `GET/POST /performance/analyze`
- `GET/POST /artifacts/bi`
- `GET/POST /artifacts/customers`
- `GET/POST /artifacts/performance`
- `GET/POST /artifacts`
- `GET/POST /artifacts/{id}`
- `GET/POST /artifacts/{id}/reviews`
- `GET/POST /artifacts/{id}/export`

## 5. Agent / Skill 接入与问数

本应用对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。

- **Skill / Tool 暴露**：应用把「销售 BI、RFM 客户分层与业绩统计」等能力以 Skill 形式暴露给默认智能体，作为其可调用的问数与业务工具。
- **问数路径**：用户在对话中提出自然语言问题 → 默认智能体调用应用（或 Data Core）的查询工具 → 返回可溯源结论（含 `record_id` + `source_type` + `data_mode`）。
- **可审阅工件**：问数结果与业务分析必须能生成可接受/驳回/导出的 Artifact，不能只有临时文本。

已登记的 Agent 可调用工具（部分）：`/bi/analyze`、`/customers/segment`、`/performance/analyze`。

把「销售 BI」「RFM 分层」「业绩统计」等能力封装为 Skill，供默认智能体做销售/CRM 问数并基于真实订单记录。

## 6. UI 入口

“我的应用 → 销售客户 → 销售客户中心”，路由 /apps/zhiyun-sales-studio。

应用内需提供「智能体对话」板块入口（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），可直接与默认智能体对话并查看问数结果。

## 7. 验收标准

- BI 指标必须由底层订单记录聚合，禁止静态图。
- RFM 分层需基于真实交易最近时间/频次/金额。
- 业绩统计需给出目标达成率与排名。
- 结果可生成 Artifact 并支持审阅导出。
- 应用内「智能体对话」板块可用，能直接与默认智能体对话并查看问数结果。
- 问数结果必须可追溯到底层记录（`record_id` + `source_type`），demo / production 严格隔离。
- 无权限的问数或操作必须被阻断并写入审计，禁止跨环境读取或修改数据。

---

> 本文件由 `docs/apps/README.md` 索引；产品级 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。
