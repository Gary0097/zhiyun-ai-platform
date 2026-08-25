# 需求变更记录（2026-08-24）

> 状态：已纳入当前迭代。本文件是「智造云 AI-OS · 五大业务 Studio」在 2026-08-24 迭代的需求变更说明，后续所有 PRD、测试与交付参考本文件。
>
> 变更范围：服务 / 供应 / 销售 / 财务 / 人力 五个 Studio，共 18 个功能模块。Data Studio 与 Order Studio 作为基础数据与订单底座一并纳入部署与数据可写修复，不在 18 模块矩阵内。

---

## 一、变更动因

上一版功能以「接口返回 JSON / 数组」为主要呈现方式，用户无法直接理解与使用，且缺少可编辑的业务输入、示例数据导入和可审阅结果面板。本迭代将全部功能改为「真实 GUI + 真实输入控件 + 一键示例数据 + 结果审阅 + Agent 对话嵌入」，并补齐登录 / 权限 / 企业隔离，确保测试人员可直接在界面完成验证。

---

## 二、本次变更内容

### 1. 每个功能独立 GUI（深度重构）

- 所有功能不再返回裸 JSON，而是渲染为「左功能导航 + 上工具栏 + 输入区 + 分析结果区」的业务界面。
- 输入控件按功能类型分为三类：
  - `text`：多行客户文本输入，内置「载入示例文本」。
  - `table`：可编辑业务表格（增删行、字段需校验），内置「一键导入示例数据」。
  - `form`：结构化业务表单（含材料子表等嵌套输入），内置「一键填入示例数据」。
- 结果区统一呈现 KPI 卡片 + 明细表格/应答/趋势，并带「数据来源（真实/模拟）」标识。
- 每个结果生成「待审阅工件」，支持具名审阅人「接受 / 驳回」，接受后可「导出」，并可将结果「交给 Agent」进入上下文。
- 交互风格：简洁高效、克制配色、稳定栅格；不使用装饰性渐变/辉光/卡片套卡片；B 端工具型界面优先信息密度与可扫描性。

### 2. 每个功能内嵌 Agent 对话框

- 每个 Studio 右上角固定「问 Agent」入口，点击打开右侧智能体抽屉。
- 抽屉内展示：当前功能标签、四个功能快捷指令（生成应答 / 识别意图 / 创建并待审阅 / 生成知识库 等）、自由输入框。
- 用户输入自然语言后自动匹配功能并载入示例数据运行，结果以「工件卡片」回填到对话与界面，可直接「查看结果 / 交给 Agent」。
- Agent 对话在功能内完成闭环（识别意图 → 载入示例 → 运行模块 → 生成工件卡片），不再需要手写 JSON。

### 3. 登录与权限（RBAC）

- 每个企业实例具备独立的登录入口，身份基于企业内账号体系。
- 角色（管理员 / 部门经理 / 财务 / 销售 / 采购 / 员工）决定可用 Agent（即 Studio/功能）、可访问数据与知识库范围。
- 权限建议模块（People Studio · 权限建议）用于生成「角色 × 权限」矩阵，识别缺失 / 超配权限并输出高危 / 关注 / 正常分级。
- 本迭代先落地权限矩阵展示与建议；服务端鉴权与强制路由在本迭代之后接入（见下文落地顺序）。

### 4. 企业隔离（多实例 = 多租户）

- 部署模型：**一套运行实例对应一个企业**（单租户实例）。不同企业 → 不同独立实例，各自拥有独立的数据库、知识库、模型/Agent 配置与数据目录。
- 同一企业内的所有用户共享该企业实例下的 Agent、业务数据与知识库；用户仅按 RBAC 看到其被授权范围。
- 因此「多租户」在架构上表述为：企业维度隔离发生在「实例边界」而非「单实例内的租户表」。同一实例只服务一个企业，不跨企业共享任何数据。
- 数据存储：每个 Studio 后端默认使用独立 SQLite（`SERVICE_STUDIO_DB` 等），并存放于可写运行时数据目录 `runtime/.qwenpaw-runtime-data/<studio>/`，避免回退到只读用户目录。

---

## 三、18 模块矩阵（本迭代交付）

| # | Studio | 模块 | 输入类型 | 结果要点 |
| --- | --- | --- | --- | --- |
| 12 | 服务 | 客户咨询应答 | text | 置信度 / 意图 / 命中知识 / 应答内容 |
| 13 | 服务 | 智能意图识别 | text | 意图标签 / 实体 |
| 14 | 服务 | 售后工单管理 | form | 团队 / 工程师推荐 / 派单建议 |
| 15 | 服务 | 知识库构建 | table | 抽取 / 去重 / 打分 / 可审阅知识 |
| 16 | 供应 | 供应商评估 | table | A/B/C/D 分级 / 评分 / 风险点 |
| 17 | 供应 | 智能补货 | table | 补货建议 / 数量 / 级别 |
| 18 | 供应 | 风险监控 | table | 高 / 中 / 低风险记录 |
| 19 | 销售 | 销售 BI 分析 | table | 营收 / 销量 / 订单 / 客单价 / 趋势 |
| 20 | 销售 | 客户价值分层 | table | 分层 / 流失风险 / 建议 |
| 21 | 销售 | 销售业绩统计 | table | 目标达成率 / 排名 / 状态 |
| 22 | 财务 | 报销审核 | table | 通过 / 退回 / 驳回 / 问题 |
| 23 | 财务 | 财务看板 | table | 毛利 / 净利 / 流动比率 / 负债率 |
| 24 | 财务 | 成本预测 | form | 新单位成本 / 变动% / 年度影响 |
| 25 | 人力 | 权限建议 | table | 缺失 / 超配 / 高危 / 关注 |
| 26 | 人力 | 通讯录协作 | table | 技能定位 / 检索 |
| 27 | 人力 | 审批路径 | form | 金额 / 角色 / 节点 / 建议审批人 |
| 28 | 人力 | 员工关怀 | table | 临近生日 / 司龄 / 关怀建议 |
| 29 | 人力 | 人力分析 | table | 在编 / 缺编 / 离职率 / 部门分布 |

> 注：功能编号沿用「PawApp 功能矩阵」，列表以实际交付为准；编号 12-29 覆盖五个 Studio 的 18 个模块。

---

## 四、验收标准

1. 五个 Studio 均可通过 `http://127.0.0.1:8088/apps/zhiyun-<studio>` 打开真实 GUI，无裸 JSON。
2. 每个功能一键载入示例数据后可运行，结果区展示真实后端计算值（非空、非「暂无分析结果」）。
3. 右上角「问 Agent」可打开抽屉，抽屉内快捷指令可自动载入示例并运行模块，输出工件卡片。
4. 结果支持具名接受 / 驳回 / 导出 / 交给 Agent，状态正确联动（待审阅 ↔ 已接受 / 已驳回）。
5. 后端重启后（含 `npm start` 或直接 `python -m qwenpaw app`）模块仍可运行，不因数据目录只读而 503。
6. 各 Studio PRD 追加本「需求变更」说明；QA 报告、交接文档落库到 `docs/qa` 与 `docs/handoff`。

---

## 五、已修复问题（本迭代）

| 问题 | 严重级 | 修复 |
| --- | --- | --- |
| 功能只返回 JSON 数组、无 GUI | P0 | `_gen_ui.py` 重构为真实输入 + 结果面板，五 Studio 全覆盖 |
| 后端数据目录只读导致运行 503 | P0 | 各 Studio 读取 `*_STUDIO_DB` 环境变量；`start.mjs` 注入可写运行时数据目录 |
| 右上角「问 Agent」被宿主手机壳按钮遮挡无法打开 | P1 | Topbar 右侧留白 `padding-right`，让出宿主胶囊按钮 |
| Agent 快捷指令 / 自然语言运行失败（text 模块缺 sample + 闭包读取旧输入） | P1 | `sampleFor()` 兼容 `example`；`runModule` 支持 `overrideValue` 绕过旧闭包 |
| 应答结果「命中知识」恒为否，与命中标准问答矛盾 | P2 | 命中知识改由 `matched_faq` 判断 |

---

## 六、落地顺序（下一步，交给更强模型）

1. 服务端鉴权与强制路由（把 Role → Agent/数据/知识库 的能力边界真正落到 API 层）。
2. 企业实例配置化（部署时读取企业标识，分配给实例级数据目录与模型配置）。
3. 审计日志对接 `zhiyun-audit`，记录审阅人、动作、工件与 Agent 上下文导出。
4. 统一 Workspace 数据核心，把示例数据标记为「模拟」，真实数据走 Excel 导入。

---

# 第二迭代码段（2026-08-24 追加）

> 本段记录「登录与权限 + 系统应用直达路由 + 真实 GUI 全量复核」第二次迭代的最终事实。
> 对应的交付以「员工账号登录」（默认账号 `admin` / `Zhiyun@2026`）与「六个系统应用（数据核心 / 应用中心 / 审计中心 / Logo / 登录）共用完整路由 `/apps/<plugin-id>`」为基准。

## 1. 本次新增与修复

### 1.1 员工账号登录与权限（zhiyun-auth，已落地）
- 登录门覆盖所有页面：未登录一律进入登录页，校验通过才进入工作区。
- 登录页支持自定义背景图与品牌名（`workspace/branding/login-config.json`），默认账号密码可配。
- 认证：账号 + 密码，`token` 有效期 7 天，密码采用 salt + SHA-256 存储（`workspace/auth/users.json`）。
- 接口：
  - `GET /api/zhiyun-auth/config`（取登录页背景/品牌配置）
  - `POST /api/zhiyun-auth/login`（登录，返回 token）
  - `GET /api/zhiyun-auth/me`（当前员工与权限）
  - `POST /api/zhiyun-auth/agents/activate`（员工 → 可用 Agent 激活）
  - `GET /api/zhiyun-auth/users`、`POST /api/zhiyun-auth/users`（员工/账号管理）
  - `PATCH /api/zhiyun-auth/branding`（自定义登录页）
- 前端 API 根：`/zhiyun-auth`（宿主 `getApiUrl` 自动加 `/api` 前缀，**不要再写 `/api/...`**）。

### 1.2 默认账号（交付测试用）
- 账号：`admin`
- 密码：`Zhiyun@2026`
- token 有效期：7 天；密码采用 salted SHA-256。

### 1.3 系统应用直达路由（已修复，P0）
- 现象：三个系统应用（`zhiyun-data-core`、`zhiyun-app-discovery`、`zhiyun-audit`）在 `app_catalog.json` 中的 `route` 写成短名 `/apps/data-core`、`/apps/app-discovery`、`/apps/audit`，但插件 `plugin.json` 的 `entry_page` 与 `ui/index.js` 的 `registerRoutes` 均为完整路由 `/apps/zhiyun-<id>`。
- 后果：从「应用与项目中心」卡片点「打开」会按短名跳转，落回「应用」列表页，导致用户以为“没有正常 GUI / 进不去”。
- 修复：将三个系统应用的 `route` 改为完整路由：
  - `/apps/zhiyun-app-discovery`
  - `/apps/zhiyun-data-core`
  - `/apps/zhiyun-audit`
- 影响文件：`plugins/zhiyun-app-discovery/app_catalog.json`（源码）与 `apps/qwenpaw-embedded/workspace/plugins/zhiyun-app-discovery/app_catalog.json`（运行副本），两者已同步为一致。

### 1.4 真实 GUI 全量复核（登录后逐应用打开）
- 方法：单次登录 → 打开 `/apps/zhiyun-<id>` → 抓取 body 文本 + 截图。
- 结论：三个系统应用在短路由下 body 长度均为 1249、页面为「应用」列表（空壳感）；改为完整路由后，`zhiyun-data-core` body 提升到 2089，出现「统一数据中心 / 数据预览 / 数据表 2 / 当前记录 300 / 真实 20 / 模拟 280 / 订单明细表」，真实 GUI 确认渲染。
- 端到端验收：登录 → 「应用与项目中心」→ 点「统一数据中心」的「打开」按钮（href=`/apps/zhiyun-data-core`）→ 落到真实面板，`VERDICT data_core_panel_rendered=True`。

## 2. 真实可运行的访问地址

- 服务根地址：`http://127.0.0.1:8088`
- 建议访问方式（打开真实 GUI，而不是看 JSON/列表）：
  - 业务 Studio：`http://127.0.0.1:8088/apps/zhiyun-service-studio`
  - 其他 Studio 同理：`/apps/zhiyun-data-studio`、`/apps/zhiyun-order-studio`、`/apps/zhiyun-supply-studio`、`/apps/zhiyun-sales-studio`、`/apps/zhiyun-finance-studio`、`/apps/zhiyun-people-studio`、`/apps/zhiyun-integration-hub`
  - 系统应用：`/apps/zhiyun-data-core`、`/apps/zhiyun-app-discovery`、`/apps/zhiyun-audit`
- 首次打开：若浏览器保留旧缓存，请 **Ctrl+F5 硬刷新**。

## 3. 已知问题与后续

- 员工登录的「角色 → Agent/数据/知识库」边界目前为前端展示与矩阵建议，服务端强制鉴权与路由在后续迭代接入。
- 企业隔离 = 单租户实例：一套运行实例对应一个企业，不同企业单独启动实例，数据/知识库/Agent 各自独立。
- 审计链路（zhiyun-audit）与「审阅人、动作、工件、Agent 上下文导出」的对接按后续迭代完善。


---

# 第三迭代码段（2026-08-24 追加）：双态运行体系（Demo / Production）规格

> 本段性质：**规格先行（spec-first）**。把用户方向从「造一批演示数据」升级为「长期可持续运行的 Demo / Production 双态验证体系」，并作为后续实现阶段的权威需求来源。
> 权威需求：`docs/product/AI-OS-SIMULATION-DUAL-STATE-VISION.md`；Epic 计划：`docs/product/DEMO-PRODUCTION-EPICS.md`。

## 1. 一句话目标

> 从一个全新数据库开始，执行一次初始化命令即可自动生成 2025-12-01 至当前日期持续运行的企业 AI 环境；任意日期可查看用户、智能体、聊天、Token、应用、权限、文件与执行统计，并能在演示环境与真实业务环境之间一键切换，且所有统计可追溯到底层业务记录。

## 2. 关键决策（本段定稿）

1. **命名**：产品前台不叫「模拟数据」，叫 **数据环境**（演示环境 / 生产环境，或 Demo / Live）；底层统一字段 **`data_mode`**，取值 `demo` / `production`。
2. **统一数据流**：所有查询走统一 `DataContext`：
   `User → App → DataContext → Demo/Production Dataset → Database`；页面不自选数据集。
3. **双态隔离**：Demo 与 Production 逻辑/物理隔离，记录带 `tenant_id / environment_id / data_source`；正式模式严禁读演示记录；导入真实数据不污染 Demo 历史。
4. **台账分开**：双态 6 Epic 放入独立台账 `DEMO-PRODUCTION-EPICS.md`，不塞进现有 31 项 `feature_progress.json`；避免破坏其「唯一 ID + status/progress 配比 + 证据 note」校验（`scripts/verify-project-plan.mjs`）。
5. **统计闭环**：所有统计必须追溯到记录（调用量 ↔ 会话、Token ↔ 执行、文件 ↔ 下载、权限 ↔ 可访问 Agent）。
6. **展示无痕迹**：禁止明显生成痕迹（全同注册日/每日登录/100% 成功率/每日递增 Token/固定 3 轮聊天/整数金额/固定执行时间/周末工作日同流量/每月相同），允许失败/波动/异常/休眠/低频/峰值。

## 3. 6 Epic（详见台账）

| Epic | 名称 | 范围 |
| --- | --- | --- |
| 1 | Enterprise Seeder | 一键生成企业、部门、用户、角色、权限、Agent、Skill、应用、数据源、会话、任务、Token、日志 |
| 2 | Agent Factory | 按岗位模板生成完整 Agent 配置（Prompt/模型/Skill/Tool/知识库/权限/Token/频率/成功率/响应时间），并真正调用本地模型 |
| 3 | Simulation Runtime | 业务事件 → Agent → Skill → Tool → 结果 → 日志 → Token → 用户行为 → 统计 |
| 4 | Time Machine | 2025-12-01 至当前的历史数据，任意时间段同步切换所有 Dashboard |
| 5 | Data Platform | Excel/CSV 统一 Import/Export SDK；字段映射/预览/校验/错误行/去重/增量/覆盖；Demo/Production 双态 |
| 6 | Data Integrity | 跨模块一致性检查、异常检查、可安全修复项自动修复、生成 `Data Integrity Report` |

## 4. 与现有实现的复用与改造点

| 对象 | 现状 | 双态体系下的处理 |
| --- | --- | --- |
| `zhiyun-auth` | 已有登录门、默认账号 `admin/Zhiyun@2026`、前端 RBAC 展示 | 作为企业 IAM 底座；服务端强制鉴权与路由待接入 |
| `zhiyun-data-core` | 已有 `data_core_meta / batches / records`、`source_type=real\|simulated`、`preview_import / import_rows / list_records / list_batches / rollback_batch`、`generate_orders / generate_production` | 作为 Simulation/Data Platform/Time Machine 的底座；**改造点**：UI 的「模拟订单/生产数据」按钮与「模拟」徽标按命名规范改为「数据环境 Demo/Live 措辞」，本轮只记录不改码 |
| `zhiyun-audit` | 已有审计链完整性、Tool 表、防篡改哈希链 | 作为 Data Integrity 的校验与审计底座 |
| `feature_progress.json` | 当前 1-31 项能力台账 | 保持不动；Epic 产出的可交付能力若需入账，先评估与校验器兼容性 |

## 5. 本段交付（文档）

- 新增：`docs/product/AI-OS-SIMULATION-DUAL-STATE-VISION.md`
- 新增：`docs/product/DEMO-PRODUCTION-EPICS.md`
- 修改：`docs/product/PROJECT-PLAN.md`（Phase 4）
- 修改：`docs/handoff/HANDOFF_GPT_2026-08-24.md`（第 13 节）
- 修改：`docs/architecture/QWENPAW-ONLY-ARCHITECTURE.md`（双态分层组件）

> 本段不包含实现代码。实现按「Epic 1 → 2 → 3 → 4 → 5 → 6」推进，每 Epic 达「可运行 + 证据留存 + 口径闭环」才在台账标记进展。

---

# 第四迭代变更（2026-08-25）

> 本段为 2026-08-24 双态规格之后的落地实现记录。第 1、2 阶段（企业环境初始化器 + 服务端鉴权）已实现并通过回归；后续按 Epic 2 → 6 推进。

## 1. 企业环境初始化器

- 插件：`plugins/zhiyun-enterprise-seeder`（后端 `enterprise_plugin.py`，前端 `ui/index.js`）。
- 一次初始化：`POST /api/zhiyun-enterprise-seeder/seed` 生成企业/部门/用户/角色/权限/Agent/Skill/应用/数据源/会话/任务/Token/日志。
- 多环境：记录带 `env_id + data_mode`，`/records` 强制按 `env_id + data_mode` 过滤。
- 账号同步：生成后同步到 `auth/users.json`，默认密码 `Zhiyun@2026`。
- 交互：前端为真实 GUI（参数表单 + 概览 + 明细表 + 实体切换 + Agent 抽屉），非裸 JSON。

## 2. 服务端鉴权（RBAC 落地）

- `zhiyun-enterprise-seeder`：`/config`、`/summary`、`/records/{entity}` 需 Bearer token；`/seed` 仅 admin。
- `/records` 非管理员按 `data_scope` 过滤（部门/Agent/用户）。
- `zhiyun-auth`：`login / me / users / branding / agents/activate` 均校验 token；`/users`、`/branding` 仅 admin。
- 前端注入 Authorization header，未登录等待登录事件再加载。

## 3. 验收与证据

- 健康检查：13/13 pass；`/api/version=2.1.0`。
- 接口：匿名 401；admin 全量 9 agents / 50 org_users；member（sales_02）agents 仅 1、org_users 仅销售部、sessions 全部绑定 agent；非管理员 `/seed` 403；admin `/seed` 200。
- GUI：Playwright 22/22 pass，截图在 `docs/qa/screenshots`。
- 台账：31 项 completed 13 / testing 17 / in_progress 1；**未全部完成**。

## 4. 待办（下一迭代）

- 各 Studio 业务接口接入统一 RBAC 强制路由（Epic 前置）。
- 前端「模拟/Mock」标识改为「数据环境 Demo/Live」。
- 不同企业独立实例的部署脚本配置化。
- Epic 5 真实 Excel 校准接入。

---

# 第五迭代修复（2026-08-25 晚）

> 本段为 2026-08-25 对「企业环境初始化器」的回归修复与统计口径补齐。服务已重启至 2.1.0，`/integration` 与 GUI 均恢复并通过。

## 1. 本次修复内容

1. **文件时间分布修复（Epic 4 Time Machine）**
   - 问题：`files.created_at` 生成时用 `_now()`，所有文件落在种子当天，导致 `/summary` 的时间范围过滤对文件失效、文件维度不随时间切换。
   - 修复：改为按历史随机日生成（与会话/任务/下载一致）；重导后 `files.created_at` 覆盖 2025-12-01~2026-08-25 共 **230 天**。
   - 验证：`summary` 传 `start_date/end_date` 后，`files` 均按范围返回部分计数，不再与全量相等。

2. **`/summary` 统计口径补齐**
   - 新增 `files / downloads / logins` 三个维度的计数，并支持 `start_date / end_date` 范围过滤（与会话/任务/Token 一致）。

3. **`/integrity` 性能与完整性修复**
   - 新增 5 条索引：`idx_tasks_task_id`、`idx_files_file_id`、`idx_sessions_user`、`idx_tasks_user_agent`、`idx_tasks_env_task`。
   - 修复 `orphan_files` 子查询误用索引导致的超时（原 >120s），现 `/integrity` 约 **1.1s**，`total=13 passed=13 failed=0 healthy=true`。
   - `_integrity_report` 补齐：污染行、`overall_failed`、`perm_violations`、`file_count/orphan_files/download_rows/orphan_downloads/file_download_sum/login_count`。

4. **前端 UI 崩溃回归修复**
   - 问题：`ui/index.js` 的 `statItems` 数组在 `["Token","token_total"]` 后缺少逗号，导致 `["文件","files"]` 被当作下标运算，数组出现 `undefined`，整页崩溃。
   - 修复：补齐逗号并同步运行态 bundle；`文件 / 下载 / 登录` 统计卡与实体切换 chip（共 14 个）恢复正常。

## 2. 新增前端实体与统计项

- `ENTITIES` 增加 `files / file_downloads / login_activity`。
- `statItems` 增加 `文件 / 下载 / 登录`。
- 环境概览现包含：部门 / 员工 / 智能体 / 应用 / 数据源 / 会话 / 任务 / Token / 文件 / 下载 / 登录，并可按「全部 / 今天 / 昨天 / 近7天 / 近30天 / 本月 / 自定义」切换时间范围。

## 3. 验证证据

- 健康检查 13/13；`/api/version=2.1.0`。
- 新环境 `env_75790ea7ba`：sessions=19201、tasks=38474、token=43505857、files=21842、downloads=40609、logins=5802。
- 范围 `2026-08-01..2026-08-20`：sessions=1716、tasks=3439、files=1950、downloads=3618、logins=539。
- 详细用例与结果见 `docs/qa/qa-report-enterprise-seeder-2026-08-25.md` 第十节。

## 4. 待办（下一迭代）

- 各 Studio 业务接口统一接入 RBAC 强制路由。
- 前端「模拟/Mock」标识改为「数据环境 Demo/Live」。
- 不同企业独立实例的部署脚本配置化。
- Epic 5 真实 Excel 校准接入。

---

# 第六迭代：Data Core Demo/Production 双态隔离（2026-08-25）

> 本段为 2026-08-25 对 `zhiyun-data-core` 的演示/正式双态改造与 v2→v3 迁移。服务已重启至 `http://127.0.0.1:8088`，Data Core `0.8.0` / schema `v3`，健康 `13/13`。

## 1. 需求变更背景

此前 Data Core 只有「真实/模拟」一类含义，环境维度缺失，无法区分「演示环境」与「生产环境」，存在正式数据与演示数据混用风险。本轮引入 `data_mode`（`demo`/`production`）作为独立环境维度，纳入数据批次与记录，并让查询、导入、模拟生成、前端切换全部按环境隔离。

## 2. 变更内容

1. **schema 升级到 v3**：`data_batches`、`data_records` 新增 `data_mode TEXT NOT NULL DEFAULT 'demo'`；旧库启动时 `ALTER TABLE ADD COLUMN` 自动升级，既有记录默认归入 `demo`；新增 `idx_records_mode` / `idx_batches_mode`。
2. **接口双态**：`/entities`、`/records/{entity}`、`/orders`、`/batches` 支持 `data_mode` 查询；`/imports/{entity}/commit` 默认写入 `production`，`/simulate/orders`、`/simulate/production` 默认写入 `demo`。
3. **Agent 工具**：`query_enterprise_orders`、`generate_simulated_orders` 增加 `data_mode`（默认 `demo`），文案「模拟」改「演示」。
4. **前端**：新增「数据环境 演示 Demo / 正式 Live」切换、「来源 已导入/系统生成」筛选、「数据环境」列、「演示数据/正式数据」统计卡；导入提示改为「已导入 N 条正式数据」。
5. **版本**：`plugin.json` `0.7.0 → 0.8.0`，描述改「演示/正式数据环境服务」。

## 3. 验证证据

- v2 一致快照升 v3：`schema_version 2→3`，迁移日志 `[2,3]`，旧 300 条订单归 `demo`，demo/production 写入隔离，`list_entities` 计数正确（`RESULT | ALL_PASS`）。
- 接口实测：`/health` version=`0.8.0` schema=3；`/entities`（无过滤）orders demo=300 prod=0，production 实体 demo=0 prod=0；`/entities?data_mode=demo` 仅 orders；`/records/orders?data_mode=demo&limit=3` 返回 demo 记录；`/apps/zhiyun-data-core` 返回 `text/html`。
- 详见 `docs/qa/qa-report-enterprise-seeder-2026-08-25.md` 第十一节。

## 4. 待办（下一迭代）

- 用真实 Excel 导入后复验正式/演示两张数据集互不污染（当前 `production` 为空）。
- 各 Studio 业务接口统一接入 RBAC 强制路由。
- 不同企业独立实例的部署脚本配置化。


# 第七迭代：Epic 6 Data Integrity 收尾（2026-08-25）

> 服务已重启至 `http://127.0.0.1:8088`，QwenPaw 2.1.0，健康 13/13。

## 1. 需求变更背景

前序 `/integrity` 仅提供 14 项一致性只读检查，缺少「发现后如何处置」。为满足「数据一致性」闭环，需补充安全自动修复策略、每日一致性报告与历史轨迹，供管理员处置异常并按日留痕。

## 2. 变更内容

1. **安全自动修复（Epic 6）**：新增 `POST /integrity/repair`（仅管理员），只处理语义明确、可逆且不伪造数据的项：
   - 删除孤儿会话（用户/智能体不存在）
   - 删除孤儿任务（会话不存在）
   - 删除孤儿文件（任务不存在）
   - 删除孤儿下载记录（文件不存在）
   - 依据下载事件回写 `files.download_count`
   - 回填员工智能体绑定（同环境首个可用智能体）
   - 人工决策项（登录回查 / 权限 / 成功率方差 / 日波动 / 业务事件链）不改动；全部行为写入 `integrity_repair_log` 审计。
2. **每日一致性快照**：新增 `GET /integrity/daily`，懒生成并按 `report_day` 幂等持久化到 `integrity_reports`（同日重复为更新）；`_ensure_schema` 启动钩子自动生成当日报告。
3. **历史轨迹**：新增 `GET /integrity/history`，按 `report_day DESC` 返回快照摘要。
4. **Agent 工具**：`run_integrity_repair`、`query_daily_integrity_report`、`query_integrity_history`。
5. **前端**：数据一致性卡片新增「自动修复 / 运行检查 / 今日快照」三按钮与「今日快照」摘要；自动修复结果写入 Agent 抽屉。

## 3. 验证证据

- 单测 `test_integrity.py` 3/3（修复孤儿/重算、空环境、每日幂等+历史）；旧基线 20/20，合计 23/23。
- 实机接口：`/integrity/daily` demo 14/14 `persist=inserted`，同日重复 `persist=updated`；`/integrity/repair` `ok=true fixed_checks=[]`；`/integrity/history` `count=1`；无 token 401。
- `node scripts/verify-release.mjs`、`node scripts/verify-project-plan.mjs` 均通过。
- 详见 `docs/qa/qa-report-integrity-repair-2026-08-25.md`。

## 4. 待办（下一迭代）

- 真实模型驱动执行替换规则引擎（当前本地 `kilo/kilo-auto/free` 不可达，不影响规则驱动）。
- 各 Studio 业务接口统一接入 RBAC 强制路由。
- 不同企业独立实例的部署脚本配置化。
