# 工作区知识库（qwenpaw-knowledge-base）

> 分类：知识库 ｜ 版本：2.1.0 ｜ 路由：/files
> 仓库：https://github.com/agentscope-ai/QwenPaw

## 1. 需求概述

工作区知识库为整个 AI-OS 提供文档沉淀、知识检索与维护能力，支持从文档构建企业知识库，供各业务应用与 Agent 引用，是售后、客服问答的知识来源。

## 2. 功能清单

- 智能知识库系统（能力 25）
- 智能体对话板块（应用内与默认智能体对话）
- 问数能力（默认智能体通过 Skill/Tool 执行自然语言问数并返回可溯源结论）

## 3. 数据路径

数据来自工作区真实文件上传、生成与下载。文件在 /files 下组织；知识条目必须来源于真实文档内容，维护与更新需落库并支持索引。

## 4. API 端点

- `GET/POST /files`

## 5. Agent / Skill 接入与问数

本应用对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。

- **Skill / Tool 暴露**：应用把「基于真实文档的知识命中与文件引用」等能力以 Skill 形式暴露给默认智能体，作为其可调用的问数与业务工具。
- **问数路径**：用户在对话中提出自然语言问题 → 默认智能体调用应用（或 Data Core）的查询工具 → 返回可溯源结论（含 `record_id` + `source_type` + `data_mode`）。
- **可审阅工件**：问数结果与业务分析必须能生成可接受/驳回/导出的 Artifact，不能只有临时文本。

已登记的 Agent 可调用工具（部分）：`知识检索`、`文件引用`。

把「文档解析」「知识检索」「文件引用」等能力封装为 Skill，供默认智能体做知识问答并返回真实文档来源。

## 6. UI 入口

“我的应用 → 知识库 → 工作区知识库”，路由 /files（QwenPaw 2.1.0 内置）。

应用内需提供「智能体对话」板块入口（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），可直接与默认智能体对话并查看问数结果。

## 7. 验收标准

- 文件上传/生成/下载必须真实落盘并可追溯。
- 知识检索命中必须来自真实文档内容。
- 知识更新需写入底层记录并支持检索。
- 与 demo / production 环境对应隔离。
- 应用内「智能体对话」板块可用，能直接与默认智能体对话并查看问数结果。
- 问数结果必须可追溯到底层记录（`record_id` + `source_type`），demo / production 严格隔离。
- 无权限的问数或操作必须被阻断并写入审计，禁止跨环境读取或修改数据。

---

> 本文件由 `docs/apps/README.md` 索引；产品级 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。
