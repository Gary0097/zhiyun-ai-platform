# 品牌 Logo 配置（zhiyun-logo）

> 分类：系统组件 ｜ 版本：1.0.0 ｜ 路由：（无独立页面，后端 /config）
> 仓库：平台内置（无独立仓库）

## 1. 需求概述

品牌 Logo 配置是平台级系统组件，提供品牌 Logo 的配置与展示，供桌面壳与各页面统一引用品牌标识。

## 2. 功能清单

- 品牌 Logo 配置与持久化
- 平台级品牌标识展示
- 智能体对话板块（应用内与默认智能体对话）
- 问数能力（默认智能体通过 Skill/Tool 执行自然语言问数并返回可溯源结论）

## 3. 数据路径

配置来自 /config 接口与本地配置存储。Logo 不产生业务数据，只承载平台级品牌配置。

## 4. API 端点

- `GET/POST /config`

## 5. Agent / Skill 接入与问数

本应用对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。

- **Skill / Tool 暴露**：应用把「平台品牌 Logo 配置读取」等能力以 Skill 形式暴露给默认智能体，作为其可调用的问数与业务工具。
- **问数路径**：用户在对话中提出自然语言问题 → 默认智能体调用应用（或 Data Core）的查询工具 → 返回可溯源结论（含 `record_id` + `source_type` + `data_mode`）。
- **可审阅工件**：问数结果与业务分析必须能生成可接受/驳回/导出的 Artifact，不能只有临时文本。

已登记的 Agent 可调用工具（部分）：`/config`。

作为平台级系统能力暴露配置读取 Skill，供默认智能体在低风险场景（非业务写）下读取品牌配置。

## 6. UI 入口

不单独在“我的应用”展示为独立卡片；作为系统组件后台配置，路由无独立页面（后端 /config）。

应用内需提供「智能体对话」板块入口（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），可直接与默认智能体对话并查看问数结果。

## 7. 验收标准

- Logo 配置必须可持久化并在平台级生效。
- 不与其他应用竞争业务数据，保持平台级隔离。
- 配置更新需留痕。
- 应用内「智能体对话」板块可用，能直接与默认智能体对话并查看问数结果。
- 问数结果必须可追溯到底层记录（`record_id` + `source_type`），demo / production 严格隔离。
- 无权限的问数或操作必须被阻断并写入审计，禁止跨环境读取或修改数据。

---

> 本文件由 `docs/apps/README.md` 索引；产品级 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。
