# 应用级需求文档索引

> 本目录按“每个主要功能应用一份独立需求/开发文档”收录智云 AI-OS 当前登记的功能应用。
> 产品级总体 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`；本目录只描述可落地、可检验、基于真实数据路径的单个应用需求与验收口径。

## 文档清单

| 应用 | app_id | 分类 | 文档 |
| --- | --- | --- | --- |
| 企业数据分析中心 | `zhiyun-data-studio` | data | [zhiyun-data-studio.md](./zhiyun-data-studio.md) |
| 智能订单中心 | `zhiyun-order-studio` | order | [zhiyun-order-studio.md](./zhiyun-order-studio.md) |
| 智能售后服务中心 | `zhiyun-service-studio` | service | [zhiyun-service-studio.md](./zhiyun-service-studio.md) |
| 采购与供应链中心 | `zhiyun-supply-studio` | supply | [zhiyun-supply-studio.md](./zhiyun-supply-studio.md) |
| 销售客户中心 | `zhiyun-sales-studio` | sales | [zhiyun-sales-studio.md](./zhiyun-sales-studio.md) |
| 财务智能中心 | `zhiyun-finance-studio` | finance | [zhiyun-finance-studio.md](./zhiyun-finance-studio.md) |
| 组织协同中心 | `zhiyun-people-studio` | people | [zhiyun-people-studio.md](./zhiyun-people-studio.md) |
| 系统集成中心 | `zhiyun-integration-hub` | integration | [zhiyun-integration-hub.md](./zhiyun-integration-hub.md) |
| 工作区知识库 | `qwenpaw-knowledge-base` | knowledge | [qwenpaw-knowledge-base.md](./qwenpaw-knowledge-base.md) |
| 统一数据中心 | `zhiyun-data-core` | system | [zhiyun-data-core.md](./zhiyun-data-core.md) |
| 安全审计中心 | `zhiyun-audit` | system | [zhiyun-audit.md](./zhiyun-audit.md) |
| 应用与项目中心 | `zhiyun-app-discovery` | system | [zhiyun-app-discovery.md](./zhiyun-app-discovery.md) |
| 品牌 Logo 配置 | `zhiyun-logo` | system | [zhiyun-logo.md](./zhiyun-logo.md) |

## 共同约定（所有应用必须遵守）

1. **真实数据路径**：任何功能都必须建立在真实导入数据或明确标识的“模拟数据”之上，禁止用占位/硬编码数据冒充实现。空数据必须显示为空；模拟数据必须能在 UI 明确标识来源。
2. **demo / production 隔离**：Data Core 通过 `data_mode`（`demo` / `production`）与 `source_type`（`real` / `simulated`）区分演示与正式；功能应用必须写入并读取自己所属环境，不得互相污染。
3. **可审阅工件**：业务分析结果必须生成可审阅、可接受/驳回、可导出的 Artifact（`/artifacts/...`），不能只有一张临时图表。
4. **Agent Tool**：每个业务应用须提供可被 Agent 调用的工具，输入来自真实查询文本或数据，输出可追溯到数据记录。
5. **健康与门禁**：每个应用必须通过 `GET {prefix}/health`，并保持 `node scripts/verify-release.mjs`、健康检查和端到端验证通过。
6. **Agent / Skill 接入与问数**：每个业务应用都必须对应**一个默认智能体**（`agent_id` 与应用在 `agent_app_access` 中的关系由 `zhiyun-enterprise-seeder` 在初始化时持久化，平台注册 `agent-binding` 能力）。应用把「问数 / 业务操作」能力以 SKILL 形式暴露给该智能体：用户在对话中提出自然语言问题 → 智能体调用应用或 Data Core 的查询工具 → 返回可溯源结论（含 `record_id` + `source_type`）。应用 UI 内必须提供「智能体对话」板块（复用 `zhiyun-app-discovery` 的 `AgentDock` / `Q.setAgentContext` / `qwenpaw:agent-context` 机制，或应用自身实现），用于在应用内直接与默认智能体对话并查看问数结果。
7. **Agent 对话/问数的数据隔离与审计**：应用内智能体对话与问数必须遵守 `data_mode`（demo / production）与 `source_type`（real / simulated），问数结果只能来自当前环境底层记录，禁止跨环境污染；无权限的问数或操作必须被阻断并写入 `zhiyun-audit` 记录。
