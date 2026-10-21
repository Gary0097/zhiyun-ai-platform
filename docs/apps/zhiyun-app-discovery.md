# 应用与项目中心（zhiyun-app-discovery）

> 分类：系统组件 ｜ 版本：0.3.0 ｜ 路由：/apps/zhiyun-app-discovery
> 仓库：平台内置（无独立仓库）

## 1. 需求概述

应用与项目中心是制造云 AI-OS 的“我的应用”入口与功能清单聚合页，按功能大类展示已登记应用，提供搜索、应用状态与功能进度查看，帮助用户找到并能打开各业务应用。

## 2. 功能清单

- 应用按大类分组与中文展示
- 功能能力清单入口
- 应用/功能搜索
- 功能进度查看
- 智能体对话板块（应用内与默认智能体对话）
- 问数能力（默认智能体通过 Skill/Tool 执行自然语言问数并返回可溯源结论）

## 3. 数据路径

数据来自 app_catalog.json（应用登记、分类、路由、能力清单）与 feature_progress.json（功能进度）。该页仅做聚合展示，不产生业务数据，但必须与真实应用路由、实时健康状态一致。

## 4. API 端点

- `GET/POST /catalog`
- `GET/POST /search`
- `GET/POST /progress`

## 5. Agent / Skill 接入与问数

本应用对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。

- **Skill / Tool 暴露**：应用把「应用发现、能力索引与交付进度」等能力以 Skill 形式暴露给默认智能体，作为其可调用的问数与业务工具。
- **问数路径**：用户在对话中提出自然语言问题 → 默认智能体调用应用（或 Data Core）的查询工具 → 返回可溯源结论（含 `record_id` + `source_type` + `data_mode`）。
- **可审阅工件**：问数结果与业务分析必须能生成可接受/驳回/导出的 Artifact，不能只有临时文本。

已登记的 Agent 可调用工具（部分）：`/catalog`、`/search`、`/progress`。

把「应用发现」「能力检索」「进度查看」能力封装为 Skill，供默认智能体引导用户找到并打开对应业务应用（内置 `AgentDock` 对话面板）。

## 6. UI 入口

“我的应用 → 系统组件 → 应用与项目中心”，路由 /apps/zhiyun-app-discovery。

应用内需提供「智能体对话」板块入口（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），可直接与默认智能体对话并查看问数结果。

## 7. 验收标准

- 应用必须按功能大类分组展示，分类名称使用中文。
- 能力清单必须是每个应用的真实 capabilities。
- 搜索与进度必须来自真实 catalog 与 progress 数据。
- 打开入口必须跳转到真实应用路由。
- 应用内「智能体对话」板块可用，能直接与默认智能体对话并查看问数结果。
- 问数结果必须可追溯到底层记录（`record_id` + `source_type`），demo / production 严格隔离。
- 无权限的问数或操作必须被阻断并写入审计，禁止跨环境读取或修改数据。

---

> 本文件由 `docs/apps/README.md` 索引；产品级 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。
