# 组织协同中心（zhiyun-people-studio）

> 分类：组织协同 ｜ 版本：0.1.0 ｜ 路由：/apps/zhiyun-people-studio
> 仓库：https://github.com/Gary0097/zhiyun-people-studio

## 1. 需求概述

组织协同中心面向 HR 与管理者，提供组织权限分级（高风险/关注/正常）、全员通讯录检索、审批路径推荐、生日/周年关怀与人力资源分析（离职率/招聘周期/缺口）。

## 2. 功能清单

- 组织与权限配置建议（能力 23）
- 全员通讯录与人员推荐（能力 24）
- 审批路径推荐（能力 26）
- 员工信息与生日管理（能力 27）
- 人力资源数据分析（能力 28）
- 智能体对话板块（应用内与默认智能体对话）
- 问数能力（默认智能体通过 Skill/Tool 执行自然语言问数并返回可溯源结论）

## 3. 数据路径

数据来自真实组织、员工、通讯录与审批数据，或用户明确标记的模拟数据。权限、检索、审批与关怀均基于真实组织数据。

## 4. API 端点

- `GET/POST /health`
- `GET/POST /permission/suggest`
- `GET/POST /contact/search`
- `GET/POST /approval/recommend`
- `GET/POST /anniversary/upcoming`
- `GET/POST /hr/analyze`
- `GET/POST /artifacts/permission`
- `GET/POST /artifacts/contact`
- `GET/POST /artifacts/approval`
- `GET/POST /artifacts/anniversary`
- `GET/POST /artifacts/hr`
- `GET/POST /artifacts`
- `GET/POST /artifacts/{id}`
- `GET/POST /artifacts/{id}/reviews`
- `GET/POST /artifacts/{id}/export`

## 5. Agent / Skill 接入与问数

本应用对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。

- **Skill / Tool 暴露**：应用把「组织权限、通讯录、审批路径与 HR 分析」等能力以 Skill 形式暴露给默认智能体，作为其可调用的问数与业务工具。
- **问数路径**：用户在对话中提出自然语言问题 → 默认智能体调用应用（或 Data Core）的查询工具 → 返回可溯源结论（含 `record_id` + `source_type` + `data_mode`）。
- **可审阅工件**：问数结果与业务分析必须能生成可接受/驳回/导出的 Artifact，不能只有临时文本。

已登记的 Agent 可调用工具（部分）：`/permission/suggest`、`/contact/search`、`/approval/recommend`、`/anniversary/upcoming`、`/hr/analyze`。

把「权限建议」「通讯录检索」「审批推荐」「HR 分析」等能力封装为 Skill，供默认智能体做组织/HR 问数。

## 6. UI 入口

“我的应用 → 组织协同 → 组织协同中心”，路由 /apps/zhiyun-people-studio。

应用内需提供「智能体对话」板块入口（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），可直接与默认智能体对话并查看问数结果。

## 7. 验收标准

- 权限分级必须依据真实角色与敏感度规则。
- 通讯录检索基于真实员工数据。
- 审批路径需结合金额、部门与紧急程度。
- 结果可生成 Artifact 并支持审阅导出。
- 应用内「智能体对话」板块可用，能直接与默认智能体对话并查看问数结果。
- 问数结果必须可追溯到底层记录（`record_id` + `source_type`），demo / production 严格隔离。
- 无权限的问数或操作必须被阻断并写入审计，禁止跨环境读取或修改数据。

---

> 本文件由 `docs/apps/README.md` 索引；产品级 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。
