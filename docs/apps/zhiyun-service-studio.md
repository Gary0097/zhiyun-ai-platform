# 智能售后服务中心（zhiyun-service-studio）

> 分类：售后服务 ｜ 版本：0.1.0 ｜ 路由：/apps/zhiyun-service-studio
> 仓库：https://github.com/Gary0097/zhiyun-service-studio

## 1. 需求概述

智能售后服务中心面向售后客服，提供咨询意图识别、FAQ/知识命中、工单智能推荐与售后知识库构建，并从真实维修记录沉淀可优化的知识条目。

## 2. 功能清单

- 客户咨询智能应答（能力 12）
- 智能语义理解与意图识别（能力 13）
- 售后工单智能管理（能力 14）
- 售后知识结构化（能力 15）
- 智能体对话板块（应用内与默认智能体对话）
- 问数能力（默认智能体通过 Skill/Tool 执行自然语言问数并返回可溯源结论）

## 3. 数据路径

数据来自真实客服咨询文本与维修记录，或用户明确标记的模拟示例。意图分类、答案命中、工单推荐均基于真实知识条目与工单数据集；知识库从真实维修记录抽取与优化。

## 4. API 端点

- `GET/POST /health`
- `GET/POST /intent/classify`
- `GET/POST /answer`
- `GET/POST /knowledge/extract`
- `GET/POST /knowledge/optimize`
- `GET/POST /knowledge/artifacts`
- `GET/POST /knowledge/artifacts/{id}`
- `GET/POST /knowledge/artifacts/{id}/reviews`
- `GET/POST /knowledge/artifacts/{id}/export`
- `GET/POST /tickets`
- `GET/POST /tickets/{id}`
- `GET/POST /tickets/{id}/reviews`

## 5. Agent / Skill 接入与问数

本应用对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。

- **Skill / Tool 暴露**：应用把「售后意图识别、知识命中与工单推荐」等能力以 Skill 形式暴露给默认智能体，作为其可调用的问数与业务工具。
- **问数路径**：用户在对话中提出自然语言问题 → 默认智能体调用应用（或 Data Core）的查询工具 → 返回可溯源结论（含 `record_id` + `source_type` + `data_mode`）。
- **可审阅工件**：问数结果与业务分析必须能生成可接受/驳回/导出的 Artifact，不能只有临时文本。

已登记的 Agent 可调用工具（部分）：`/intent/classify`、`/answer`、`/knowledge/extract`、`/knowledge/optimize`、`/tickets`。

把「意图识别」「知识问答」「工单推荐」「知识沉淀」等能力封装为 Skill，供默认智能体做售后问数并基于真实工单/知识条目。

## 6. UI 入口

“我的应用 → 售后服务 → 智能售后服务中心”，路由 /apps/zhiyun-service-studio。

应用内需提供「智能体对话」板块入口（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），可直接与默认智能体对话并查看问数结果。

## 7. 验收标准

- 意图与答案必须来自真实知识条目，禁止固定回复。
- 工单推荐需体现技能匹配与负载均衡。
- 知识库必须由真实维修记录构建并可导出。
- 知识工件需支持审阅与导出。
- 应用内「智能体对话」板块可用，能直接与默认智能体对话并查看问数结果。
- 问数结果必须可追溯到底层记录（`record_id` + `source_type`），demo / production 严格隔离。
- 无权限的问数或操作必须被阻断并写入审计，禁止跨环境读取或修改数据。

---

> 本文件由 `docs/apps/README.md` 索引；产品级 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。
