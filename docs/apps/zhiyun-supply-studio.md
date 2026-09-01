# 采购与供应链中心（zhiyun-supply-studio）

> 分类：供应链 ｜ 版本：0.1.0 ｜ 路由：/apps/zhiyun-supply-studio
> 仓库：https://github.com/Gary0097/zhiyun-supply-studio

## 1. 需求概述

采购与供应链中心面向采购与供应链管理，提供供应商综合评分（ABCD）、补货/EOQ 计算与供应链风险监控（红/黄/绿）。

## 2. 功能清单

- 供应商评估与智能补货（能力 16）
- 供应链风险实时监控（能力 30）
- 智能体对话板块（应用内与默认智能体对话）
- 问数能力（默认智能体通过 Skill/Tool 执行自然语言问数并返回可溯源结论）

## 3. 数据路径

数据来自真实供应商档案、价格、交付与库存记录，或用户明确标记的模拟数据。评分、补货与风险均基于真实数据集计算，风险等级可下钻到明细记录。

## 4. API 端点

- `GET/POST /health`
- `GET/POST /suppliers/score`
- `GET/POST /replenishment/calc`
- `GET/POST /risk/monitor`
- `GET/POST /artifacts/supplier`
- `GET/POST /artifacts/replenishment`
- `GET/POST /artifacts/risk`
- `GET/POST /artifacts`
- `GET/POST /artifacts/{id}`
- `GET/POST /artifacts/{id}/reviews`
- `GET/POST /artifacts/{id}/export`

## 5. Agent / Skill 接入与问数

本应用对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。

- **Skill / Tool 暴露**：应用把「供应商评分、补货建议与供应链风险」等能力以 Skill 形式暴露给默认智能体，作为其可调用的问数与业务工具。
- **问数路径**：用户在对话中提出自然语言问题 → 默认智能体调用应用（或 Data Core）的查询工具 → 返回可溯源结论（含 `record_id` + `source_type` + `data_mode`）。
- **可审阅工件**：问数结果与业务分析必须能生成可接受/驳回/导出的 Artifact，不能只有临时文本。

已登记的 Agent 可调用工具（部分）：`/suppliers/score`、`/replenishment/calc`、`/risk/monitor`。

把「供应商评分」「补货/EOQ」「风险监控」等能力封装为 Skill，供默认智能体做采购/供应链问数并可下钻到明细。

## 6. UI 入口

“我的应用 → 供应链 → 采购与供应链中心”，路由 /apps/zhiyun-supply-studio。

应用内需提供「智能体对话」板块入口（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），可直接与默认智能体对话并查看问数结果。

## 7. 验收标准

- 评分模型必须反映准时率/质量/价格/服务维度并输出等级。
- 补货结果需给出安全库存、再订货点与 EOQ。
- 风险监控必须支持下钻且只基于真实数据。
- 结果可生成 Artifact 并支持审阅导出。
- 应用内「智能体对话」板块可用，能直接与默认智能体对话并查看问数结果。
- 问数结果必须可追溯到底层记录（`record_id` + `source_type`），demo / production 严格隔离。
- 无权限的问数或操作必须被阻断并写入审计，禁止跨环境读取或修改数据。

---

> 本文件由 `docs/apps/README.md` 索引；产品级 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。
