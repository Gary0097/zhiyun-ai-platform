# 智能订单中心（zhiyun-order-studio）

> 分类：订单管理 ｜ 版本：0.7.1 ｜ 路由：/apps/zhiyun-order-studio
> 仓库：https://github.com/Gary0097/zhiyun-order-studio

## 1. 需求概述

智能订单中心面向销售与订单管理，将客户提供的订单图片/文本/合同进行结构化解析，通过模板匹配、合同要素抽取与订单-合同一致性校验，识别异常并进行具名化的接受/驳回/重试处理。

## 2. 功能清单

- 客户订单自动格式化（能力 7）
- 多模板支持与适配（能力 8）
- 合同要素提取与比对（能力 9）
- 订单—合同一致性验证（能力 10）
- 异常处理流程自动化（能力 11）
- 智能体对话板块（应用内与默认智能体对话）
- 问数能力（默认智能体通过 Skill/Tool 执行自然语言问数并返回可溯源结论）

## 3. 数据路径

数据来自真实录入的订单图片/微信/邮件/OCR 文本，或用户明确标记的模拟原文。每个订单/合同都保留原文证据，解析结果形成可审阅项目；异常处理与结果全部写入底层记录，可追溯到原文。

## 4. API 端点

- `GET/POST /health`
- `GET/POST /parse-text`
- `GET/POST /projects`
- `GET/POST /projects/{id}`
- `GET/POST /projects/{id}/reviews`
- `GET/POST /projects/{id}/export`
- `GET/POST /templates/match`
- `GET/POST /contracts/review`
- `GET/POST /contracts/extract-file`
- `GET/POST /contracts/compare-order`
- `GET/POST /exceptions`
- `GET/POST /exceptions/{case_id}`
- `GET/POST /exceptions/{case_id}/reviews`
- `GET/POST /exceptions/{case_id}/retry`
- `GET/POST /exceptions/{case_id}/export`

## 5. Agent / Skill 接入与问数

本应用对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。

- **Skill / Tool 暴露**：应用把「订单/合同结构化、一致性校验与异常重试」等能力以 Skill 形式暴露给默认智能体，作为其可调用的问数与业务工具。
- **问数路径**：用户在对话中提出自然语言问题 → 默认智能体调用应用（或 Data Core）的查询工具 → 返回可溯源结论（含 `record_id` + `source_type` + `data_mode`）。
- **可审阅工件**：问数结果与业务分析必须能生成可接受/驳回/导出的 Artifact，不能只有临时文本。

已登记的 Agent 可调用工具（部分）：`/parse-text`、`/templates/match`、`/contracts/review`、`/contracts/compare-order`、`/exceptions/{case_id}/retry`。

把「订单解析」「模板匹配」「合同要素校验」「一致性比对」等能力封装为 Skill，供默认智能体做订单/合同问数并保留原文证据。

## 6. UI 入口

“我的应用 → 订单管理 → 智能订单中心”，路由 /apps/zhiyun-order-studio。

应用内需提供「智能体对话」板块入口（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），可直接与默认智能体对话并查看问数结果。

## 7. 验收标准

- 订单/合同必须保留原文证据，禁止只用摘要。
- 模板匹配必须基于真实模板库与字段映射。
- 异常支持具名接受/驳回/重试，状态与结果可追溯。
- 校验结果与人工复审记录写入底层记录。
- 应用内「智能体对话」板块可用，能直接与默认智能体对话并查看问数结果。
- 问数结果必须可追溯到底层记录（`record_id` + `source_type`），demo / production 严格隔离。
- 无权限的问数或操作必须被阻断并写入审计，禁止跨环境读取或修改数据。

---

> 本文件由 `docs/apps/README.md` 索引；产品级 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。
