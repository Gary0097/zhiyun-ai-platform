# 智造云 AIOS · 智能制造多租户 SaaS 平台（演示项目源码）

13 家佛山制造企业客户的多租户演示系统：每家企业独立账号、独立数据中枢实例、
专属 ERP/财务/订单中心/WeKnora 知识库工作空间，按合同功能清单差异化交付。

## 组件
- `datahub/` — AI 智能数据中枢（主服务 + 13 企业实例）：datahub_api.py(看板/风险/趋势/SQL台/采集)、
  ent_api.py(企业 ERP 页)、render_console_app.py(控制台内嵌页渲染)、crm_sync_tick.py(CRM 同步心跳)
- `dashboard/` — 交互看板三页（index/sql/snapshot）
- `weknora-gateway/` — WeKnora 知识库网关（8001，免密自动登录 + 按企业路由专属工作空间）
- `console-assets/` — 控制台定制入口（订单/客服/财务/销售/管理协同/采购 + 数据中枢内嵌页）
- `mcc/ sales-platform/ purchase/` — 管理协同中心 / 销售智能分析 / 智能采购
- `finance/` — 财务智能化中枢（Flask，FINANCE_DB/FINANCE_COMPANY 环境变量驱动，13 企业实例镜像同源）
- `order-center/` — 智能订单处理中心（FastAPI，SSO 免密 + WeKnora 智能体解析/适配/问答）

## WeKnora 知识库本体
本体为微信开源 wechatopenai/weknora-{app,ui}:v0.8.0（docker 部署，端口 18000），
本仓库不含其源码；`weknora-gateway/` 为自研网关（免密自动登录、按企业路由专属工作空间）。
- `ops/` — 运维脚本（46 项数据自检、WeKnora 企业空间供给、财务实例生成）

## 部署要点
- 凭据全部走环境变量：`DATAHUB_LLM_KEY` `WEKNORA_EMAIL` `WEKNORA_PASSWORD` `FINANCE_LLM_KEY` 等
- 业务数据库（*.sqlite）与企业账号台账不入库，按 ops/ 脚本可重建
- 入口地图见 `datahub/ENTRY_MAP.md`
