# 智造云企业 AI 智能体平台（apps/enterprise）

基于 DeepSeek Harness 的多租户企业 AI 智能体运行与业务执行平台。完整需求规格见仓库根目录 PRD 文档与 `AI-OS-PRD-V3.0.md`。

## 架构

```text
企业平台 (8390)  ←HTTP 信封 API + WebSocket→  DSH Harness (8308)  ←OpenAI 兼容→  模型层
```

- **企业平台**（本目录）：零依赖 Node ≥24（node:http + node:sqlite），管租户/RBAC/业务数据/看板/AI 自动运行/知识库/调度/日志审计
- **DSH Harness**：Cordis 插件化 Agent Runtime（仓库 dsh 部分，已做去品牌化与工作区即续接等定制）
- **模型层**：多 Provider 可路由（本地 LM Studio / 远端 OpenAI 兼容网关）

## 快速开始

```sh
# 1. 配置模型密钥（本地文件，不入库）
cp config/secrets.example.env config/secrets.local.env   # 编辑填入密钥

# 2. 启动 DSH Web（8308，模型凭据见 ~/.dsh/settings.yaml 与 ~/.dsh/.credentials.yaml）
node ../cli/lib/bin.js web --no-open --port 8308

# 3. 启动企业平台（8390，自动加载 secrets.local.env）
node start.mjs

# 4.（可选）生成 88.6 万条历史运行数据
node server/cli.js simulate
```

默认账号（密码统一 `Zhiyun@2026`，种子数据仅演示用）：`platform` 平台超管 · `admin.a/b/c` 企业管理员 · `admin.j` 金汉隆管理员 · `sales.a` 普通员工 · `audit.a` 审计员。

## 核心能力

- **多租户**：所有核心表绑定 `tenant_id`，查询一律由服务端 Context 注入；跨租户访问一律 403
- **AI 自动运行**：34 角色轮跑（6 业务 + 28 功能模块演示），dsh 信封 API 直驱真实模型，全链路日志（trigger_type: auto:sim/report/multiagent/feature/research/task）
- **知识库**：两级（库→条目）+ knowledge_search 真检索 + 联网资料收割（资料→模型加工→入库→工作区 KNOWLEDGE.md 导出，dsh 会话可直接阅读）
- **WorkBuddy 式协作**：一次性 AI 任务（异步执行/状态轮询/trace 回放）+ 项目容器
- **定时任务**：cron/interval/condition 三类触发 + job_lock 防重 + 重试 + 死信审计
- **数据生成**：历史运行数据（88.6 万条，月度曲线/时段规律）+ 成体系企业业务数据（行业画像/订单状态机/财务派生）
- **可视化**：33 表数据库浏览（分页/全列搜索/凭据列隐藏）+ AI 运行监控看板（KPI/趋势/耗时/模块分布）+ 完整 markdown 渲染
- **日志审计**：四层日志表 + trace replay + 数据修改留痕（audit_change）

## 目录导览

```text
server/
├── index.js               服务入口
├── db.js                  33 表 schema + 种子 + 幂等迁移
├── routes.js              REST API（权限守卫）
├── auto-run.js            AI 自动运行模拟器
├── function-catalog.js    28 项产品功能清单（单一数据源）
├── knowledge-harvester.js 知识收割器
├── business-generator.js  企业业务数据生成器
├── harness.js             平台内 Agent 执行引擎（6 步循环 + trace 落库）
├── llm.js                 模型适配层（OpenAI 兼容/mock/连通测试）
├── tools.js               Tool 实现（query_*/knowledge_search 等）
├── scheduler.js           定时任务调度
└── auth.js                认证/权限/操作日志
public/index.html          单文件 SPA 前端（分组侧边栏/看板/表单/轮询）
scripts/                   验证/导入/夜间排程脚本
start.mjs                  启动器（加载本地密钥）
config/model.json          模型配置（密钥走环境变量，已脱敏）
```

## 数据说明

运行数据（`data/` 下 SQLite 库与租户工作区文档）不入库，服务启动时幂等生成种子；所有数据带 `data_origin` 标记（real/simulated/imported/manual/generated/auto-simulated/web-research），可在数据库浏览页按来源筛选。
