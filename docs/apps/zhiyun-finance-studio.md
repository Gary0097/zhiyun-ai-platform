# 财务智能中心（zhiyun-finance-studio）

> 分类：财务 ｜ 版本：0.1.0 ｜ 路由：/apps/zhiyun-finance-studio
> 仓库：https://github.com/Gary0097/zhiyun-finance-studio

## 1. 需求概述

财务智能中心面向财务人员，提供报销单智能审核（字段完整性/金额/税号/重复 → 通过/退回/驳回）、财务看板（毛利率/流动比率/负债率/趋势）与成本预测（BOM/原材料价格/单位成本）。

## 2. 功能清单

- 智能报销审核（能力 20）
- 财务数据分析看板（能力 21）
- 智能成本预测（能力 22）
- 智能体对话板块（应用内与默认智能体对话）
- 问数能力（默认智能体通过 Skill/Tool 执行自然语言问数并返回可溯源结论）

## 3. 数据路径

数据来自真实报销单、财务凭证与成本物料数据，或用户明确标记的模拟数据。审核规则、财务指标与成本预测均基于真实数据计算。

## 4. API 端点

- `GET/POST /health`
- `GET/POST /expense/audit`
- `GET/POST /finance/analyze`
- `GET/POST /cost/forecast`
- `GET/POST /artifacts/expense`
- `GET/POST /artifacts/finance`
- `GET/POST /artifacts/cost`
- `GET/POST /artifacts`
- `GET/POST /artifacts/{id}`
- `GET/POST /artifacts/{id}/reviews`
- `GET/POST /artifacts/{id}/export`

## 5. Agent / Skill 接入与问数

本应用对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。

- **Skill / Tool 暴露**：应用把「报销审核、财务指标与成本预测」等能力以 Skill 形式暴露给默认智能体，作为其可调用的问数与业务工具。
- **问数路径**：用户在对话中提出自然语言问题 → 默认智能体调用应用（或 Data Core）的查询工具 → 返回可溯源结论（含 `record_id` + `source_type` + `data_mode`）。
- **可审阅工件**：问数结果与业务分析必须能生成可接受/驳回/导出的 Artifact，不能只有临时文本。

已登记的 Agent 可调用工具（部分）：`/expense/audit`、`/finance/analyze`、`/cost/forecast`。

把「报销审核」「财务看板」「成本预测」等能力封装为 Skill，供默认智能体做财务问数并基于真实凭证/物料数据。

## 6. UI 入口

“我的应用 → 财务 → 财务智能中心”，路由 /apps/zhiyun-finance-studio。

应用内需提供「智能体对话」板块入口（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），可直接与默认智能体对话并查看问数结果。

## 7. 验收标准

- 报销审核必须逐字段校验并给出明确结论与原因。
- 财务指标必须由底层凭证聚合，禁止静态值。
- 成本预测需基于 BOM 与原材料价格。
- 结果可生成 Artifact 并支持审阅导出。
- 应用内「智能体对话」板块可用，能直接与默认智能体对话并查看问数结果。
- 问数结果必须可追溯到底层记录（`record_id` + `source_type`），demo / production 严格隔离。
- 无权限的问数或操作必须被阻断并写入审计，禁止跨环境读取或修改数据。

---

> 本文件由 `docs/apps/README.md` 索引；产品级 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。
