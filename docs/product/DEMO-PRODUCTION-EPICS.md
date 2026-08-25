# Demo / Production 双态运行体系 — Epic 计划台账

> 独立于 `plugins/zhiyun-app-discovery/feature_progress.json`（当前 31 项能力台账）的新体系计划。
> 需求来源：`docs/product/AI-OS-SIMULATION-DUAL-STATE-VISION.md`。
> 状态取值：`planned`（仅计划）/ `in_progress` / `test` / `completed`。进展以真实浏览器/接口证据为准。
> **不将 Epic 直接写入 31 项台账**；只有当某 Epic 产出可交付能力并满足完成标准时，才评估是否需要新增能力条目并同步 `scripts/verify-project-plan.mjs` 校验。

---

## Epic 状态说明

- `planned` = 需求已明确，尚未实现。
- `in_progress` = 有实现工作在推进。
- `test` = 实现完成，等真实实机验收。
- `completed` = 以「可运行 + 证据留存 + 口径闭环」为证。

---

## Epic 1 — Enterprise Seeder（企业环境初始化器）

| 项 | 内容 |
| --- | --- |
| 目标 | 一键从零生成完整企业组织与数字员工 |
| 范围 | 企业 → 部门 → 用户 → 角色 → 权限 → Agent → Skill → 应用 → 数据源 → 会话 → 任务执行 → Token → 操作日志 |
| 复用现状 | `zhiyun-auth` 已有登录门、用户文件、默认账号 `admin/Zhiyun@2026`；`zhiyun-enterprise-seeder` 已上线（seed/config/summary/records，含多环境隔离与 Bearer 鉴权）；`zhiyun-data-core` 已有 `data_core_meta / data_batches / data_records` 与 `source_type=real\|simulated` |
| 缺口 | 已实现一键初始化与账号同步；仍需 Agent 与执行记录/Token/日志的跨模块引用闭环与一致性校验（见 Epic 3/6） |
| 关键产物 | 企业模板（制造企业）、部门/岗位/权限矩阵、初始化命令、运行时实体 |
| 验收 | 全新 DB 一次初始化后，企业、部门、用户、角色、权限、Agent、Skill、应用、会话、任务、Token、日志全部存在且可跨模块引用 |
| 状态 | `test` |
| 依赖 | 无 |
> **本轮进展（2026-08-25）**：已上线 `zhiyun-enterprise-seeder`，`/seed` 一次生成企业与全链路数据并同步账号；`/records` 强制 `env_id + data_mode` 多环境隔离；Bearer 鉴权覆盖 config/summary/records/seed（seed 仅 admin）；GUI Playwright 22/22 pass。证据见 `docs/qa/screenshots` 与 `docs/handoff/HANDOFF_GPT_2026-08-24.md` §14。
> **残留**：RBAC 未覆盖各 Studio 业务接口；跨模块一致性检查（Epic 6）未做；多实例独立启动仍为人工约定。
## Epic 2 — Agent Factory（智能体自动配置）

| 项 | 内容 |
| --- | --- |
| 目标 | 按岗位模板自动生成完整智能体配置并真正关联模型 |
| 范围 | Agent 名称/岗位/部门/System Prompt/模型/Skill/Tool/知识库/数据权限/应用权限/最大 Token/执行频率/工作时间/自动任务/人工触发/成功率/平均响应时间 |
| 复用现状 | 各 Studio 已有 Skill/Tool 注册（`qwenpaw plugins/api.py` 注入 ToolRegistry）；`zhiyun-auth` 有员工 → 可用 Agent 激活接口 |
| 缺口 | 缺岗位模板库；缺 Agent 与 Skill/Tool/模型/知识库/权限的完整创建链路；缺成功率/响应时间等仿真指标 |
| 关键产物 | 岗位模板（销售报价/客户跟进/邮件营销/采购对账/财务票据/售后客服/经营分析）、Agent 工厂 API、配置校验 |
| 验收 | 按模板创建 Agent 后，其 Skill/Tool/模型/知识库/权限均有真实关联记录，且能被本地模型调用 |
| 状态 | `test` |
| 依赖 | Epic 1 |
> **本轮进展（2026-08-25 服务重启后）**：Agent Factory 已实现并实机验证。`agent_factory.py` 提供 `MODEL_CATALOG`（本地 Qwen2.5 7B/14B/72B + 云端 Qwen-Max/Plus）、`TOOL_CATALOG`（22 个真实工具）、`CATEGORY_DEFAULT_TOOLS`、`APP_ACCESS_BY_DEPT`，以及 `build_agent_config / validate_agent_config / persist_bindings / reconcile_bindings / make_agent_row / new_agent_id`。`enterprise_plugin.py` 新增 5 条路由（catalog/templates/bindings/validate/reconcile），均带 Bearer 鉴权（validate/reconcile 仅 admin）。前端新增 `AgentFactoryPanel` GUI（模板切换、表格、绑定摘要、回填/校验按钮）。实测：catalog 5 模型/22 工具，templates 双行业模板，reconcile 回填 demo 环境 57 个 Agent，validate 对合法/非法规格均正确输出；单测 7/7。修复 P1：非法规格触发 `KeyError` 500，已改为兜底并跳过落盘未注册工具。
> **残留**：`models` 表新增时不回写 `agents.model` 列；本地模型服务不可达不影响平台健康。`data_mode=production` 已非空（2026-08-25 新增 `env_9955444109`，30 用户/5621 会话），双态隔离已实测通过。

## Epic 3 — Simulation Runtime / Business Activity Generator（本地模型自动跑业务）

| 项 | 内容 |
| --- | --- |
| 目标 | 本地模型按业务规则产生事件，驱动 Agent → Skill → Tool → 结果 → 日志 → Token → 用户行为 → 统计 |
| 范围 | 业务事件、Agent 执行、Skill/Tool 调用、结果工件、Token、用户行为、每日持续增量 |
| 复用现状 | `zhiyun-data-core` 已有 `generate_orders / generate_production / import_rows(source_type="real")` 与模拟批次；`zhiyun-data-core` UI 已有生成演示数据按钮 |
| 缺口 | 现为后端直接插模拟行，非「模型驱动的业务事件 → Agent → Skill → Tool → 日志 → Token」闭环；缺 Token/执行日志/用户行为联动 |
| 关键产物 | Simulation Runtime、业务事件引擎、执行/Tok 统计闭环 |
| 验收 | 任一日期的 Agent 调用量、Token、文件、活跃用户均可由底层会话/执行记录追溯；前台无「模拟/Mock」标记 |
| 状态 | `test` |
| 依赖 | Epic 1、Epic 2 |
> **本轮进展（2026-08-25 服务重启后）**：`simulation_runtime.py` 已实现规则驱动运行时（业务事件 -> Agent -> Skill/Tool -> 结果 -> 下载 -> Token -> 统计），新增 `_stable_day_seed`（跨进程稳定）、`build_day_events/execute_day_events`、`log_business_event/list_events`、`preview_interval/run_interval`、`_clear_day`（force 幂等），并落地 `/simulation/status|preview|run|events` 四端点。单测 6/6；实机验收 preview 只读、force 重跑幂等、事件审计闭环、Integrity 14/14（demo 与 production 均通过）。修复 `force=true` 重复插入导致统计翻倍的 P2 缺陷。同轮已补全：`_clear_day` 覆盖 `login_activity/operation_logs`；运行时写入登录/操作日志并记 `business_events`；`business_events` 纳入 `/integrity`（第 14 项 `business_event_scope`）。待补：模型驱动执行替换规则引擎。
> **残留**：本地模型服务不可达，真实模型驱动执行不可用；规则驱动运行时不受影响。

## Epic 4 — Time Machine / Time Simulation Engine（历史数据时间引擎）

| 项 | 内容 |
| --- | --- |
| 目标 | 生成 2025-12-01 至当前日期的历史数据，并支持任意时间段同步切换 |
| 范围 | 默认 2025-12-01~当前，每日补充；今天/昨天/近7/近30/本月/上月/本季/今年/自定义；业务周期规律 |
| 复用现状 | `zhiyun-data-core` 有 `data_core_meta / data_batches / data_records` 带 `created_at`；各 Studio 有日期字段 |
| 缺口 | 缺统一时间维度上下文；缺工作日/工作时间/月度/企业增长规律；切时间范围需所有 Dashboard/Agent/Token/用户/聊天/任务/应用同步 |
| 关键产物 | Time Machine、统一时间上下文、业务周期生成规则 |
| 验收 | 选择任一时间段，所有统计数据（用户/Agent/聊天/Token/应用/权限/文件/执行）同步切换到该时段，而非只有图表日期变化 |
| 状态 | `test` |
| 依赖 | Epic 1、Epic 3 |
> **本轮进展（2026-08-25 服务重启后）**：`/analytics/trends` 已上线（日/周/月粒度、工作日/周末均值、Agent/用户首次活跃增长、区间总量）；前端新增「趋势分析」卡与 上月/本季度/今年 档位、日/周/月 粒度与六条曲线。`/summary` 仍支持范围过滤（sessions/tasks/token/files/downloads/logins）。复测：production `env_9955444109` 2026-01-01~2026-08-25 日粒度 summary=5621/11293/12763511/6495/12035/2348/130，workday_avg=32 vs weekend_avg=3；跨粒度 2026-08-01~25 周 5 桶 / 月 1 桶、summarySessions=718 一致。单测 `test_analytics` 7/7，全套 20/20。修复两处真实 BUG（f-string `{group_col}`、末月 cutoff clamp）。多 Studio Dashboard 同步已由 DataContext 广播闭环（见下）。

> **多 Studio 时间同步（DataContext 广播）**：`zhiyun-data-core` 落地共享活动上下文，`data_core_meta.active_context` 存 `data_mode + env_id + start_date + end_date`，由 `PUT /context` 下发、`GET /context` 读取；`list_records/search_records` 与 `/orders`、`/records/{entity}` 未显式传参时自动套用。`zhiyun-enterprise-seeder` 在 `loadAll / loadSummary / doGenerate / agentCommand` 成功后自动 `publishDataContext` 广播。实测（服务重启后）：企业环境初始化器加载后上下文自动变为 `env_9955444109 / production / 全量`；外部 `zhiyun-data-studio` 未传参调用 `/zhiyun-data-core/orders` 即自动继承——demo 全量「订单总数 100 / 风险表填充」，production 「订单总数 0 / 空」双态隔离正确；GUI 证据见 `docs/qa/screenshots/studio-inherit-demo.png`、`studio-inherit-production.png`。源码与运行副本 SHA256 一致。状态由 `in_progress` → `test`。残留：外部 Studio 前端来源列仍显示「模拟数据」标签（源自第三方仓库，待 Epic 5 在源项目统一改口）。
## Epic 5 — Data Platform（Excel/CSV Import/Export + Demo/Production 双态）

| 项 | 内容 |
| --- | --- |
| 目标 | 把 Excel/CSV 导入导出做成平台统一能力，并落地 Demo/Production 双态隔离与一键切换 |
| 范围 | Import(.xlsx/.xls/.csv)、Export(.xlsx/.csv)、字段映射/预览/校验/错误行/去重/增量/覆盖；`data_mode=demo\|production`；DataContext；`tenant_id/environment_id/data_source` |
| 复用现状 | `zhiyun-data-core` 已有 `preview_import / import_rows / list_records / search_records / list_batches / rollback_batch`，`source_type="real"`，Data Core 同时有「真实/模拟」视图（数据核心当前显示「真实 20 / 模拟 280」） |
| 缺口 | 缺公共 Import/Export SDK；缺 `data_mode`/DataContext 统一下发；缺 Demo/Production 逻辑或物理隔离；frontend 仍见「模拟」徽标（改造点） |
| 关键产物 | Data Import/Export SDK、DataContext、环境切换 UI（数据环境 Demo/Live）、隔离字段 |
| 验收 | 任一 App 可通过 SDK 导入/导出 Excel/CSV；切换演示/正式环境后，两张数据集互不污染；正式模式不读演示记录；前台无「模拟/Mock」标记 |
| 状态 | `test` |
| 依赖 | Epic 1（需要企业/用户上下文）、Epic 3 |

> **本轮进展（2026-08-25）**：`zhiyun-data-core` 落地 Demo/Production 双态隔离。`data_batches/data_records` 新增 `data_mode TEXT NOT NULL DEFAULT 'demo'`，`SCHEMA_VERSION` 升至 `3`，旧库（v2）启动时自动 `ALTER TABLE` 升级并把既有记录归入 `demo`。`/entities`、`/records/{entity}`、`/batches`、`/orders` 均支持 `data_mode`（demo/production）过滤；导入落 `production`（真实），演示生成落 `demo`。前端新增「数据环境 演示 Demo / 正式 Live」切换、来源筛选「已导入 / 系统生成」、「数据环境」列与「演示数据 / 正式数据」统计卡，全文件移除「模拟/Mock」字样。迁移验证（v2 一致快照→v3）通过：`schema_version=2→3`、旧 300 条订单默认 `demo`、demo/production 写入隔离、`list_entities` 计数正确。

## Epic 6 — Data Integrity（数据一致性检查器）

| 项 | 内容 |
| --- | --- |
| 目标 | 跨模块一致性检查、异常检查、可安全修复项自动修复，并生成报告 |
| 范围 | 用户/Agent/Token/聊天/文件/权限一致性；成功+失败=执行总数；Agent Token=应用 Token=企业 Token；消息↔ Conversation↔User↔Agent；下载记录↔文件；用户↔权限 |
| 复用现状 | `zhiyun-audit` 已有审计链完整性校验、Tool 表、防篡改哈希链、敏感信息防泄漏；`zhiyun-data-core` 有批次与回滚 |
| 缺口 | 缺跨模块一致性检查器、报告生成、自动修复策略 |
| 关键产物 | Data Integrity Checker、`Data Integrity Report`、安全自动修复 |
| 验收 | 每日自动生成报告；可安全修复项自动修复；所有检查项有明确通过/失败证据 |
| 状态 | `completed` |
| 依赖 | Epic 1、Epic 3、Epic 4、Epic 5 |
> **本轮进展（2026-08-25）**：`/integrity` 已实现 Data Integrity Report，覆盖 14 项一致性检查（执行总数、Token 一致性、会话/任务/文件/下载归属、登录回查、权限越权、成功率、日波动、业务事件链完整性 `business_event_scope`），`total=14 passed=14 failed=0 healthy=true`，约 1.1s。新增 5 条索引提速。待补：自动修复策略与每日定时报告。
> **本轮收尾（2026-08-25 服务重启后）**：安全自动修复 + 每日一致性快照 + 历史轨迹已落地。新增 `integrity_reports` / `integrity_repair_log` 表与索引；`GET /integrity/daily`（同日重复为更新）、`GET /integrity/history`、`POST /integrity/repair`（仅管理员）；启动钩子自动生成当日报告。实机验收：demo/production 均 14/14 通过，repair `fixed_checks=[]`（已健康）且写入审计，无授权 401。GUI 新增（自动修复 / 运行检查 / 今日快照）三按钮与快照摘要。详见 `docs/qa/qa-report-integrity-repair-2026-08-25.md`。

---

## 关联与提醒

- 需求全文见 `docs/product/AI-OS-SIMULATION-DUAL-STATE-VISION.md`。
- 真实数据源（Excel 文件）用于 Epic 5 / Epic 15（Real Data Profiler）校准，见愿景文档 §7。
- 任何 Epic 达「可运行」后，需回填 `docs/qa` 测试结果并在 `docs/handoff` 记录证据。
- **不要**改动 `feature_progress.json` 现有 1-31 项；如需新增能力条目，先评估其是否与现有 31 项台账的「唯一 ID + status/progress 配比 + 证据 note」校验兼容，避免破坏 `scripts/verify-project-plan.mjs`。
