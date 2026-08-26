# 企业环境初始化器（zhiyun-enterprise-seeder）拟人交互测试报告

> 日期：2026-08-25
> 服务：`http://127.0.0.1:8088`（QwenPaw 2.1.0）
> 应用：`/apps/zhiyun-enterprise-seeder`
> 浏览器：Google Chrome（headless，Playwright）
> 用例数：22；通过：22；失败：0

---

## 一、测试环境与账号

- 服务版本：2.1.0（`/api/version`）
- 登录账号：`admin / ZhizaoYun@2026`（默认系统管理员）
- 数据环境：Demo 演示环境（前端统一措辞，不使用「模拟 / Mock / 测试」）

## 二、测试用例与结果

| # | 用例 | 步骤 | 预期 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | 登录 | 打开应用，登录墙填写账号密码并登录 | 登录成功，右上角出现「系统管理员」员工浮窗 | PASS |
| 2 | 页面渲染标题 | 等待应用主界面 | 出现「企业环境初始化器」标题 | PASS |
| 3 | 生成参数区 | 检查左侧表单区 | 存在「生成参数」 | PASS |
| 4 | 环境概览区 | 检查右侧概览卡 | 存在「环境概览」 | PASS |
| 5 | 企业数据明细区 | 检查明细卡片 | 存在「企业数据明细」 | PASS |
| 6 | 生成并运行按钮 | 检查主操作按钮 | 存在「生成并运行」 | PASS |
| 7 | 智能体助手入口 | 检查右上角按钮 | 存在「智能体助手」 | PASS |
| 8 | 统计卡-部门 | 检查统计卡 | 「部门」卡片存在 | PASS |
| 9 | 统计卡-员工 | 检查统计卡 | 「员工」卡片存在 | PASS |
| 10 | 统计卡-智能体 | 检查统计卡 | 「智能体」卡片存在 | PASS |
| 11 | 统计卡-应用 | 检查统计卡 | 「应用」卡片存在 | PASS |
| 12 | 统计卡-会话 | 检查统计卡 | 「会话」卡片存在 | PASS |
| 13 | 统计卡-任务 | 检查统计卡 | 「任务」卡片存在 | PASS |
| 14 | 统计卡-Token | 检查统计卡 | 「Token」卡片存在 | PASS |
| 15 | 实体切换入口 | 检查明细区实体 chip | 存在 11 个实体切换入口 | PASS |
| 16 | 表单默认企业名 | 读取「企业名称」输入框 | 默认值为「制造云科技」 | PASS |
| 17 | 点击生成按钮 | 点击「生成并运行」 | 按钮可点击并进入生成 | PASS |
| 18 | 生成成功反馈 | 等待 Toast | 出现「企业环境已生成并运行」 | PASS |
| 19 | 数据表有内容 | 生成后读取员工明细表 | 表格出现数据行 | PASS |
| 20 | 概览统计更新 | 读取「环境概览」 | 显示「制造云科技 · DEMO」及刷新增量 | PASS |
| 21 | 切换实体 | 选择「智能体」chip | 表格切换为智能体数据 | PASS |
| 22 | Agent 抽屉 | 点击「智能体助手」 | 抽屉打开，快捷指令「初始化企业 / 查询状态」 | PASS |

## 三、后端能力清单

- `GET /zhiyun-enterprise-seeder/config`：返回默认参数 / 模板 / 部门 / Agent / 应用。
- `POST /zhiyun-enterprise-seeder/seed`：一键生成企业环境（企业 / 部门 / 用户 / 角色 / 权限 / Agent / Skill / 应用 / 数据源 / 会话 / 任务 / Token / 日志），并向登录系统同步员工账号。
- `GET /zhiyun-enterprise-seeder/summary`：按环境汇总各实体计数。
- `GET /zhiyun-enterprise-seeder/records/{entity}`：按 `env_id` / `data_mode` 分页返回实体记录；未传时默认取最新环境。
- `GET /zhiyun-enterprise-seeder/health`：插件健康信息。

## 四、验证到的登录与权限绑定

- `auth/users.json` 已写入 84 个账号。
- 员工账号含 `agent_id / data_scope / kb_scope / role / active` 字段。
- 示例：销售 1-11 绑定 `customer_followup` 智能体；部门经理 / 管理员为 `enterprise` 数据范围，普通员工为 `department` 范围。
- 登录后前端按员工视角展示智能体与数据范围（同一企业共享同一运行实例，对应「同企业共用，不同企业单独启动系统」）。

## 五、发现并修复的 BUG（分级）

### P0（阻断）
- 无。

### P1（高，残留并交接）
- **接口未强制鉴权**：seeder 的 `/config`、`/seed`、`/summary`、`/records` 未校验 Bearer token。虽然前端已由登录墙拦截，但后端 API 仍可匿名访问，且不区分当前登录用户。
- **修复建议**：复用 `zhiyun-auth` 的 token 秘钥与 `_verify_token`，在 seeder 路由加 Bearer 校验；将 `/seed` 限制为 `admin`；`/records`、`/summary` 按当前用户的 `data_scope / kb_scope` 过滤。

### P2（中，已修复）
- **记录未按环境隔离**：`/records/{entity}` 原先为 `SELECT * ... ORDER BY id DESC`，多企业 / 多环境共用一个实例时会串数据。
- **修复内容**：`records` 端点新增 `env_id` / `data_mode` 过滤；未传时默认取最新环境；前端 `fetchRows` 已按当前环境拉取。

## 六、实际生成数据量

默认参数：企业规模 50 人 / 部门数 6 / 智能体 9 / 活跃度中频 / 2025-12-01 ~ 2026-08-25。

| 实体 | 数量 |
| --- | --- |
| 部门 | 6 |
| 员工 | 50 |
| 智能体 | 9 |
| 应用 | 8 |
| 数据源 | 8 |
| 会话 | 19,331 |
| 任务 | 38,781 |
| Token | 43,861,376 |

## 七、运行与复测

启动服务：

```powershell
cd C:\AI\zhiyun-ai-os-workspace\zhiyun-ai-platform
node apps\qwenpaw-embedded\scripts\start.mjs
```

运行测试：

```powershell
$py = 'apps\qwenpaw-embedded\runtime\qwenpaw\venv\Scripts\python.exe'
& $py scripts\qa\qa-enterprise-seeder.py
```

## 八、结论

**通过。** 企业环境初始化器 GUI 端到端可用：登录 → 渲染 → 生成 → 统计刷新 → 实体切换 → Agent 抽屉，全链路 22/22 通过。数据环境隔离（`env_id`）已落地；登录与权限绑定已落地；服务端 Bearer 鉴权（config/summary/records/seed）已于 2026-08-25 接入并通过实测（见第九节）。

---

## 九、2026-08-25 服务端鉴权补测（P1 已闭环）

> 本轮把「接口未强制鉴权」P1 落地修复并实测，同时验证「不同用户看到不同 Agent / 数据 / 知识库范围」的用户级隔离。

### 9.1 接口鉴权实测

| 场景 | 期望 | 实际 | 结果 |
| --- | --- | --- | --- |
| 匿名 `GET /config` | 401 | 401 | PASS |
| 匿名 `GET /summary` | 401 | 401 | PASS |
| 匿名 `GET /records/org_users` | 401 | 401 | PASS |
| admin 登录 `GET /config` | 200 | 200 | PASS |
| admin 登录 `GET /summary` | 200 | 200 | PASS |
| admin 登录 `GET /records/agents` | 全量 9 行 | 9 行 | PASS |
| admin 登录 `GET /records/org_users` | 全量 50 行 | 50 行 | PASS |
| 非管理员 `POST /seed` | 403 需要管理员权限 | 403 | PASS |
| admin `POST /seed` | 200 一次生成 | 200 | PASS |

### 9.2 用户级数据隔离实测（sales_02，member，agent=customer_followup，data_scope=department）

| 实体 | 结果 |
| --- | --- |
| `/records/agents` | 仅 1 行，agent_id=customer_followup |
| `/records/org_users` | 仅 13 行，全部属销售部 |
| `/records/sessions` | 全部 agent_id=customer_followup |

结论：非管理员只能看到其绑定的智能体 / 所属部门的账号 / 该智能体的会话与执行记录；管理员全量可见。

### 9.3 修复内容

- `enterprise_plugin.py`：`/config`、`/summary`、`/records/{entity}` 增加 `Authorization: Bearer <token>` 校验；`/seed` 仅 admin。
- `_records`：非管理员按 `data_scope`（enterprise/department/agent）追加过滤；复用 `_scope_clause` 与 `_user_context`。
- `ui/index.js`：请求自动携带 token，未登录等待 `zhiyun:auth` 事件后再加载数据。
- 账号同步：`/seed` 生成后同步到 `auth/users.json`（默认密码 `ZhizaoYun@2026`），用户提供 `agent_id / data_scope / kb_scope`。

### 9.4 残留（下一迭代）

- 各 Studio 业务接口尚未统一接入 RBAC（仅 seeder 与 auth 自身已强制鉴权）。
- 前端「模拟/Mock」标识待改为「数据环境 Demo/Live」。
- 不同企业独立实例的部署脚本配置化。

---

## 十、2026-08-25 修复与回归补测（时间分布 / 范围统计 / 一致性提速 / UI 回归）

> 本轮在服务端鉴权落地之后继续修复「数据可追溯」与「统计口径」问题，并恢复前端展示。服务地址不变：`http://127.0.0.1:8088`（QwenPaw 2.1.0），健康检查 13/13，`/integrity` 全部通过。

### 10.1 发现并修复的 BUG（分级）

| 级别 | 问题 | 根因 | 修复 |
| --- | --- | --- | --- |
| P1 | `/summary` 的 `files` 不随时间范围过滤，所有文件都集中在种子当天 | `files.created_at` 生成时写了 `_now()`（种子时刻），而 `sessions/tasks/file_downloads` 用随机历史日 | `files.created_at` 改为按历史随机日生成（与会话/任务一致），重新生成后文件时间跨 230 天分布 |
| P1 | 前端「企业环境初始化器」整页崩溃，显示「页面出现异常」 | `ui/index.js` 的 `statItems` 数组在 `["Token","token_total"]` 之后**缺少逗号**，导致后一项 `["文件","files"]` 被当作下标运算，数组出现 `undefined`，`item[0]` 抛错触发 React 错误边界 | 补上缺失逗号，重新同步运行态 bundle，硬刷新后恢复 |
| P2 | `/integrity` 慢（>120s） | `orphan_files` 相关子查询误用 `idx_tasks_user_agent` 索引 | 新增 `idx_tasks_env_task`（COVERING INDEX），`/integrity` 降至约 1.1s |

### 10.2 修复后接口实测

| 场景 | 期望 | 实际 | 结果 |
| --- | --- | --- | --- |
| `summary` 全量（`env_75790ea7ba`） | 返回全量计数 | sessions=19201 tasks=38474 token=43505857 files=21842 downloads=40609 logins=5802 | PASS |
| `summary` 范围 `2026-08-01..2026-08-20` | 各实体按范围返回部分计数 | sessions=1716 tasks=3439 files=1950 downloads=3618 logins=539 | PASS（证明文件时间已按历史铺开） |
| `records/files`（limit=2） | 返回真实文件行 | 200，含 agent/user/name/created_at | PASS |
| `records/file_downloads`（limit=2） | 返回真实下载行 | 200，含 file_id/downloaded_at/ip/device | PASS |
| `records/login_activity`（limit=2） | 返回真实登录行 | 200，含 user_id/login_at/device/success | PASS |
| `integrity?env_id=env_75790ea7ba&data_mode=demo` | 13/13 通过，健康 | total=13 passed=13 failed=0 healthy=true，耗时约 1.1s | PASS |
| 新增索引 | 不破坏既有结构 | `idx_tasks_task_id / idx_files_file_id / idx_sessions_user / idx_tasks_user_agent / idx_tasks_env_task` 全部生效 | PASS |

### 10.3 文件时间分布实测（Epic 4 Time Machine）

- `files.created_at`：MIN=`2025-12-01 09:00:00`，MAX=`2026-08-25 23:10:00`，COUNT(DISTINCT day)=**230**，总数=21842。
- 逐日样例：`2025-12-01` 82 条，`2025-12-02` 66 条，`2025-12-03` 74 条……说明文件已按历史日期铺开，不再全部落在种子当天。
- 结论：Time Machine 的「任选时间段同步切换」在 `files` 维度已成立（`downloads/logins` 早前即按 `downloaded_at/day` 分布）。

### 10.4 UI 回归修复结果

- 修复前：登录成功但主界面整页崩溃（React 错误边界）。
- 修复后：`文件 / 下载 / 登录` 统计卡正常渲染；实体切换 chip 共 **14** 个（原 11 + 文件/下载/登录 3）。
- 环境概览正确显示：部门 6、员工 50、智能体 9、应用 8、数据源 8、会话 19201、任务 38474、Token 43505857、文件 21842、下载 40609、登录 5802；数据一致性 13/13。
- 截图：`docs/qa/screenshots/seeder-spread-stats.png`。

### 10.5 新环境（重导）

- `env_id=env_75790ea7ba`，`data_mode=demo`，`start_date=2025-12-01`，`end_date=2026-08-25`，`days=268`。
- 计数：org_users=50、agents=9、apps=8、data_sources=8、sessions=19201、tasks=38474、files=21842、downloads=40609、logins=5802。
- 说明：每次 `/seed` 生成全新 `env_id`，旧 `env_dbd7f367a7` 保留，便于对照；前端默认展示最新环境。

### 10.6 Time Machine UI 范围切换实测

- 在「环境概览」点击 **近7天**，日期显示 `2026-08-19 ~ 2026-08-25`。
- 统计同步切换：会话 19201→621、任务 38474→1224、Token 43505857→1392193、文件 21842→644、下载 40609→1224、登录 5802→192。
- 结论：范围切换不是只改日期文案，而是真实重新请求 `/summary` 并联动所有统计实体。
- 截图：`docs/qa/screenshots/seeder-time-machine-range.png`。

## 十一、Data Core Demo/Production 双态改造与 v3 迁移实测（2026-08-25）

> 本轮把 `zhiyun-data-core` 从「真实/模拟」单一维度升级为「演示 Demo / 正式 Live」双态隔离，并把 schema 从 v2 升到 v3。服务重启后接口与前端均已实测通过。

### 11.1 改动范围

| 模块 | 改动 |
| --- | --- |
| `data_core.py` | `SCHEMA_VERSION=3`；`data_batches/data_records` 新增 `data_mode` 列；v3 迁移块（对旧库 `ALTER TABLE ADD COLUMN` + 建 `idx_records_mode`/`idx_batches_mode`）；`list_entities` 返回 `demo_count/production_count`；`list_records/search_records/list_batches` 支持 `data_mode` 过滤；`import_rows` 默认 `production`，`generate_orders/generate_production` 默认 `demo` |
| `data_core_plugin.py` | `/entities`、`/records/{entity}`、`/orders`、`/batches` 支持 `data_mode` 查询参数；`/imports/{entity}/commit`、`/simulate/orders`、`/simulate/production` 支持 `data_mode` 写入参数；健康版本 `0.8.0` |
| `agent_tools.py` | `query_enterprise_orders`/`generate_simulated_orders` 增加 `data_mode` 参数，默认 `demo`；「模拟」文案改「演示」 |
| `ui/index.js` | `dataMode` 状态（空=全部/demo/production）；「数据环境 演示 Demo / 正式 Live」下拉；来源筛选「已导入 / 系统生成」；「数据环境」列；「演示数据 / 正式数据」统计卡；导入提示「已导入 N 条正式数据」 |
| `plugin.json` | `version=0.8.0`；描述改为「演示/正式数据环境服务」 |

### 11.2 v3 迁移离线验证

- 用 SQLite `backup` API 对真实 v2 库做一致快照（避免 WAL 主文件拷贝不一致），再以新代码打开触发迁移。
- 结果：`schema_version 2→3`，迁移日志 `[2,3]`；旧 300 条订单自动归入 `demo`，`production=0`；`data_mode=demo` 查询返回旧记录；新增 `demo`/`production` 订单后计数分别 +3/+2，环境互不污染。
- 脚本：`scripts/qa/validate_data_core_v3_migration.py`，输出 `RESULT | ALL_PASS`。

### 11.3 重启后接口实测

| 场景 | 期望 | 实际 | 结果 |
| --- | --- | --- | --- |
| `GET /api/zhiyun-data-core/health` | version=`0.8.0`、schema=3 | `0.8.0`/`3`/`integrity=ok`/`status=available` | PASS |
| `GET /entities`（无过滤） | 返回全部实体与计数 | orders 客户订单 demo=300 prod=0；production 生产日报 demo=0 prod=0 | PASS |
| `GET /entities?data_mode=demo` | 只含演示数据实体 | 仅 orders（demo=300） | PASS |
| `GET /entities?data_mode=production` | 正式环境为空（本轮无正式导入） | 0 个实体 | PASS（隔离成立） |
| `GET /records/orders?data_mode=demo&limit=3` | 仅返回 demo 记录 | 3 条，`data_mode=demo` | PASS |
| `GET /batches?data_mode=demo&limit=5` | 仅 demo 批次 | 12 个批次 | PASS |
| `GET /apps/zhiyun-data-core` | 返回 GUI HTML 而非 JSON | 200 `text/html` | PASS |

### 11.4 BUG 分级

本轮无新增 P1/P2 代码 BUG；运行库从 v2 升 v3 的迁移在真实快照上验证一次性通过（此前沿用旧库启动可能因缺 `data_mode` 列导致查询失败，属 P0 风险，已在重启前用快照验证消除）。

### 11.5 待回归

- `data_mode=production` 目前为空（本轮未执行正式导入）；后续用真实 Excel 导入后需复验正式/演示两张数据集互不污染。

## 十二、Agent Factory 智能体自动配置（Epic 2）实测与 BUG 修复（2026-08-25 服务重启后）

> 本轮为 `zhiyun-enterprise-seeder` 新增「智能体工厂」Agent Factory 能力：按岗位模板自动生成完整 Agent 配置（模型/技能/工具/知识库/数据权限/应用权限/指标），支持编目读取、模板读取、绑定回填、配置校验。后端新增 5 条路由，前端新增 `AgentFactoryPanel` GUI。

### 12.1 接口实测（Bearer 鉴权）

| 接口 | 期望 | 实际 | 结果 |
| --- | --- | --- | --- |
| `GET /api/zhiyun-enterprise-seeder/agent-factory/catalog` | 返回模型/工具/岗位默认工具/部门应用权限 | 模型 5 个、工具 22 个、分类默认工具 9 组、部门应用 8 组 | PASS |
| `GET /api/zhiyun-enterprise-seeder/agent-factory/templates` | 按行业（manufacturing/finance）返回 Agent 模板 | 返回 manufacturing 与 finance 两套模板，含完整 model/tools/apps/skills 指标 | PASS |
| `GET /api/zhiyun-enterprise-seeder/agent-factory/bindings` | 返回当前绑定摘要 | `models/agent_tools/agent_app_access` 均返回空（尚未落地） | PASS |
| `POST /api/zhiyun-enterprise-seeder/agent-factory/validate`（合法） | `ok=true` + 完整 config + 空 `errors` | 返回销售报价数字员工完整配置，`errors=[]` | PASS |
| `POST /api/zhiyun-enterprise-seeder/agent-factory/reconcile` | 为旧 Agent 回填模型/工具/应用绑定（幂等） | `ok=true`，`reconciled=57`（demo 环境） | PASS |

### 12.2 发现并修复的 BUG（P1，本轮已修复）

- **现象**：`POST /agent-factory/validate` 传入语义非法规格（未知部门/类别/工具，如 `tools=["not_a_real_tool"]`）时，接口返回 **500**（`KeyError: 'not_a_real_tool'`），而非返回错误清单。
- **根因**：`agent_factory.build_agent_config` 的 `tools` 列表推导直接写 `TOOL_CATALOG[t]`，未注册工具触发 `KeyError`，导致 `validate_agent_config` 无法兜住并输出语义错误。
- **修复**：`build_agent_config` 改用 `TOOL_CATALOG.get(t, {...})` 兜底，未知工具不再抛异常，保留在 config 中供校验识别；`persist_bindings` 落盘时跳过未注册工具，避免脏数据入库。
- **修复验证**：单测 `test_agent_factory.py` 7/7 通过；`python -m py_compile` 通过；服务重启后复测同一非法规格，接口返回 `200` + `ok=false` + `errors=[{"field":"tools","message":"工具未在编目注册：not_a_real_tool"}]`，行为符合预期。

### 12.3 前端 GUI 确认

- `ui/index.js` 含 `AgentFactoryPanel`（模板切换、表格、绑定摘要、「回填绑定」「校验配置」按钮），已挂载到 `EnterpriseSeeder` 渲染树；`node --check` 通过。
- 页面 `/apps/zhiyun-enterprise-seeder` 返回 `200 text/html`，非裸 JSON。

---

## 十三、2026-08-25 服务重启后端到端验收（全新 Seed / 一致性 / Production / 双态隔离 / Time Machine）

> 本轮在 Agent Factory（§12）之后，把「从全新 DB 一次初始化到完整企业环境」作为整条链路做实机验收：分别以 Demo 与 Production 两种数据环境重建两个独立环境，跑全量一致性校验，验证时间范围切换与双态隔离。接口统一携带 `Authorization: Bearer <admin token>`。

### 13.1 全新 Demo 种子（全历史区间 2025-12-01 ~ 2026-08-25）

请求：`POST /api/zhiyun-enterprise-seeder/seed`，body = `{"template":"manufacturing","enterprise":"未来智造验收","start_date":"2025-12-01","end_date":"2026-08-25","scale":50,"departments":6,"agents":9,"activity":"medium","data_mode":"demo","seed":8821}`。

结果：`env_id=env_4bc33f5caa`，耗时约 10.3s，268 天，50 用户，9 Agent，19097 sessions，38132 tasks，43446082 token，success 35107 / failed 3025。

### 13.2 Demo 环境一致性

`GET /integrity?env_id=env_4bc33f5caa&data_mode=demo` → `status=ready healthy=true total=13 passed=13 failed=0`（约 1.5s）。

关键项（均通过）：Token 一致性（任务 Token = Token 汇总 43446082）；孤儿会话/任务/文件/下载全 0；无 100% 成功率（整体失败 3025）；Token 日波动采 230 天中 104 个下降日，真实感成立。

### 13.3 Production 种子（正式数据环境）

请求：`POST /api/zhiyun-enterprise-seeder/seed`，body = `{"template":"manufacturing","enterprise":"正式业务验收","start_date":"2026-01-01","end_date":"2026-08-25","scale":30,"departments":6,"agents":9,"activity":"low","data_mode":"production","seed":7712}`。

结果：`env_id=env_9955444109`，耗时约 4.4s，237 天，30 用户，5621 sessions，11293 tasks。`GET /integrity` → `13/13 pass`。

### 13.4 Time Machine 范围切换

`GET /summary?env_id=env_4bc33f5caa&data_mode=demo&start_date=2026-03-01&end_date=2026-05-31` → sessions=6644、tasks=13388、token=15145126、files=7664、downloads=14262、logins=2016；`range={"start_date":"2026-03-01","end_date":"2026-05-31"}`。证明 sessions/tasks/token/files/downloads/logins 六类统计均随时间段真实切换。

### 13.5 Demo / Production 隔离验证

`/records/sessions` 逐条核对：

- demo 会话全部为 `env_id=env_4bc33f5caa`、`data_mode=demo`（如 `s_37ea809622d9` 归属用户 `finance_14`、智能体 `finance_invoice`、应用 `finance_center`）。
- production 会话全部为 `env_id=env_9955444109`、`data_mode=production`。
- 两套数据无交叉污染。

### 13.6 结论

**通过。** 全新 DB 一次初始化即可生成 2025-12 至当前完整企业环境（Demo 与 Production 各一套）；任意时间段筛选可切换；Demo/Production 一键切换与隔离成立；统计可追溯到底层会话/任务/Token/文件/下载/登录记录；前台全程无「模拟 / Mock」痕迹。

### 13.7 遗留与风险

- `models` 表新增不反向回写 `agents.model` 列（agent 行仍存模型名 `cfg["model"]["name"]`）。
- 本地模型服务不可达（`kilo/kilo-auto/free`）会阻断真实模型驱动的 Agent 执行；`Simulation Runtime`（Epic 3）已用可配置规则引擎落地并实机验收，见 §14。
## 十四、Simulation Runtime（Epic 3）端到端验收（2026-08-25）

> 时间：2026-08-25（服务已重启，源码与运行时 bundle SHA256 一致）
> 接口：统一携带 `Authorization: Bearer <admin token>`，前缀 `/api/zhiyun-enterprise-seeder`
> 结果：规则驱动运行时可用；preview 只读；force 重跑幂等；事件审计闭环成立；Demo/Production 双环境一致性 13/13。

### 14.1 能力范围

`simulation_runtime.py` 将「直接插行」升级为可追溯事件闭环：

```
业务事件 → Agent 执行 → Skill/Tool 调用 → 结果工件 → 下载 → Token → 用户行为 → 统计
```

新增能力：

- `_stable_day_seed`：用 `zlib.crc32` 生成跨进程、跨调用稳定的每日随机种子（替代不稳定的内建 `hash`）。
- `build_day_events` / `execute_day_events`：构建内存计划与落库执行分离；计划不写库。
- `log_business_event` / `list_events`：为每步写 `business_events` 审计行并支持按 `env_id/data_mode/day` 查询。
- `preview_interval` / `run_interval`：范围预览（只读）与范围执行。
- `_clear_day`：`run_interval(force=True)` 先清空该环境该日的运行期业务表（file_downloads/files/tasks/sessions/token_usage/business_events）再写入，避免重复插入。

新增端点（`enterprise_plugin.py`）：

- `GET /simulation/status`：环境列表 + 全局审计计数。
- `GET /simulation/preview`：按范围预览（只读，不写库）。
- `POST /simulation/run`：按范围运行（`force` 可强制重写，幂等）。
- `GET /simulation/events`：查询业务事件审计记录，支持日期范围与 `limit`。

### 14.2 单测结果

运行目录 `plugins/zhiyun-enterprise-seeder`：

```powershell
python -m unittest -v test_simulation_runtime
```

结果：**6/6 OK**（含 `test_run_force_replaces_without_duplicates` 幂等用例）。

同批回归：`test_agent_factory` 7/7 OK；`test_data_core`（`plugins/zhiyun-data-core`）16/16 OK。

### 14.3 实机接口验收

1. `GET /simulation/status`：返回 9 个环境；`totals.business_events` 随运行增长。
2. `GET /simulation/preview?env_id=env_4bc33f5caa&data_mode=demo&start_date=2026-08-20&end_date=2026-08-24`：5 天 / sessions 267 / calls 549 / tokens 598965；只读，不写库。
3. `POST /simulation/run`（`force=true`，`2026-08-20~2026-08-24`，`seed=1`）：
   - 第一次：`days_written=4`，sessions 267 / calls 540 / success 488 / failed 52 / tokens 609749。
   - 第二次（同参数 `force=true`）：`days_written=4`，sessions 267 / calls 540 / success 488 / failed 52 / tokens 609749。
   - **完全一致，证明 force 重写不会重复插入。**
4. `GET /simulation/events?env_id=env_4bc33f5caa&data_mode=demo&limit=5`：返回 5 条，完整 `session → task → file → download` 链路，含 `agent_id / skill_id / tool_id / tokens / latency`。
5. `GET /simulation/status`：demo `business_events=1680`（4 天 × 约 420 事件/天）。

### 14.4 一致性（Integrity）与双态隔离

- demo（`env_4bc33f5caa`）：`total=13 passed=13 failed=0 healthy=true`；组织 50 人 / 9 Agent / 18971 会话 / 37897 任务 / 21529 文件 / 39932 下载 / 5765 登录。
- production（`env_9955444109`）：`total=13 passed=13 failed=0 healthy=true`；组织 30 人 / 9 Agent / 5621 会话 / 11293 任务 / 6495 文件 / 12035 下载 / 2348 登录。
- `GET /simulation/events?env_id=env_9955444109&data_mode=production` 返回 `events=[]`，未污染；demo 事件均归属 `env_4bc33f5caa`。

### 14.5 发现并修复的 BUG 与残留

**修复（P2，已闭环）**：`force=true` 重跑会在既有会话/任务/文件/下载/Token/事件之上再次插入，导致统计翻倍。已通过 `_clear_day` 在写入前清理该日对应业务表实现幂等，单测与接口复测均通过。

**残留（交接）**：

- ✅（2026-08-25 复盘落地）`_clear_day` 已扩展清理 `login_activity / operation_logs`；`build_day_events/execute_day_events` 新增生成并写入「登录活动 + 操作日志」，使「登录 -> 打开应用 -> 对话 -> 任务 -> 文件 -> 下载」全链路可回溯，每步都写入 `business_events`。
- ✅（2026-08-25 复盘落地）`business_events` 已纳入 `/integrity`，新增第 14 项 `business_event_scope`（业务事件无孤儿引用），demo 与 production 均 `14/14` 通过。
- 本地模型服务不可达，真实模型驱动执行不可用；规则驱动运行时不受影响。

### 14.6 数据闭环补全：登录/操作日志 + 业务事件链（2026-08-25 复盘落地）

**目的**：消除「有会话无登录、有调用无用户行为」的穿帮，让新 `Simulation Runtime` 产出的数据链路完整可回溯。

**改动**：
- `simulation_runtime.py`：`build_day_events` 计划新增 `logins`（按工作日/月度比例抽样、带随机失败与设备/IP）与 `operations`（打开应用）；`execute_day_events` 落库 `login_activity / operation_logs`，并为每个登录/操作写一条 `business_events`。放在会话/任务/文件/下载生成之后，不影响主链路 RNG 序列。
- `_clear_day`：`force` 重写时同步清理 `login_activity / operation_logs`，保证幂等。
- `enterprise_plugin.py`：`/integrity` 新增第 14 项 `business_event_scope`，校验 `business_events` 引用的 session/task/file/download/user/agent 均存在。

**实机证据（demo `env_4bc33f5caa`）**：
- `force` 重跑 `2026-08-20 ~ 2026-08-24`（seed=1）：`days_written=4`，sessions=267 / calls=540 / tokens=609749，与重跑前完全一致（主链路不受扰动）。
- 4 天范围业务事件明细：session=267、task=540、file=294、download=579、login=81、operation=3，合计 1764（原 1680 + 81 登录 + 3 操作）。
- 再次 `force` 幂等：sessions=18971、tasks=37897、business_events=1764、login_activity=5712、operation_logs=136 全部不变。
- `login_activity` 校验：老值 5765 → 新值 5712（先按 `_clear_day` 清除该范围旧登录 134 行，再写入 81 行，净 -53），证明 `force` 对登录表已正确清理重建。
- `/integrity`（demo）：`total=14 passed=14 failed=0 healthy=true`，`business_events=1764`，新增 `business_event_scope` 为 `pass`。

## 十五、Epic 4 趋势分析（/analytics/trends）验收（2026-08-25 服务重启后）

### 15.1 端点与参数

- `GET /api/zhiyun-enterprise-seeder/analytics/trends`：带 Bearer 鉴权（`_require_auth`）。
- 参数：`authorization`、`env_id`（不传默认取最新 meta）、`data_mode`（demo/production）、`start_date`、`end_date`、`granularity`（默认 `day`，合法 `day/week/month`，非法自动回退 `day`）。
- 返回：`series`（按时间分桶的活动量）、`workday_avg` / `weekend_avg`（工作日/周末均值）、`growth`（智能体/用户首次活跃累计）、`summary`（区间总量）。

### 15.2 修复的真实 BUG（分级 P2，均已闭环）

1. `analytics.py` `_first_activity_cumulative`：构建 SQL 时 `{group_col}` 未做 f-string 插值，SQLite 抛 `unrecognized token "{"`。已改为 f-string（当前第 120~122 行）。
2. 最后一个月 cutoff 被统一 clamp 到该月月末，当 `end` 为当月 1 日时会把当月活动全部排除、导致 `growth=0`。已改为当 `cur == end_ref` 时 `cutoff = end_day`（当前第 138~142 行）。

### 15.3 单测

- 新增 `test_analytics.py`，7 个用例全通过（含日/周/月聚合并、工作日均值>周末、增长单调、非法粒度回退、downloads/logins/operations 非零）。
- 全套 seeder 单测（`test_analytics + test_agent_factory + test_simulation_runtime`）20/20 OK。
- 运行命令（在 `plugins\zhiyun-enterprise-seeder` 目录）：`python -m unittest test_analytics test_agent_factory test_simulation_runtime -v`；Python 为 `apps\qwenpaw-embedded\runtime\qwenpaw\venv\Scripts\python.exe`。

### 15.4 前端新增

- `ui/index.js`：`RANGE_PRESETS` 已含 `last_month / quarter / year`；`rangeFor` 实现对应日期计算。
- 新增 `TrendSpark` / `TrendPanel`、粒度 state、`loadTrends`；在「环境概览」与「数据一致性」之间插入「趋势分析」卡。
- 新增时间档位（上月 / 本季度 / 今年）与粒度切换（日 / 周 / 月）。
- `node --check` 通过；源码副本与运行副本（`apps\qwenpaw-embedded\workspace\plugins\zhiyun-enterprise-seeder\ui\index.js`）MD5 一致。

### 15.5 实机 API 数值（production `env_9955444109`，2026-01-01 ~ 2026-08-25，日粒度）

- `summary`：sessions=5621、tasks=11293、tokens=12763511、calls=11293、files=6495、downloads=12035、logins=2348、operations=130（与 `/summary` 完全一致）。
- `workday_avg.sessions=32`、`weekend_avg.sessions=3`（工作日显著高于周末）。
- `growth` 末端：agents=6、users=27（首次活跃累计口径）。
- 跨粒度一致性：`2026-08-01 ~ 2026-08-25` 周粒度 5 桶、月粒度 1 桶，summarySessions=718 与日粒度一致。

### 15.6 前端 Playwright 实测（切档联动）

- 登录 `admin / ZhizaoYun@2026` 后访问 `/apps/zhiyun-enterprise-seeder` 完整渲染。
- 趋势卡含「日 / 周 / 月」粒度按钮、总量、工作日/周末均值、六条曲线。
- 切「本月」后顶部 KPI 与趋势同步变为 `2026-08-01 ~ 2026-08-25 / 会话 718 / 任务 1432 / Token 1647625 / 文件 837 / 下载 1487 / 登录 314`。
- 切「月」粒度后序列变为「近 8 个月」；再切「本月」变为「近 1 个月」，随档位联动。

### 15.7 修复 BUG（前端趋势卡单点视觉，低优先级）

- 现象：`TrendSpark` 在区间只有 1 个点（如「本月」+「月」粒度）时只画左角点 + 退化三角，视觉上像空图。
- 修复：单点时改为居中标尺点 + 底部基线；保留 CRLF、无 BOM、`node --check` 通过。
- 已同步源码副本与运行副本。

### 15.8 口径说明（重要）

- `/summary` 的 `agents=9 / org_users=30` 是**配置规模**。
- `growth` 曲线是**首次活跃累计**：只有产生过会话活动的实体才计数，因此末端为 `agents=6 / users=27`。
- 两者口径不同，不是 Bug。前端按「累计活跃」语义标注，避免被误读为数据不一致。

### 15.9 证据截图（已入库 `docs/qa/screenshots`）

- `docs/qa/screenshots/seeder_trend_viewport.png`：趋势面板全貌。
- `docs/qa/screenshots/seeder_trend_chart.png`：六条曲线（日粒度 / 237 日）。
- `docs/qa/screenshots/seeder_trend_month_range.png`：修复前「本月 + 月」粒度单点空图。
- `docs/qa/screenshots/seeder_trend_fixed_single.png`：修复后单点 + 基线。
- `docs/qa/screenshots/seeder_login.png`、`seeder_full.png`：登录与主界面。

## 16. Epic 4 DataContext 广播验收（2026-08-25）

**验收方式**：全新库一键初始化 -> 2025-12 至当前持续运行；任意日期可查用户/智能体/聊天/Token/应用/权限/文件/执行统计；Demo/Production 一键切换；统计可追溯。

**结果：通过（Epic 4 状态 in_progress -> test）**

- 活动上下文落库：`data_core_meta.active_context` 存 `data_mode + env_id + start_date + end_date`；`PUT /context` 下发、`GET /context` 读取。
- `/orders` / `/records/{entity}` 未显式传参时自动套用活动上下文；在 `data_mode`/日期未传时自动继承。
- `zhiyun-enterprise-seeder` 在 `loadAll / loadSummary / doGenerate / agentCommand` 成功后自动 `publishDataContext` 广播。
- 实测（服务重启后）：企业环境初始化器加载后上下文自动变为 `env_9955444109 / production / 全量窗口`；外部 `/apps/zhiyun-data-studio` 未传参即自动继承：demo 全量「订单总数 100 / 风险表填充」，production「订单总数 0 / 空」。
- `GET /orders` 窗口测试：`demo + 2026-08-20~08-22` 返回 25 条且全部落在区间内；源码与运行副本 SHA256 一致。
- 证据截图：`docs/qa/screenshots/studio-inherit-demo.png`、`docs/qa/screenshots/studio-inherit-production.png`。

**残留**：外部 Studio 前端来源列显示「模拟数据」标签（第三方 GitHub 仓库，待 Epic 5 在源项目统一改口）；`data-core` 中 `orders` 生产数据为 0 属正常（当前仅在 demo 侧生成，非 Bug）。

---

## 17. Fresh Init + 双态 + Time Machine + Token 可追溯验收（2026-08-25 晚）

**验收方式**：隔离临时库一键初始化（不动线上服务），校验 Epic 1~6 的端到端可追溯链。

**运行脚本**：`scripts/qa/verify_enterprise_fresh_init.py`（用临时 `ZHIYUN_ENTERPRISE_DIR` + stub qwenpaw，不触碰线上 `enterprise.db`）。

**结论：48/48 全通过**。

### 17.1 覆盖清单

| 域 | 断言 | 结果 |
| --- | --- | --- |
| Epic 1 | demo/production 均生成 enterprise_meta，起始 2025-12-01、结束为今天或晚于今天 | PASS |
| Epic 1 | 17 类实体（部门/角色/用户/Agent/Skill/应用/数据源/绑定/会话/任务/Token/日志/文件/下载/业务事件）均非空 | PASS |
| Epic 4 | Time Machine：2026-03 窗口会话仅落在窗口内 | PASS |
| Epic 5 | 双态隔离：demo/production 各自有会话，demo 不泄漏生产记录（crossing=0） | PASS |
| Epic 6 | Token 可追溯：`token_usage.token == business_events(全量).token == business_events(仅task).token == tasks.token` | PASS |
| Epic 6 | 任务行数 == `token_usage.calls` | PASS |
| Epic 2 | Agent->Skill->Tool 绑定落地 | PASS |

### 17.2 本轮发现并修复的真实 BUG（P2，已修复）

- **现象**：审计链 Token 双算。隔离验收首次运行 46 项中 45 通过，仅「token_usage.token == business_events.token」失败，实测 `business_events.tokens=67,885,310` vs `token_usage.tokens=35,013,011`，约 2x。
- **根因**：`simulation_runtime.execute_day_events` 为每个会话（session）事件也写了一条带 Token 的 `business_events`，同一会话下的任务（task）事件再写一次 Token，导致「会话级 Token + 任务级 Token」叠加。
- **权威口径**：Token 以 `tasks.tokens` 为权威，`token_usage.tokens` 按其累加；完整性检查器 `task_token == token_total` 成立。
- **修复**：`business_events` 审计行仅当 `event_type == 'task'` 才记 Token；`session/file/download/login` 事件 Token 记 0。使 `sum(business_events.tokens) == sum(token_usage.tokens) == sum(tasks.tokens)`。
- **自愈**：`_repair_integrity` 新增 `business_event_token_accounting` 修复动作，把既有库中非任务事件的 Token 归零并写入 `integrity_repair_log`，幂等且不删除任何行为记录。

### 17.3 测试

- Seeder 单测新增：`test_simulation_runtime.test_business_events_token_not_double_counted`（生成侧不双算）与 `test_integrity.test_repair_zeroes_non_task_business_event_tokens`（修复侧归零并保留 task Token）。
- 全套 Seeder 单测：`test_simulation_runtime + test_agent_factory + test_analytics + test_integrity` = **25/25 OK**。
- 隔离验收脚本：`verify_enterprise_fresh_init.py` = **48/48 PASS**。

### 17.4 证据文件

- `docs/qa/enterprise-fresh-init-verify.json`：48 项逐条结果。
- `scripts/qa/verify_enterprise_fresh_init.py`：可重复运行的隔离验收脚本。
