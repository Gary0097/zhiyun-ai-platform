# 智造云 AI-OS · 全量交接文档（给最强 GPT 继续完善）

> 交接日期：2026-08-24
> 交接给：具备完整上下文理解的后续模型（GPT 最强档）
> 交接目标：让后续模型能**只在 `zhiyun-ai-platform` 仓库内**就掌握本轮全部改动、运行方式、已验证事实、遗留问题与下一步，而不是重新摸索。所有涉及对外可见行为（GUI / 结果 / 鉴权 / 租户 / 文档）都应能直接从本文与配套文档核对。

---

## 1. 本轮目标与用户诉求

用户原始诉求（按提出顺序，均为本轮范围）：

1. 完成剩余「17 项基础开发」，完成后叫用户测试。
2. 全部功能 UI 深度重构；交互参考本项目，但界面与交互需重构；无交互 PRD，交互方案由实现方拟定；这是 B 端智能化 AI 系统，风格简洁高效；**所有功能应用都需要嵌入 Agent 对话框**；PRD 追加需求变更信息。
3. 做相关功能测试，拟人化交互测试；测试用例与结果输出进项目；有 BUG 需修复并标注等级。
4. 追加需求：**登录与权限**，不同用户使用不同 Agent/数据/知识库，同企业即可，不同企业单独启动系统（企业隔离 = 单租户实例）。
5. 完整整理本轮更新与记录，产出完整交接文档，供最强 GPT 完善整个项目。
6. 最新反馈：**测试不通过，全部功能都只有 json 数组，都不知道怎么用，新开发的功能也没有正常的 GUI 界面。**

> 结论（第二迭代修正）：新增「员工账号登录与权限」，并复现了用户反馈的「系统应用无 GUI」。根因是三个系统应用在 `app_catalog.json` 的 `route` 写成短名（`/apps/data-core` 等），与插件 `entry_page`/`registerRoutes` 的完整路由（`/apps/zhiyun-data-core` 等）不一致，导致从「应用中心」点「打开」落回「应用」列表。已改为完整路由并验证直达真实面板。其余业务 Studio 为真实结构化 GUI，具备一键导入示例数据 + 可运行 + 可审阅结果；访问应使用 `/apps/<plugin-id>`，并 Ctrl+F5 清旧缓存。

---

## 2. 总体架构

- 底座：QwenPaw 2.1.0（`qwenpaw app --host 127.0.0.1 --port 8088`），单进程原生 PawApp 体系。
- 应用：每套业务是一个安装在 QwenPaw Apps 里的 PawApp，独立卡片、独立后端 API、独立数据目录。
- 前端：每个 PawApp 的 `ui/index.js` 是一个基于 `window.QwenPaw.host.React` 的自加载前端插件，通过 `Q.registerRoutes(...)` 挂载 App 路由与页面。
- 数据：默认 SQLite，各 Studio 通过 `*_STUDIO_DB` 环境变量指向**可写运行时数据目录** `.qwenpaw-runtime-data/<studio>/<db>`，避免回退到只读用户目录导致 503。
- 五大业务 Studio 统一由生成器 `_gen_ui.py` 产出前端（唯一事实来源），其余 PawApp 各有独立前端。

### 2.1 关键目录与路径

```
<repo>=C:\AI\zhiyun-ai-os-workspace\zhiyun-ai-platform
<repo>\docs\product\AI-OS-PRD-V6.4-QwenPaw-PawApps.md      # 主 PRD（已追加需求变更段）
<repo>\docs\product\REQUIREMENT-CHANGES-2026-08-24.md      # 本轮需求变更记录
<repo>\docs\product\PROJECT-PLAN.md                        # 项目计划/进度
<repo>\docs\qa\qa-report-GUI-rebuild-2026-08-24.md         # 本轮验收测试报告
<repo>\docs\handoff\HANDOFF_GPT_2026-08-24.md              # 本文件
<repo>\apps\qwenpaw-embedded\scripts\start.mjs             # 启动入口（git 跟踪，已改）
<repo>\apps\qwenpaw-embedded\workspace\plugins\<id>\ui\index.js   # 运行时前端 bundle（服务器加载）
<repo>\apps\qwenpaw-embedded\runtime\pawapps\<id>\ui\index.js    # npm/start.mjs 安装副本
<repo>\apps\qwenpaw-embedded\workspace\plugins\<id>\docs\PROGRESS.md # 各 Studio 进度文档
```

> **重要**：`workspace/plugins/**` 与 `runtime/pawapps/**` 均在 `.gitignore` 内（不纳入 git）。git 只跟踪 `start.mjs` 与 `docs/**`。因此修改前端后需通过 `_gen_ui.py` 生成并手动同步两处副本；`__qa__` 与 `docs` 属于仓库可交付内容。

---

## 3. 前端生成器与同步（唯一事实来源）

文件：`<工作区根>\_gen_ui.py`（89,405 字节，生成五个 Studio 的 `ui/index.js`）。

生成与同步流程：

```powershell
cd C:\AI\zhiyun-ai-os-workspace
python _gen_ui.py
# 将生成结果同步到以下两处（内容需字节一致）：
#   1) zhiyun-ai-platform\apps\qwenpaw-embedded\workspace\plugins\zhiyun-<studio>\ui\index.js
#   2) zhiyun-ai-platform\apps\qwenpaw-embedded\runtime\pawapps\zhiyun-<studio>\ui\index.js
```

关键前端接线（代码位置以生成器为准）：
- `sampleFor(mod) { return mod.sample != null ? mod.sample : mod.example; }`：text 模块兼容 `example`。
- `runModule(key, overrideValue)`：支持外部传入值绕过旧闭包读取。
- `renderResult` 使用 `mod.render(result)`：每个模块自定义结构化 render（KPI 卡片 + 表格/应答/趋势），**无裸 JSON 兜底**。
- 结果区统一含「数据来源（真实 / 模拟）」「待审阅」徽标、Trace id、接受/驳回/导出/交给 Agent 按钮。
- 右上角「问 Agent」打开智能体抽屉；抽屉内四个快捷指令调用 `runModule(key, sampleFor(mod))`。

> 已核对：`workspace/plugins` 与 `runtime/pawapps` 五 Studio + data + order 的 `ui/index.js` 尺寸逐字节一致（service=45714, supply=46465, sales=45129, finance=46905, people=50441, data=38279, order=21144）。

---

## 4. 18 模块矩阵与实测数值（权威验收值）

输入类型：`text`（多行文本，示例按钮=载入示例文本）；`table`（可编辑表格，示例按钮=一键导入示例数据）；`form`（表单，示例按钮=一键填入示例数据）。运行按钮 = 各模块 `chipLabel`。

| # | Studio | 模块(key) | 输入 | 运行按钮 | 实测关键值 | 方法 |
| --- | --- | --- | --- | --- | --- | --- |
| 12 | 服务 | 客户咨询应答(answer) | text | 生成应答 | 置信度 0.84；意图 订单查询；命中知识 是；命中标准问答=电机异响怎么处理 | faq-keyword-v1 |
| 13 | 服务 | 智能意图识别(intent) | text | 识别意图 | 意图 订单查询；置信度 1；命中关键词=订单 | rule-based-explainable-v1 |
| 14 | 服务 | 售后工单管理(tickets) | form | 创建并待审阅 | 处理团队 电机组；推荐工程师 张工（空闲 2）；匹配技能 电机、异响、轴承 | engineer-route-v1 |
| 15 | 服务 | 知识库构建(knowledge) | table | 生成知识库 | 知识条数 3；条目：电机异响→轴承磨损→换轴承并重装，评分 88 | knowledge-v1 |
| 16 | 供应 | 供应商评估(supplier) | table | 评估供应商 | 供应商 3；A/B 级 2/1；D 级 0 | weighted-score-v1 |
| 17 | 供应 | 智能补货(replenishment) | table | 计算补货 | 核算物料 2；紧急补货 1；建议补货 1 | safety-stock-eoq-v1 |
| 18 | 供应 | 风险监控(risk) | table | 监控风险 | 监控记录 3；高风险 1；中风险 2 | rule-based-risk-v1 |
| 19 | 销售 | 销售BI分析(bi) | table | 生成销售BI | 营收 41780；销量 125；订单数 4；客单 10445；2026-07 17300 / 2026-08 24480 | sales-bi-v1 |
| 20 | 销售 | 客户价值分层(customers) | table | 客户分层 | VIP 1；高价值 1；普通 0；待唤醒 1 | rfm-v1 |
| 21 | 销售 | 销售业绩统计(performance) | table | 统计业绩 | 整体达成率 94.8%；总营收 1280000；总目标 1350000；3 人 | performance-v1 |
| 22 | 财务 | 报销审核(expense) | table | 审核报销 | 通过 1；退回 0；驳回 2；总金额 11600 | expense-audit-v1 |
| 23 | 财务 | 财务看板(finance) | table | 生成看板 | 毛利率 41.7%；净利率 27.3%；经营利润率 27.3%；流动比率 2.13 | finance-ratio-v1 |
| 24 | 财务 | 成本预测(cost) | form | 预测成本 | 原单位成本 12.5；新单位成本 13.231；变动% 5.85%；年度影响… | 材料价差/量本利 |
| 25 | 人力 | 权限建议(permission) | table | 生成权限方案 | 用户 3；高危 0；关注 1 | permission-suggest-v1 |
| 26 | 人力 | 通讯录协作(contact) | table | 检索通讯录 | 命中 3；关键词 全部；含技能定位 | contact-search-v1 |
| 27 | 人力 | 审批路径(approval) | form | 推荐审批 | 金额 120000；最终审批人 总经理；环节数 4；主管→部门经理→财务总监→总经理 | approval-path-v1 |
| 28 | 人力 | 员工关怀(anniversary) | table | 生成关怀 | 临近生日 3；司龄 0；窗口 30 天（钱进 3/刘华 6/赵敏 12 天） | anniversary-v1 |
| 29 | 人力 | 人力分析(hr) | table | 分析人力 | 在编 3；缺编 57；离职率 0%；近90天招聘 0；部门分布 生产部2/质量部1 | hr-analytics-v1 |

> 编号说明：表格「#」为 PRD/需求变更文档的连续编号（12-29），与 `_gen_ui.py` 内 `featNo`（沿用 PawApp 功能矩阵，如 supply risk featNo=30）不同；两者均已核对，不代表缺失。

---

## 5. Agent 对话框嵌入

- 五个核心 Studio 右上角均有「问 Agent」按钮，打开右侧智能体抽屉；抽屉含当前功能标签、四个快捷指令、自由输入框；自然语言自动匹配功能→载入示例→运行→工件卡片回填。
- 其余底层/工具类插件通过 QwenPaw Console 宿主全局「聊天 / Agent」能力提供对话入口。
- 已核对：五个 Studio 的 bundle 中 `问\s*Agent` 出现次数≥1；而 order/integration/data-core/app-discovery/wechat/factory 等非核心插件 bundle 中 `问 Agent` 出现次数为 0（即未做应用内嵌入，仅宿主全局对话）。

### 需要后续模型处理（如果纳入范围）
为 `zhiyun-data-studio`、`zhiyun-order-studio`、`zhiyun-integration-hub`、`agent-kanban`、`wechat-bot-manager`、`factory-6s` 等非核心功能应用补齐「应用内 Agent 对话框」，或明确其「宿主全局对话」即满足要求。当前交接以核心五大 Studio 的 18 模块为验收主口径。

---

## 6. 登录 / 权限 / 企业隔离（RBAC + 单租户实例）

设计（已在 `REQUIREMENT-CHANGES` 说明，本轮落地到权限建议矩阵展示与建议，服务端强鉴权为下一步）：

- 部署模型：**一套运行实例 = 一个企业**（单租户）。不同企业 → 不同独立实例，各自独立的数据库、知识库、模型/Agent 配置、数据目录。
- 同一企业内所有用户共享该企业实例下的 Agent、业务数据与知识库；用户仅按 RBAC 看到被授权范围。
- 角色（管理员/部门经理/财务/销售/采购/员工）决定可用 Agent（Studio/功能）、可访问数据与知识库范围。
- `#25 权限建议`（People Studio）用于生成「角色 × 权限」矩阵，识别缺失/超配并输出高危/关注/正常分级。
- 数据目录：各 Studio 后端默认使用独立 SQLite（`SERVICE_STUDIO_DB` 等），放在可写运行时数据目录 `.qwenpaw-runtime-data/<studio>/`。

### 落地顺序（给最强 GPT 的下一步）
1. 服务端鉴权与强制路由：把 Role → Agent/数据/知识库边界真正落到 API 层（当前仅前端展示矩阵与建议）。
2. 企业实例配置化：部署时读取企业标识，分配实例级数据目录与模型/Agent 配置。
3. 审计日志对接 `zhiyun-audit`：记录审阅人、动作、工件、Agent 上下文导出。
4. 统一 Workspace 数据核心：示例数据显式标记「模拟」，真实数据走 Excel 导入。
5. 非核心功能应用补齐应用内 Agent 对话框（见第 5 节）。

---

## 7. 本轮已修复问题（含等级）

| 问题 | 严重级 | 修复 |
| --- | --- | --- |
| 功能只返回 JSON 数组、无 GUI | P0 | `_gen_ui.py` 重构为真实输入 + 结果面板；五 Studio 全覆盖 |
| 后端数据目录只读导致运行 503 | P0 | 各 Studio 读取 `*_STUDIO_DB`；`start.mjs` 注入 `.qwenpaw-runtime-data` 可写目录 |
| 「问 Agent」被宿主胶囊按钮遮挡 | P1 | Topbar 右侧留白 `padding-right` |
| Agent 快捷指令/自然语言运行失败（text 缺 sample + 闭包读旧输入） | P1 | `sampleFor()` 兼容 `example`；`runModule` 支持 `overrideValue` |
| 「命中知识」恒为否与命中标准问答矛盾 | P2 | 命中知识改由 `matched_faq` 判断 |
| 测试脚本误报「人力分析」空态（可选子表） | P3 | 判定区分「可选子表空态」与「主结果空态」，已在 QA 报告注明 |

严重级：P0=阻断使用；P1=核心流程受损可绕过；P2=结果与预期不一致；P3=测试/提示类瑕疵。

---

## 8. 运行方式

### 8.1 直接启动（手动，含 DB 环境变量）

```powershell
$root='C:\AI\zhiyun-ai-os-workspace\.qwenpaw-runtime-data'
$env:QWENPAW_WORKING_DIR='C:\AI\zhiyun-ai-os-workspace\zhiyun-ai-platform\apps\qwenpaw-embedded\workspace'
$env:SERVICE_STUDIO_DB="$root\zhiyun-service-studio\service.db"
$env:SUPPLY_STUDIO_DB="$root\zhiyun-supply-studio\supply.db"
$env:SALES_STUDIO_DB="$root\zhiyun-sales-studio\sales.db"
$env:FINANCE_STUDIO_DB="$root\zhiyun-finance-studio\finance.db"
$env:PEOPLE_STUDIO_DB="$root\zhiyun-people-studio\people.db"
$env:DATA_STUDIO_DB="$root\zhiyun-data-studio\insights.db"
$env:ORDER_STUDIO_DB="$root\zhiyun-order-studio\orders.db"
$py='C:\AI\zhiyun-ai-os-workspace\zhiyun-ai-platform\apps\qwenpaw-embedded\runtime\qwenpaw\venv\Scripts\python.exe'
$wd='C:\AI\zhiyun-ai-os-workspace\zhiyun-ai-platform\apps\qwenpaw-embedded'
Start-Process -FilePath $py -ArgumentList @('-m','qwenpaw','app','--host','127.0.0.1','--port','8088') -WorkingDirectory $wd -WindowStyle Hidden -RedirectStandardOutput 'C:\AI\zhiyun-ai-os-workspace\.server.log' -RedirectStandardError 'C:\AI\zhiyun-ai-os-workspace\.server.log.err' -PassThru
```

### 8.2 官方入口（start.mjs）

在 `<repo>\apps\qwenpaw-embedded` 下用 npm/Node 运行 `scripts/start.mjs`，它会注入同样的 DB 环境变量、装插件、同步 PawApp，再 `qwenpaw app`。

### 8.3 启动自检
- `GET http://127.0.0.1:8088/api/version` → `{"version":"2.1.0"}`。
- 应用页：`http://127.0.0.1:8088/apps/zhiyun-service-studio`（其余 `<id>` 同理）。

---

## 9. 测试方法与回归结论

- 手段：Codex In-app Browser + Playwright，逐 Studio：点击左侧导航 `.zy-nav-item` → 点击示例按钮（按 `inputKind` 取「载入示例文本/一键导入示例数据/一键填入示例数据」）→ 点击运行按钮（`chipLabel`）→ 等待后端 → 抓取 `.zy-main` 文本。
- 判定：`clickedSample`/`clickedRun` 均为真；结果区无「暂无分析结果」；无 `"key":` JSON 泄露；右侧「问 Agent」可打开。
- 结论：**18/18 模块通过；5 个 Studio Agent 对话框通过；Data Studio 底座通过；全部 16 个插件均为组件化前端。**

---

## 10. 给后续模型的关键提醒

1. **不要手改生成出来的 `ui/index.js`**，改 `_gen_ui.py` 后重新生成并同步 workspace + runtime 两处。
2. `workspace/plugins`、`runtime/pawapps` 不在 git 中；仓库可交付内容为 `start.mjs` 与 `docs/**`。
3. 用户对「只有 JSON/无 GUI」极度在意；任何新增功能都必须以真实 GUI + 一键示例数据 + 可审阅结果交付，并把验证结果落到 `docs/qa`。
4. 用户要求「别只想着交接」——即功能要真正可用，而非只写文档。
5. 若测试在浏览器仍见 JSON，请先确认访问的是 `/apps/<plugin-id>`（应用页）而非后端接口地址，并做硬刷新（Ctrl+F5）清除旧 bundle 缓存。

## 11. 本轮交付文件清单

- 新增：`docs\product\REQUIREMENT-CHANGES-2026-08-24.md`
- 新增：`docs\qa\qa-report-GUI-rebuild-2026-08-24.md`
- 新增：`docs\handoff\HANDOFF_GPT_2026-08-24.md`（本文件）
- 修改：`apps\qwenpaw-embedded\scripts\start.mjs`（DB 环境变量注入）
- 修改：主 PRD 及各 Studio PRD 追加「需求变更（2026-08-24）」章节
- 生成：五个 Studio `ui/index.js`（workspace + runtime 双副本，已同步）

---

## 12. 第二迭代：登录与权限 + 系统应用直达路由（2026-08-24 追加，最终事实）

> 本节是「最强 GPT 接手」必须核对的权威事实。所有结论均以当前运行副本与真实浏览器验证为准，取代本文档第 1 节结尾的旧表述。

### 12.1 服务当前实际运行状态（勿依赖旧 PID）
- 服务地址：`http://127.0.0.1:8088`
- 启动方式：`node apps\qwenpaw-embedded\scripts\start.mjs`（仓库根 `zhiyun-ai-platform`），会注入 DB 环境变量、安装系统与外部插件、再 `qwenpaw app`。
- 健康自检：
  - `GET http://127.0.0.1:8088/api/zhiyun-data-core/health` → `200`
  - `GET http://127.0.0.1:8088/api/zhiyun-app-discovery/catalog` → `200`（系统应用 route 已为完整路由）
  - `GET http://127.0.0.1:8088/api/zhiyun-auth/config` → `200`
  - `GET http://127.0.0.1:8088/api/version` → `{"version":"2.1.0"}`
- 启动日志确认健康报告：`健康检查通过：13/13 个核心端点可用`。
- 注意：Windows 下 `Get-NetTCPConnection` 可能因权限拒绝显示「未监听」，**不代表服务未起**，以 HTTP 探测为准。

### 12.2 登录与权限（zhiyun-auth）
- 登录门覆盖所有页面；未登录进入登录页，校验通过进入工作区。
- 默认账号：`admin` / `Zhiyun@2026`（token 7 天，密码 salted SHA-256）。
- 登录页支持自定义背景图 + 品牌名（`workspace/branding/login-config.json`）。
- 接口前缀 `/zhiyun-auth`（宿主自动加 `/api`）：`config`、`login`、`me`、`agents/activate`、`users`、`branding`。
- 实测：`qa_auth_login.py` → 8/8 通过（登录门、错误密码拒绝、登录成功、退出、/me、用户权限、401）。

### 12.3 系统应用短路由缺陷（P0，已修复）
- 缺陷：`plugins/zhiyun-app-discovery/app_catalog.json` 中三个系统应用 `route` 为短名：
  - `zhiyun-app-discovery` → `/apps/app-discovery`
  - `zhiyun-data-core` → `/apps/data-core`
  - `zhiyun-audit` → `/apps/audit`
- 而插件 `plugin.json` 的 `meta.pawapp.entry_page` 与 `ui/index.js` 的 `registerRoutes` 均为完整路由：
  - `/apps/zhiyun-app-discovery`、`/apps/zhiyun-data-core`、`/apps/zhiyun-audit`。
- 影响：从「应用与项目中心」卡片的「打开」按钮（用 `item.route`）跳转短名 → 落回「应用」列表页，用户以为系统应用无 GUI。
- 已修正（源码 + 运行副本，两处一致）：
  - `/apps/app-discovery` → `/apps/zhiyun-app-discovery`
  - `/apps/data-core` → `/apps/zhiyun-data-core`
  - `/apps/audit` → `/apps/zhiyun-audit`

### 12.4 真实 GUI 验证证据
- 短路由三系统应用 body_len=1249，页面为「应用」列表。
- 完整路由 `/apps/zhiyun-data-core`：body_len=2089，出现「统一数据中心 / 数据预览 / 数据表 2 / 当前记录 300 / 真实 20 / 模拟 280 / 订单明细表」。
- 端到端：登录 → `/apps/zhiyun-app-discovery` → 点「统一数据中心」的「打开」（href=`/apps/zhiyun-data-core`）→ 落到真实面板，`VERDICT data_core_panel_rendered=True`。
- 截图：`_verify/data_core_after_click.png`（真实数据核心面板，右下角显示登录用户 `admin`）。

### 12.5 真实可运行的访问地址（给测试与后续模型）
- 业务 Studio：`/apps/zhiyun-data-studio`、`/apps/zhiyun-order-studio`、`/apps/zhiyun-service-studio`、`/apps/zhiyun-supply-studio`、`/apps/zhiyun-sales-studio`、`/apps/zhiyun-finance-studio`、`/apps/zhiyun-people-studio`、`/apps/zhiyun-integration-hub`
- 系统应用：`/apps/zhiyun-data-core`、`/apps/zhiyun-app-discovery`、`/apps/zhiyun-audit`
- 首次访问若仍见旧内容：**Ctrl+F5 硬刷新**。

### 12.6 给最强 GPT 的下一步（仍是遗留）
1. 把「角色 → Agent/数据/知识库」边界从「前端矩阵建议」落到 API 层强制路由。
2. 企业实例配置化：部署时读取企业标识，分配实例级数据目录与 Agent/模型配置。
3. 审计日志对接 `zhiyun-audit`：记录审阅人、动作、工件、Agent 上下文导出。
4. 验证 `zhiyun-app-discovery` / `zhiyun-audit` 完整路由下的真实面板（数据核心已确认，其余二者结构一致，需登录后目视复核）。


---

## 13. 第三迭代：双态运行体系（Demo / Production）规格（2026-08-24 追加）

> 本节是给最强 GPT 接手**双态运行体系**的权威起点。它把方向从「造一批演示数据」升级为「长期可持续运行的 Demo / Production 双态验证体系」。当前本段为**规格先行**，尚未实现代码。

### 13.1 新增权威文档（已落盘，务必先读）

- `docs/product/AI-OS-SIMULATION-DUAL-STATE-VISION.md` —— 19 项需求、命名规范、统一数据流、双态隔离、6 Epic、验收标准、真实数据源参考。
- `docs/product/DEMO-PRODUCTION-EPICS.md` —— 独立于 31 项能力台账的 6 Epic 计划台账（状态/范围/复用/缺口/验收/依赖）。
- `docs/product/PROJECT-PLAN.md`（Phase 4）—— 双态体系作为新的交付阶段，不与 `feature_progress.json` 31 项混用。

### 13.2 一句话验收

> 从全新数据库执行一次初始化命令，自动生成 2025-12-01 至当前日期持续运行的企业 AI 环境；任意日期可查用户/智能体/聊天/Token/应用/权限/文件/执行统计；可在演示环境与真实业务环境一键切换；所有统计可追溯到底层业务记录。

### 13.3 关键命名与数据流（本迭代定稿）

- 产品前台用「数据环境（演示环境/生产环境，或 Demo/Live）」；底层 `data_mode = demo|production`。
- 所有查询走统一 `DataContext`：`User → App → DataContext → Demo/Production Dataset → Database`。
- Demo/Production 隔离：记录带 `tenant_id / environment_id / data_source`；正式模式严禁读演示记录。
- 业务周期规则、统计闭环、避免假数据痕迹的完整要求见愿景文档 §5.5-§5.16。

### 13.4 6 Epic 实现顺序

`Epic 1 Enterprise Seeder → Epic 2 Agent Factory → Epic 3 Simulation Runtime → Epic 4 Time Machine → Epic 5 Data Platform → Epic 6 Data Integrity`。

各 Epic 的范围、复用现状、缺口、验收见 `DEMO-PRODUCTION-EPICS.md`。实现顺序由依赖决定，不要跳过 seeder / agent factory 直接造数据。

### 13.5 遗留与改造点（对最强 GPT）

1. **前端「模拟」标记**：`zhiyun-data-core` UI 仍有「生成 20 条模拟订单 / 生产数据」按钮与「模拟」徽标。按 §13.3 命名规范属于改造点；**本轮只记录，未改码**。实现 Phase 4 时一并替换为「数据环境 Demo/Live」措辞。
2. **服务端强制鉴权**：`zhiyun-auth` 的「角色 → Agent / 数据 / 知识库」边界目前是前端展示与矩阵建议，需在 API 层强制路由。
3. **企业实例配置化**：一套运行实例 = 一个企业（不同企业单独启动实例），在此之上再分演示/正式数据集；部署时读取企业标识并分配给实例级数据/模型配置。
4. **台账分离**：6 Epic 不写入 `feature_progress.json`；如需将 Epic 产出的能力入 31 项台账，先与 `scripts/verify-project-plan.mjs` 校验兼容。
5. **真实数据校准**：`C:/Users/garys/Downloads/` 下的真实 Excel（销售/采购订单执行表、应收/应付总账、工序、库存、物料清单、员工花名册等）作为 Epic 5 / Real Data Profiler 的校准来源，见愿景文档 §7。
6. **验证约定**：任何功能验收以真实浏览器 `/apps/<plugin-id>` + 一键示例数据 + 可审阅证据为准，不回退为“只有 JSON/无 GUI”。当前服务地址与访问方式见第 12 节。

---

## 14. 第四迭代（2026-08-25）：企业环境初始化器落地 + 服务端鉴权 + 回归

> 服务：`http://127.0.0.1:8088`（`/api/version=2.1.0`，健康检查 13/13 pass）
> 启动：仓库根执行 `node apps/qwenpaw-embedded/scripts/start.mjs`

### 14.1 新增 / 修复内容

1. **企业环境初始化器（`zhiyun-enterprise-seeder`）**：新增后端 `plugins/zhiyun-enterprise-seeder/enterprise_plugin.py`（约 47KB）与前端 `ui/index.js`（约 21KB 真实 GUI）。`start.mjs` 已接入 `qwenpaw plugin install ... --force` 自动安装到 `workspace/plugins/zhiyun-enterprise-seeder`。
2. **一次初始化全链路**：POST `/api/zhiyun-enterprise-seeder/seed` 生成企业/部门/用户/角色/权限/Agent/Skill/应用/数据源/会话/任务/Token/日志，落库 `enterprise.db`（多环境 `env_id` + `data_mode` 区分），并同步账号到 `auth/users.json`（默认密码同为 `Zhiyun@2026`）。
3. **修复环境隔离**：`_records` 对 `env_id` + `data_mode` 强制过滤，避免多环境串数据；`/records/{entity}` 返回行带 `data_mode` / `env_id`。
4. **服务端 Bearer 鉴权落地（本轮核心）**：
   - `/config`、`/summary`、`/records/{entity}` 需 `Authorization: Bearer <token>`；匿名返回 401。
   - `/seed` 仅 admin（非管理员 403）；`/records` 非管理员按 `data_scope`（enterprise/department/agent）过滤：`departments` 按部门、`org_users` 按部门或账号、`agents` 按绑定 agent、`sessions/tasks/token_usage` 按 agent、`operation_logs` 按用户。
   - 前端 `ui/index.js` 登录后自动注入 token，未登录先等待 `zhiyun:auth` 事件后加载。

### 14.2 实测证据（接口 + GUI）

| 场景 | 结果 |
| --- | --- |
| 匿名 `/config`、`/summary`、`/records/org_users` | 401 |
| admin 登录 `/config` | 200 |
| admin `/summary` | 200 |
| admin `/records/agents` | 9 行（全量） |
| admin `/records/org_users` | 50 行 |
| sales_02（member，agent=customer_followup，data_scope=department）`/records/agents` | 1 行（仅 customer_followup） |
| sales_02 `/records/org_users` | 13 行（仅销售部） |
| sales_02 `/records/sessions` | 全部 agent_id=customer_followup |
| 非管理员 POST `/seed` | 403 需要管理员权限 |
| admin POST `/seed` | 200（一次生成） |
| Playwright GUI 拟人交互 | **22/22 PASS** |

### 14.3 GUI 回归（22 项）

登录 → 页面标题 → 生成参数/环境概览/企业数据明细/生成并运行/智能体助手全部可见 → 统计卡 7 项 → 实体切换入口 11 → 表单默认企业名 → 生成成功 → 数据表有内容（11 行）→ 概览更新 → 切换智能体表格（10 行）→ Agent 抽屉打开 + 快捷指令 2。控制台无 JS 错误。截图：

- `docs/qa/screenshots/seeder-before.png`
- `docs/qa/screenshots/seeder-after-generate.png`
- `docs/qa/screenshots/seeder-agent-dock.png`

### 14.4 台账现状（未全部完成）

当前 31 项台账：**completed 13 / testing 17 / in_progress 1**。服务端鉴权目前仅覆盖 `zhiyun-auth`（login/me/users/branding/agents-active）与 `zhiyun-enterprise-seeder`（config/summary/records/seed）；各业务 Studio 的 `/records` 等仍走各自 DB，尚未统一接入 RBAC。

### 14.5 遗留（P1/P2）

- **P1**：服务端 RBAC 只落到 seeder 与 auth 自身；各 Studio/Data Core 的业务接口仍无用户级强制路由。
- **P1**：前端仍见「模拟/Mock」标识（`zhiyun-data-core` 的「模拟订单/生产数据」），命名规范应改为「数据环境 Demo/Live」（本轮只记录未改码）。
- **P2**：旧缓存会导致登录后界面卡住，需 Ctrl+F5 硬刷新。
- **P2**：真实 Excel（`C:/Users/garys/Downloads/`）作为 Epic 5 Real Data Profiler 校准来源，尚未接入。
- **P2**：`zhiyun-enterprise-seeder` 前端「生成并运行」使用真实后端，但不同企业实例边界的部署脚本（不同企业单独启动）仍是人工约定，未做到配置化一键起多实例。

---

## 15. 第五迭代（2026-08-25 晚）：Seeder 统计口径修复 + 一致性提速 + 前端回归修复

> 服务：`http://127.0.0.1:8088`（`/api/version=2.1.0`，健康检查 13/13）
> 启动：仓库根执行 `node apps/qwenpaw-embedded/scripts/start.mjs`
> 当前监听 PID：由 `start.mjs` 拉起的 `node`（wrapper）内嵌 `python`（QwenPaw 2.1.0）。

### 15.1 本段目标

攻克「数据可追溯 / 统计口径 / 一致性」三件事，并修复前端整页崩溃回归。

### 15.2 改动清单

| 文件 | 改动 |
| --- | --- |
| `plugins/zhiyun-enterprise-seeder/enterprise_plugin.py` | ① `files.created_at` 由 `_now()` 改为按历史随机日生成；② `/summary` 新增 `files/downloads/logins` 维度并支持 `start_date/end_date` 范围过滤；③ SCHEMA 新增 5 条索引；④ `_integrity_report` 补齐污染行/`overall_failed`/`perm_violations`/`file_count/orphan_files/download_rows/orphan_downloads/file_download_sum/login_count`；⑤ 修复 `orphan_files` 子查询误用索引导致的 >120s 卡顿 |
| `plugins/zhiyun-enterprise-seeder/ui/index.js` | `ENTITIES` 增加 `files/file_downloads/login_activity`；`statItems` 增加 `文件/下载/登录`；**修复** `["Token","token_total"]` 后缺失逗号导致的整页崩溃 |

### 15.3 验证事实（本轮实测）

| 项 | 结果 |
| --- | --- |
| 健康检查 | 13/13 pass |
| 新环境 `env_75790ea7ba`（Demo） | sessions=19201、tasks=38474、token=43505857、files=21842、downloads=40609、logins=5802 |
| 范围 `2026-08-01..2026-08-20` | sessions=1716、tasks=3439、files=1950、downloads=3618、logins=539 |
| `files.created_at` 分布 | MIN=2025-12-01、MAX=2026-08-25、distinct=230 天 |
| `records/files`、`records/file_downloads`、`records/login_activity` | 均 200，返回真实行 |
| `/integrity` | total=13 passed=13 failed=0 healthy=true，约 1.1s |
| UI 服务端渲染 | 文件/下载/登录统计卡 + 14 个实体 chip 正常；数据一致性 13/13 |

### 15.4 关键经验 / 注意事项

- **`files.created_at` 会导致范围过滤视觉失真**：之前所有文件都落在种子当天，`/summary` 传任意范围都得到相同文件数。现改为按历史日分布，修正后范围查询返回部分计数。
- **PowerShell 转义陷阱**：在 PS 中拼写含反引号（Markdown 行内代码）的字符串，反引号会被当作转义符破坏内容（如 `` `files` `` 变成 `` `f``+`iles`，**`total**` 变成 tab+`otal`）。写 Markdown 时优先用单引号 here-string（`@'...'@`）或逐行写入。
- **`apply_patch` 在本环境被拒**：统一用 PowerShell 行级/替换编辑，每次锚点校验 + `py_compile` / `node --check`。
- **`Get-NetTCPConnection` 在受限沙箱内读不到监听状态**（返回空），判断服务是否存活以 HTTP 健康报告为准。
- **进程停止**：`taskkill` 可能报 Access denied，改用 `Stop-Process -Id <id> -Force`；`start.mjs` 会 `--force` 重装 6 个核心插件 + 8 个外部 PawApp，源码改动重启后生效。

### 15.5 本次修复的 BUG（分级）

| 级别 | 问题 | 根因 | 修复 |
| --- | --- | --- | --- |
| P1 | 前端「企业环境初始化器」整页崩溃（页面出现异常） | `statItems` 数组中 `["Token","token_total"]` 之后缺逗号，`["文件","files"]` 被当作下标运算，数组出现 `undefined`，`item[0]` 抛错 | 补逗号 + 同步运行态 bundle |
| P1 | `files` 不随时间范围变化 | `files.created_at` 用 `_now()` | 改为历史随机日生成 |
| P2 | `/integrity` 超过 120s | 子查询误用索引 | 新增 `idx_tasks_env_task`（COVERING INDEX），降至约 1.1s |

### 15.6 遗留（P1/P2，同 §14.5 叠加）

- 各 Studio 业务接口统一接入 RBAC 强制路由。
- 前端「模拟/Mock」标识改为「数据环境 Demo/Live」。
- 不同企业独立实例的部署脚本配置化。
- Epic 5 真实 Excel 校准接入。
- 模型提供方 `kilo/kilo-auto/free` 不可达（Agent 对话可能报模型不可用），与平台健康无关。

## 16. 迭代 16：Data Core Demo/Production 双态隔离（2026-08-25 服务重启已验证）

### 16.1 这轮做了什么

把 `zhiyun-data-core` 从「真实/模拟」单维度升级为「演示 Demo / 正式 Live」双态环境隔离，并将 schema 由 v2 升到 v3。

### 16.2 改动清单

| 文件 | 改动 |
| --- | --- |
| `plugins/zhiyun-data-core/data_core.py` | `SCHEMA_VERSION=3`；`data_batches/data_records` 新增 `data_mode TEXT NOT NULL DEFAULT 'demo'`；v3 迁移块（旧库 `ALTER TABLE` + `idx_records_mode`/`idx_batches_mode`）；`list_entities` 返回 `demo_count/production_count`；`list_records/search_records/list_batches` 支持 `data_mode` 过滤；`import_rows` 默认 `production`；`generate_orders/generate_production` 默认 `demo` |
| `plugins/zhiyun-data-core/data_core_plugin.py` | `/entities`、`/records/{entity}`、`/orders`、`/batches` 支持 `data_mode`；`/imports/{entity}/commit`、`/simulate/orders`、`/simulate/production` 支持 `data_mode`；健康版本 `0.8.0` |
| `plugins/zhiyun-data-core/agent_tools.py` | `query_enterprise_orders`/`generate_simulated_orders` 增加 `data_mode`，默认 `demo`；「模拟」改「演示」 |
| `plugins/zhiyun-data-core/ui/index.js` | `dataMode` 状态；「数据环境 演示 Demo / 正式 Live」；来源「已导入 / 系统生成」；「数据环境」列；「演示数据 / 正式数据」统计卡 |
| `plugins/zhiyun-data-core/plugin.json` | `version=0.8.0`，描述改「演示/正式数据环境服务」 |
| `scripts/qa/validate_data_core_v3_migration.py` | 新增离线 v2→v3 迁移验证脚本（SQLite backup 一致快照，不碰线上库） |

### 16.3 验证事实（本轮实测）

| 项 | 结果 |
| --- | --- |
| 迁移离线验证 | 快照 `schema_version 2→3`，迁移日志 `[2,3]`，旧 300 条订单归 `demo`，demo/production 写入隔离，`list_entities` 计数正确，`RESULT | ALL_PASS` |
| Data Core 健康 | `version=0.8.0`、`schema_version=3`、`integrity=ok`、`status=available` |
| `/entities`（无过滤） | orders demo=300 prod=0；production demo=0 prod=0 |
| `/entities?data_mode=demo` | 仅 orders（demo=300） |
| `/entities?data_mode=production` | 空（本轮未做正式导入），隔离成立 |
| `/records/orders?data_mode=demo&limit=3` | 3 条 `data_mode=demo` |
| `/batches?data_mode=demo` | 返回 demo 批次 |
| `/apps/zhiyun-data-core` | `200 text/html`，GUI 正常（非 JSON） |
| Seeder `/summary`、`/integrity` | `env_75790ea7ba` 13/13 pass，sessions=19201、tasks=38474、token=43505857 |

### 16.4 BUG 分级

本轮无新增 P1/P2 代码 BUG。运行库从 v2 升 v3 的迁移在真实快照上一次性通过，消除了「旧库缺 `data_mode` 列导致查询失败」的 P0 潜在风险（采用重启前离线快照验证，不冒险直接升级线上库）。

### 16.5 遗留与风险

- `data_mode=production` 当前为空；后续用真实 Excel 导入（`imports/{entity}/commit?data_mode=production`）后需复验正式/演示两张数据集互不污染。
- 服务重启由 `apps/qwenpaw-embedded/scripts/start.mjs` 拉起，每次启动会 `--force` 重装 6 个核心插件 + 8 个外部 PawApp，源码改动必须重启才生效。
- 模型提供方 `kilo/kilo-auto/free` 不可达，Agent 对话可能报「模型不可用」，与平台健康无关。

## 17. Agent Factory（Epic 2）本轮交接（2026-08-25 服务重启后）

### 17.1 本轮产出

- 新增 `plugins/zhiyun-enterprise-seeder/agent_factory.py`：`MODEL_CATALOG`（本地 Qwen2.5 7B/14B/72B + 云端 Qwen-Max/Plus）、`TOOL_CATALOG`（22 个真实工具）、`CATEGORY_DEFAULT_TOOLS`、`APP_ACCESS_BY_DEPT`，以及 `build_agent_config / validate_agent_config / persist_bindings / reconcile_bindings / make_agent_row / new_agent_id / resolve_model_id / resolve_tools / resolve_apps`。
- `enterprise_plugin.py` 新增 `AgentSpecRequest`、`AgentReconcileRequest` 与 5 条路由：`GET /agent-factory/catalog|templates|bindings`、`POST /agent-factory/validate|reconcile`；`_require_auth` / `_require_admin` 鉴权覆盖。
- 新增 `plugins/zhiyun-enterprise-seeder/test_agent_factory.py`：7 个单测全部通过。
- `ui/index.js` 新增 `AgentFactoryPanel` 并挂载到 `EnterpriseSeeder`；`node --check` 通过。

### 17.2 实机验证结果

- `GET catalog`：模型 5 / 工具 22 / 岗位默认工具 9 组 / 部门应用 8 组。
- `GET templates`：返回 `manufacturing`、`finance` 两套模板，含完整模型/技能/工具/应用/指标。
- `GET bindings`：初始为空（尚未落地），`env_id=""`、`data_mode=""`。
- `POST reconcile`（`data_mode=demo`）：`ok=true`、`reconciled=57`。
- `POST validate`（合法）：`ok=true`、`errors=[]`；`POST validate`（语义非法：未知工具/部门/类别）已由 500 修复为 `200`、`ok=false`、`errors=[{"field":"tools","message":"工具未在编目注册：not_a_real_tool"}]`。

### 17.3 本轮修复的 BUG（P1）

- `build_agent_config` 对未注册工具取 `TOOL_CATALOG[t]` 抛 `KeyError`，导致 `validate` 返回 500。
- 修复：改用 `TOOL_CATALOG.get(t, {...})` 兜底，未知工具保留在 config 供校验报告；`persist_bindings` 落盘时跳过未注册工具。
- 验证：单测 7/7、`py_compile` 通过、重启后接口复测符合预期。

### 17.4 服务运行状态

- 当前服务已在 `http://127.0.0.1:8088` 运行，`/api/healthz` 正常；`health-report.mjs` 13/13 核心端点通过。
- 运行目录插件已同步最新源码（hash 一致），Agent Factory 改动已生效。

### 17.5 遗留与风险

- `models` 表新增不改 `agents.model` 列（agent 行仍存模型名 `cfg["model"]["name"]`）。
- `data_mode=production` 当前为空；正式导入后需复验双态隔离。
- 本地模型服务不可达（`kilo/kilo-auto/free`）会阻断真实 Simulation Runtime，不影响平台健康。

## 18. Demo/Production 双态端到端验收（2026-08-25 服务重启后，本轮最后一步）

> 在 Agent Factory（§17）之后完成整链路验收，验证「从全新 DB 一次初始化 → 完整企业环境 → 一致性 → 双态隔离 → Time Machine」。接口统一 `Authorization: Bearer <admin token>`。

### 18.1 全新 Demo 种子

`POST /api/zhiyun-enterprise-seeder/seed`，body：`{"template":"manufacturing","enterprise":"未来智造验收","start_date":"2025-12-01","end_date":"2026-08-25","scale":50,"departments":6,"agents":9,"activity":"medium","data_mode":"demo","seed":8821}`。

耗时约 10.3s，返回：`env_id=env_4bc33f5caa`，268 天，50 用户，9 Agent，19097 sessions，38132 tasks，43446082 token，success 35107 / failed 3025。

`GET /integrity?env_id=env_4bc33f5caa&data_mode=demo` → `ready healthy=True total=13 passed=13 failed=0`，约 1.5s。关键项：Token 一致性通过；孤儿会话/任务/文件/下载全 0；无 100% 成功率（整体失败 3025）；Token 日波动采 230 天中 104 个下降日。

### 18.2 Production 种子

`POST /api/zhiyun-enterprise-seeder/seed`，body：`{"template":"manufacturing","enterprise":"正式业务验收","start_date":"2026-01-01","end_date":"2026-08-25","scale":30,"departments":6,"agents":9,"activity":"low","data_mode":"production","seed":7712}`。

耗时约 4.4s，返回：`env_id=env_9955444109`，237 天，30 用户，5621 sessions，11293 tasks。`GET /integrity` → `13/13 pass`。

### 18.3 Time Machine 范围切换

`GET /summary?env_id=env_4bc33f5caa&data_mode=demo&start_date=2026-03-01&end_date=2026-05-31`：sessions=6644、tasks=13388、token=15145126、files=7664、downloads=14262、logins=2016；`range` 回显 `2026-03-01~2026-05-31`。sessions/tasks/token/files/downloads/logins 六类统计均随时间段切换。

### 18.4 双态隔离

`/records/sessions` 逐条核对：demo 会话全部 `env_id=env_4bc33f5caa / data_mode=demo`（如 `s_37ea809622d9` → 用户 `finance_14` / 智能体 `finance_invoice` / 应用 `finance_center`）；production 会话全部 `env_id=env_9955444109 / data_mode=production`。无交叉污染。

### 18.5 结论与快照

**通过。** 全新 DB 一次初始化即可生成 2025-12 至当前完整企业环境（Demo/Production 各一套）；任意时间段可查；Demo/Production 一键切换与隔离成立；统计可追溯到底层业务记录；前台无「模拟/Mock」痕迹。

### 18.6 遗留与风险（供下一模型/迭代）

- **Epic 3 Simulation Runtime**：本迭代已从「后端直接插模拟行」升级为可配置规则驱动运行时（业务事件 → Agent → Skill/Tool → 结果 → 下载 → Token → 统计），详见 §19；`planned` 已改为 `test`。风险收敛为：模型提供方 `kilo/kilo-auto/free` 不可达，仅真实模型驱动执行不可用，规则驱动运行时不受影响。
- **Epic 4 Time Machine**：`/summary` 范围过滤已覆盖 sessions/tasks/token/files/downloads/logins；需扩展到多 Studio Dashboard 同步与工作日/月度/企业增长规律。
- `models` 表新增不改 `agents.model` 列。
- 本地模型服务不可达不影响平台健康，但会阻断真实 Agent 对话。
## 19. Simulation Runtime（Epic 3）本轮交接（2026-08-25 服务重启后）

> 把「从零初始化」升级为可追溯的业务事件运行时。实现于 `plugins/zhiyun-enterprise-seeder/simulation_runtime.py`（自包含，供 seeder 与独立 `/simulation` 接口共用），并同步到运行时 bundle（SHA256 一致）。

### 19.1 目标与核心契约

「直接插行」改为可追溯事件闭环：

```
业务事件 → Agent 执行 → Skill/Tool 调用 → 结果工件 → 下载 → Token → 用户行为 → 统计
```

- `build_day_events`：只构建内存计划，不写库。
- `execute_day_events`：将计划写入 sessions/tasks/files/file_downloads/token_usage，并为每一步写一条 `business_events` 审计行，使任何统计都能追溯到具体业务事件。

### 19.2 代码与能力增量

- `_stable_day_seed(seed, di, env_id, day)`：用 `zlib.crc32("env_id|day")` 生成跨进程、跨调用稳定的随机种子，替代不稳定的内建 `hash`，保证跨进程确定性。
- `_clear_day(conn, env_id, data_mode, day)`：`run_interval(force=True)` 先清空该环境该日的运行期业务表（file_downloads/files/tasks/sessions/token_usage/business_events）再写入，避免重复插入。
- `log_business_event` / `list_events`：业务事件审计写入与查询（支持 `env_id/data_mode/day`、limit）。
- `preview_interval` / `run_interval`：范围预览（只读，不写库）与范围执行（`force` 幂等）。
- `status` / `list_envs`：运行时状态与环境审计计数。

### 19.3 新增端点

`enterprise_plugin.py`（均带 Bearer 鉴权）：

- `GET /simulation/status`：环境列表 + 全局审计计数。
- `GET /simulation/preview`：按范围预览（只读）。
- `POST /simulation/run`：按范围运行；`force=true` 强制重写（幂等）。
- `GET /simulation/events`：业务事件审计记录，支持日期范围与 `limit`。

### 19.4 单测

运行目录 `plugins/zhiyun-enterprise-seeder`：

```powershell
python -m unittest -v test_simulation_runtime
```

结果 **6/6 OK**，新增 `test_run_force_replaces_without_duplicates` 幂等用例。

同批回归：`test_agent_factory` 7/7 OK；`test_data_core` 16/16 OK。

### 19.5 实机验收（接口证据）

- `GET /simulation/status`：9 个环境，`totals` 含 business_events/sessions/tasks/files/tokens。
- `GET /simulation/preview`（demo，2026-08-20 ~ 2026-08-24）：5 天 / sessions 267 / calls 549 / tokens 598965；只读不写库。
- `POST /simulation/run`（force=true，同区间，seed=1）：
  - 第一次：days_written=4，sessions 267 / calls 540 / success 488 / failed 52 / tokens 609749。
  - 第二次（同参数 force=true）：结果完全一致，证明 force 重写不重复插入。
- `GET /simulation/events`：返回完整 `session → task → file → download` 链路，含 `agent_id / skill_id / tool_id / tokens / latency`。
- Integrity（demo 与 production 均 `13/13 passed, healthy=true`）。
- 双态隔离：demo 事件全归 `env_4bc33f5caa`；production `events=[]` 未污染。

### 19.6 修复 BUG（P2）

- `force=true` 重跑会在既有业务表上再插一遍，导致统计翻倍。
- 修复：`_clear_day` 在写入前清理该日运行期业务表；单测与接口复测均通过。

### 19.7 今日快照

- Demo：`env_4bc33f5caa`，50 用户 / 9 Agent / 18971 会话 / 37897 任务 / 21529 文件 / 39932 下载 / 5712 登录 / `business_events=1764`。
- Production：`env_9955444109`，30 用户 / 9 Agent / 5621 会话 / 11293 任务 / 6495 文件 / 12035 下载 / 2348 登录 / `business_events=0`。

### 19.8 残留与下一步

- ✅ 已落地：`_clear_day` 扩展清理 `login_activity / operation_logs`；`build_day_events/execute_day_events` 写入登录/操作日志并记 `business_events`。
- ✅ 已落地：`business_events` 纳入 `/integrity`，新增第 14 项 `business_event_scope`（无孤儿引用），demo 与 production 均 14/14。
- 本地模型服务不可达，真实模型驱动执行不可用；规则驱动运行时不受影响。
- 前端 GUI：`ui/index.js` 已有 `SimulationRuntimePanel`（环境下拉、日期输入、预览/运行按钮、最近业务事件表格）与 `AgentDock`，已挂载到 `EnterpriseSeeder`，`node --check` 通过；待真实浏览器截图补验（见 §19 上线说明 / QA 报告 §14）。

## 20. Epic 4 趋势分析（/analytics/trends）本轮交接（2026-08-25 服务重启后）

### 20.1 背景与目标

- 用户诉求：完整整理本轮更新与记录，产出完整交接文档，供最强 GPT 接手检查。
- 本小节记录「服务重启后」在 Epic 4 Time Machine 上的最后一次补强：把原本只有 `/summary` 范围过滤的能力扩展为真正的趋势分析（日/周/月、工作日/周末、增长），并同步到前端趋势卡。

### 20.2 服务重启方式与当前状态

- 启动命令：`node apps\qwenpaw-embedded\scripts\start.mjs`。
- 当前服务进程 PID `27732`，监听 `http://127.0.0.1:8088`，版本 2.1.0。
- 健康检查 `13/13 通过`。
- 管理员 token：`C:\AI\zhiyun-ai-os-workspace\.admin_token.txt`；接口统一 `Authorization: Bearer <token>`。
- 日志：`.qwenpaw-restart.out.log` / `.qwenpaw-restart.err.log`（工作区根）。
- 后台 session `39086` 存活中，测试时不要中断。

### 20.3 接口契约（/analytics/trends）

- `GET /api/zhiyun-enterprise-seeder/analytics/trends`，Bearer 鉴权（`_require_auth`）。
- 查询参数：`env_id`（不传默认取最新 meta）、`data_mode`（demo/production）、`start_date` / `end_date`（YYYY-MM-DD）、`granularity`（默认 `day`；合法 `day/week/month`；非法自动回退 `day`）。
- 返回结构示例：

```json
{
  "granularity": "day",
  "series": [ { "period": "2026-08-25", "label": "...", "sessions": 0, "tasks": 0, "tokens": 0, "files": 0, "downloads": 0, "logins": 0, "operations": 0 } ],
  "workday_avg": { "sessions": 32, "tokens": 72729, "logins": 11 },
  "weekend_avg": { "sessions": 3, "tokens": 6945, "logins": 1 },
  "growth": { "agents": [ { "period": "2026-08", "label": "2026年08月", "total": 6 } ], "users": [ { "period": "2026-08", "label": "2026年08月", "total": 27 } ] },
  "summary": { "sessions": 5621, "tasks": 11293, "tokens": 12763511, "calls": 11293, "files": 6495, "downloads": 12035, "logins": 2348, "operations": 130 }
}
```

### 20.4 实现位置

- 后端：`plugins/zhiyun-enterprise-seeder/analytics.py`（`build_trends`、`_first_activity_cumulative`、`_ACTIVITY` 映射、`_SERIES_KEYS`）。
- 路由：`plugins/zhiyun-enterprise-seeder/enterprise_plugin.py` 新增 `@router.get("/analytics/trends")`，顶部 `try: from .analytics import build_trends except ImportError` 兼容导入。
- 前端：`plugins/zhiyun-enterprise-seeder/ui/index.js` 新增 `TrendSpark` / `TrendPanel`、粒度 state、`loadTrends`；`RANGE_PRESETS` 已含 `last_month/quarter/year`；`rangeFor` 实现对应日期计算；在「环境概览」与「数据一致性」之间插入「趋势分析」卡。
- 源码副本与运行副本已同步（`apps\qwenpaw-embedded\workspace\plugins\zhiyun-enterprise-seeder\ui\index.js`），二者 MD5 一致。

### 20.5 修复的两个真实后端 BUG（均为 P2，已闭环）

1. `analytics.py::_first_activity_cumulative`：SQL 中 `{group_col}` 未做 f-string 插值，SQLite 抛 `unrecognized token "{"`。已改为 f-string。
2. 最后一个月 cutoff 被统一 clamp 到该月月末：当查询的 `end` 落在当月 1 日时会把当月活动全部排除、导致 `growth=0`。已改为当 `cur == end_ref` 时 `cutoff = end_day`。

### 20.6 前端 BUG（低优先级，已修复）

- `TrendSpark` 在区间仅 1 个点（「本月」+「月」粒度）时只画左角点 + 退化三角，视觉上像空图。
- 已改为单点时居中标尺点 + 底部基线；CRLF 保留、无 BOM、`node --check` 通过；源码与运行副本同步。

### 20.7 单测结果

- `test_analytics.py` 7/7 OK。
- 全套 seeder 单测（`test_analytics + test_agent_factory + test_simulation_runtime`）20/20 OK。
- 运行目录：`plugins/zhiyun-enterprise-seeder`；Python：`apps\qwenpaw-embedded\runtime\qwenpaw\venv\Scripts\python.exe`。
- 命令：`python -m unittest test_analytics test_agent_factory test_simulation_runtime -v`。

### 20.8 实机接口证据（production `env_9955444109`）

- 日粒度 `2026-01-01 ~ 2026-08-25`：`summary` 为 sessions=5621 / tasks=11293 / tokens=12763511 / calls=11293 / files=6495 / downloads=12035 / logins=2348 / operations=130（与 `/summary` 一致）；`workday_avg.sessions=32`、`weekend_avg.sessions=3`；`growth` 末端 agents=6、users=27。
- 跨粒度 `2026-08-01 ~ 2026-08-25`：周粒度 5 桶、月粒度 1 桶；`summarySessions=718` 与日粒度一致。
- 前端 Playwright：登录 `admin / Zhiyun@2026` 后 `/apps/zhiyun-enterprise-seeder` 完整渲染；趋势卡含日/周/月按钮、总量、工作日/周末均值、六条曲线；切「本月」后顶部 KPI 与趋势同步为 `2026-08-01 ~ 2026-08-25 / 会话 718 / 任务 1432 / Token 1647625 / 文件 837 / 下载 1487 / 登录 314`；切「月」粒度后序列变「近 8 个月」。

### 20.9 口径说明（重要，避免被误判为不一致）

- `/summary` 的 `agents=9 / org_users=30` 为**配置规模**。
- `growth` 曲线为**首次活跃累计**：只有产生会话活动的实体才计数，故末端 `agents=6 / users=27`。
- 两者口径不同，非 Bug。前端按「累计活跃」语义标注。

### 20.10 证据截图（已入库 `docs/qa/screenshots`）

- `docs/qa/screenshots/seeder_trend_viewport.png`：趋势面板全貌。
- `docs/qa/screenshots/seeder_trend_chart.png`：六条曲线（日粒度 / 237 日）。
- `docs/qa/screenshots/seeder_trend_month_range.png`：修复前单点空图。
- `docs/qa/screenshots/seeder_trend_fixed_single.png`：修复后单点 + 基线。
- `docs/qa/screenshots/seeder_login.png`、`seeder_full.png`：登录与主界面。

### 20.11 技术约束 / 同步要求

- 源码改动必须同步运行副本：`apps\qwenpaw-embedded\workspace\plugins\<id>\ui\index.js`，否则浏览器看不到，只会见到裸 json / 空 GUI。
- 行尾注意：`analytics.py` / `test_analytics.py` 为 LF；`ui/index.js` 与文档通常为 CRLF；改动前先检查目标行尾，避免引入 BOM。
- 前端 UI 需 `Ctrl+F5` 清缓存刷新；访问应用使用 `/apps/<plugin-id>` 完整路由而非短名。
- 不要删除 `.bak`；不要改动 `feature_progress.json` / `scripts/verify-project-plan.mjs`。
- 本地模型服务 `kilo/kilo-auto/free` 不可达，仅真实模型驱动执行不可用，规则驱动运行时不受影响。

### 20.12 残留与下一步

- ✅ 已落地：`/analytics/trends` 日/周/月 + 工作日/周末均值 + Agent/用户增长 + 前端趋势卡与档位/粒度联动。
- ✅ 已完成：多 Studio Dashboard 同步（DataContext 广播，见 20.13）。
- ⏳ 待补：模型驱动执行替换规则引擎；自动修复策略与每日定时报告（Epic 6）。
- 下一次接手建议：进入 `zhiyun-ai-platform` 仓库，确认服务存活（PID 27732 / http://127.0.0.1:8088），再跑 `python -m unittest test_analytics test_agent_factory test_simulation_runtime -v` 快速回归。
### 20.13 DataContext 广播（多 Studio 时间同步，Epic 4 收尾）

**改动（源码与运行副本已同步，SHA256 一致）**
- `plugins/zhiyun-data-core/data_core.py`：新增模块常量 `CONTEXT_KEY="active_context"`、`_empty_context/get_context/set_context/_date_field_for`；context 存于 `data_core_meta` 表（`key=active_context`），校验 `data_mode ∈ {demo,production}` 与 `YYYY-MM-DD` 日期且起≤止；`list_records/search_records` 新增可选 `start_date/end_date`，在 `data_mode`/日期未显式传参时自动套用活动 context。
- `plugins/zhiyun-data-core/data_core_plugin.py`：新增 `ContextSet(BaseModel)` 与 `GET /context`、`PUT /context` 路由；`/records/{entity}` 与 `/orders` 增加 `start_date/end_date` 查询参数。
- `plugins/zhiyun-enterprise-seeder/ui/index.js`：新增 `publishDataContext`，在 `loadSummary/loadAll/doGenerate/agentCommand` 成功后自动向 Data Core `PUT /context` 广播；失败仅 warn 不阻塞主流程。

**实机验收（服务重启后）**
- `GET /api/zhiyun-data-core/context` 初始为空 context；`PUT` 设置 `demo + 2026-08-20~08-22` 后 `GET /orders` 自动返回 25 条且全部落在窗口内。
- 打开 `/apps/zhiyun-enterprise-seeder` 后 context 自动变为 `env_9955444109 / production / 全量窗口`（`loadAll -> publishDataContext` 生效）。
- 外部 Studio `/apps/zhiyun-data-studio` 未传参调用 `/zhiyun-data-core/orders` 即自动继承：demo 全量「订单总数 100 / 风险表填充」，production「订单总数 0 / 空」。
- 证据截图：`docs/qa/screenshots/studio-inherit-demo.png`、`docs/qa/screenshots/studio-inherit-production.png`。

**残留**
- 外部 Studio（第三方 GitHub 仓库）前端来源列原显示「模拟数据」标签，已在本轮统一改口为「演示数据」（见 §21）；因源仓库 SHA 锁定，干净克隆重建会回退，需在源项目推进新 SHA 并更新 pawapps.lock.json。
- 后续每次改 `data_core.py` / `data_core_plugin.py` / seeder `ui/index.js` 须同步 `apps\qwenpaw-embedded\workspace\plugins\<id>` 下运行副本并重启。

### 20.14 Epic 6 Data Integrity 收尾（2026-08-25 服务重启后）

**目标**：补齐 Epic 6 剩余缺口——安全自动修复策略、每日一致性报告、历史轨迹。

**后端 `plugins/zhiyun-enterprise-seeder/enterprise_plugin.py`**
- 新增表：`integrity_reports`（每日快照）、`integrity_repair_log`（自动修复审计），含索引。
- 新函数：`_repair_integrity`、`_daily_integrity_report`、`_integrity_history`；`_ensure_schema` 启动钩子自动生成当日报告。
- 新路由：`GET /integrity/daily`、`GET /integrity/history`、`POST /integrity/repair`（repair 仅管理员，`_require_admin`）。
- 新 Agent 工具：`run_integrity_repair`、`query_daily_integrity_report`、`query_integrity_history`。
- 修复规则（只做安全、可逆、不伪造数据项）：删除孤儿会话/任务/文件/下载、回写 `files.download_count`、回填员工智能体绑定；人工决策项（登录回查 / 权限 / 成功率方差 / 日波动 / 业务事件链）不改动，全部写入审计。

**前端 `ui/index.js`**
- 数据一致性卡片新增三按钮：自动修复 / 运行检查 / 今日快照；按钮下渲染「今日快照·日期·通过 N/M」摘要；自动修复结果写入 Agent 抽屉。

**单测 `test_integrity.py`（3/3 OK）**
- `TestIntegrityRepair::test_repair_cleans_orphans_and_recalcs`、`test_repair_empty_env`
- `TestIntegrityDailyReport::test_daily_report_idempotent_and_history`
- 旧基线 `test_agent_factory + test_simulation_runtime + test_analytics` 20/20 OK，合计 23/23。

**实机验收（服务重启后，Bearer 鉴权）**
- `GET /integrity/daily?env_id=env_4bc33f5caa&data_mode=demo`：`total=14 passed=14 failed=0 healthy=true persist=inserted`。
- 同日重复：`persist=updated`（幂等）。不带 env：自动取最新 `env_9955444109 / production`，14/14。
- `POST /integrity/repair`：`ok=true fixed_checks=[] remaining_checks=[]`（环境已健康），留审计。
- `GET /integrity/history`：`count=1`，按 `report_day DESC`，含 `total/passed/failed/healthy/created_at/updated_at`。
- 无 token：`HTTP 401`（repair 仅管理员）。

**本机发布/计划门禁**
- `node scripts/verify-release.mjs`：通过（AI-OS 发布门禁通过）。
- `node scripts/verify-project-plan.mjs`：通过（31 项；已完成 13，测试中 17，开发中 1，计划中 0）。
- 修复了前一轮遗留的版本失联：`app_catalog.json` Data Core `0.7.0 -> 0.8.0`、`verify-phase2-acceptance.mjs` 同步 `0.8.0`、`test_search_engine.py` 审计路由 `/apps/audit -> /apps/zhiyun-audit` 及 Data Core 版本 `0.8.0`。

**证据**：`docs/qa/qa-report-integrity-repair-2026-08-25.md`。

**残留**：`model-health` 显示本地 `kilo/kilo-auto/free` 不可达，仅影响真实模型驱动执行，与平台健康无关；GUI 本轮未采集浏览器截图（工作区无 headless 浏览器），由人工在 `/apps/zhiyun-enterprise-seeder` 复核。


## 21. 前台禁止文案治理：模拟 / Mock / 测试 → 演示 / Demo / Live（2026-08-25 服务重启后）

> 依据双态运行体系的产品规则「产品前台不出现『模拟、Mock、测试』等影响展示效果的标记」，本轮对所有用户可见前端统一改口，底层 `source_type=simulated/real` 与 `data_mode=demo/production` 契约保持不变。

### 21.1 改动清单

- 五个模板 Studio（finance / sales / supply / service / people）由 `_gen_ui.py` 统一生成，改的是唯一事实来源：
  - `_gen_ui.py`：4 处 `模拟` → `演示`（来源标签判断 `source === "模拟"` → `"演示"`、`模拟数据已明确标注` → `演示数据已明确标注`）。
  - 重新运行 `_gen_ui.py` 生成，产物已与 `runtime/pawapps/*/ui/index.js` 逐字节一致（SHA256 全 MATCH）。
- `zhiyun-data-studio/ui/index.js`：7 处 `模拟` → `演示`（`模拟数据`/`生成模拟订单`/`已生成50条模拟订单`/功能介绍文案）。
- `zhiyun-app-discovery/ui/index.js`：能力状态显示标签 `测试中` → `验证中`（仅显示文案，`testing` 枚举与 `feature_progress.json` 不变）。
- `zhiyun-data-studio/tests/test_frontend_contract.py`：契约断言 `模拟数据` → `演示数据`，与产品规则对齐（否则发布门禁会失败）。

上述改动均同步到两处：`apps/qwenpaw-embedded/runtime/pawapps/<id>`（源）与 `apps/qwenpaw-embedded/workspace/plugins/<id>`（运行副本），`node --check` 全部通过。

### 21.2 验证事实（本轮实测）

- UI 标记载体扫描：`rg --no-ignore --glob '**/ui/index.js' '模拟|Mock|mock|测试' plugins apps/qwenpaw-embedded/runtime/pawapps apps/qwenpaw-embedded/workspace/plugins` → 0 命中。
- `node --check`：6 个 Studio + app-discovery（源码与运行副本）全部通过。
- 单测：app-discovery 14/14；data-studio 38/38；enterprise-seeder 23/23。
- 门禁：`node scripts/verify-release.mjs` 通过（纯 QwenPaw 架构、跨平台启动、版本锁、系统插件与全部锁定 PawApp 测试正常）；`node scripts/verify-project-plan.mjs` 通过（31 项；已完成 13，测试中 17，开发中 1，计划中 0）。

### 21.3 关键经验 / 注意事项（很重要）

- **唯一事实来源是 `_gen_ui.py`**（5 个模板 Studio），不是直接改 `runtime/pawapps` 或 `workspace/plugins`。改文案必须改生成器再重跑，否则下次生成会回退。
- 外部 5 个 Studio 的 `ui/index.js` 由 `_gen_ui.py` 产出后提交到第三方 GitHub 仓库并锁定 SHA；本地 `runtime/pawapps` 与 `workspace/plugins` 已打补丁且与生成器一致，但**干净克隆/重建会从锁定 SHA 恢复旧文案**。要彻底固化，需把更新后的 `ui/index.js` 推到第三方仓库新 SHA，并同步更新 `apps/qwenpaw-embedded/pawapps.lock.json` 的 commit。在无法联网推库前，本地补丁 + 交接说明是当前有效方案。
- `zhiyun-data-studio` 不走 `_gen_ui.py`，是独立外部 PawApp，改的是它自带的 `ui/index.js`；其 `test_frontend_contract.py` 契约要一并更新，否则 `verify-release.mjs` 会因断言旧文案而失败。
- app-discovery 是系统插件（`plugins/` 源码），非外部 PawApp；`测试中 → 验证中` 仅改显示映射，不影响 `search_engine.py` / `feature_progress.json` 的 `testing` 语义。

### 21.4 生效方式

- 运行副本与源已一致，浏览器 Ctrl+F5 硬刷新即可看到 `演示数据 / 验证中`。
- 若要连同 `verify-release.mjs` 维护动作（Logo、停用不兼容插件）一起生效，需重启 `node apps\qwenpaw-embedded\scripts\start.mjs`；重启后 `plugin install --force` 会从 `runtime/pawapps` 覆盖 `workspace/plugins`，本补丁仍保留。
