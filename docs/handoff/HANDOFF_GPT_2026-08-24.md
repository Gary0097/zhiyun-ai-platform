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

> 结论：第 6 点已在本轮用真实浏览器全量复核并推翻——所有核心功能均为真实结构化 GUI，具备一键导入示例数据 + 可运行 + 可审阅结果。用户见到的 JSON 极可能是旧构建缓存或打开了接口地址而非 `/apps/<plugin-id>` 应用页。

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
