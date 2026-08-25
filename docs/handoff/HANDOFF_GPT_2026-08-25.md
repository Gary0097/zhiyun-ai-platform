# 智云 AI-OS · 全量交接文档（2026-08-25 · 给最强 GPT 继续完善）

> 交接日期：2026-08-25
> 前置文档：`docs/handoff/HANDOFF_GPT_2026-08-24.md`（本轮在其基础上推进，二者合一可还原全貌）
> 交接目标：让后续模型**只在 `zhiyun-ai-platform` 仓库内**即可掌握本轮全部改动、已验证事实、遗留问题与下一步，无需重新摸索。

---

## 1. 本轮目标与用户诉求（按顺序）

1. 完成剩余「17 项基础开发」，完成后叫我测试。
2. 全部功能 UI 深度重构；交互参考本项目，界面/交互需重构；无交互 PRD，交互方案由实现方拟定；B 端简洁高效；**所有功能应用嵌入 Agent 对话框**；PRD 追加需求变更。
3. 做相关功能测试（拟人化交互）；测试用例与结果输出进项目；有 BUG 修复并标注等级。
4. 追加：登录与权限，不同用户使用不同 Agent/数据/知识库；同企业共享，不同企业单独启动系统（单租户实例）。
5. 完整整理本轮更新与记录，产出完整交接文档。
6. 最新反馈：**测试不通过，全部功能都只有 json 数组，都不知道怎么用，新开发的功能也没有正常的 GUI 界面。**
7. 最新指令：**重启一下服务，我检查一下需要更新的内容。**
8. 收尾指令：**暂停功能开发，项目收尾，全面编写交接文档与资料，交给其他 Agent 接管。**

---

## 2. 当前服务状态（已重启并核验）

- 地址：`http://127.0.0.1:8088`
- 版本：`GET /api/version` → `{"version":"2.1.0"}`
- 企业种子：`GET /api/zhiyun-enterprise-seeder/health` → `{"status":"ok","database_exists":true}`
- 启动日志：`C:\AI\zhiyun-ai-os-workspace\.qwenpaw-start.log` / `.qwenpaw-start.err.log`（本轮用 `start.mjs` 后台重启）
- 登录：`admin` / `Zhiyun@2026`；token 文件 `C:\AI\zhiyun-ai-os-workspace\.admin_token.txt`
- 浏览器可访问；应用直达路径为 `/apps/<plugin-id>`（如 `/apps/zhiyun-sales-studio`）。

---

## 3. 本轮完成 / 已验证事实（2026-08-25）

### 3.1 登录与权限（RBAC + 单租户，本轮已落地前端与登录）

- 新增 `plugins/zhiyun-auth`：`/api/zhiyun-auth/config|me|login`，基于 JWT，`localStorage.zhiyun_token` 承载会话；登录后 `zhiyun:auth` 事件广播用户 `display_name / role / agent_id`。
- 右上角悬浮用户卡（`系统管理员 · admin / 智云AI · Agent: 默认` + 退出），未登录时全屏登录层。
- 意图（后续服务端强鉴权见第 5 节）：同一企业共享实例内 Agent/数据/知识库，用户按 RBAC 看到授权范围；不同企业各自独立实例。

### 3.2 全平台 GUI / 功能（真实登录后，Playwright + Chrome 实测）

- **11/11 应用** 登录后均渲染为结构化 GUI：标题 + 工具条 + 输入/表格 + 结果面板/按钮；`body` 无原始 JSON 泄露（`jsonLeak=false`，`preLen=0`），登录层消失。
- **11/11 应用** 点击「载入示例 + 运行」后结果区非空、非「暂无分析结果」、无执行错误。
- **11/11 应用** 均有可用的应用内「问 Agent」抽屉（含输入框）。
- 关键实测：销售 KPI `41780 / 125 / 4 / 10445`；服务置信度 `0.84`、意图`订单查询`、命中知识`是`、方法 `faq-keyword-v1`；人力用户数`3`；数据核心`370 条（演示 370 / 正式 0）`；审计`审计链完整性已验证`；订单`反馈订单 A202608001 / 模板 标准销售订单 (medium 50) / 提取证据 unit_price 6800`。
- 后端全量：**207 测试全通过 / 51 测试文件全通过**（见 QA 报告第六节）。

### 3.3 证据文件（本次新增）

- 报告：`docs/qa/qa-report-full-gui-functional-2026-08-25.md`
- 渲染探测：`docs/qa/ui-post-login-probe.json`
- 功能探测：`docs/qa/functional-interaction-probe.json`
- 截图：`docs/qa/screenshots/{post-login,functional}/*.png`（功能截图含每应用 `-agent.png`）
- 探测器：`scripts/qa/functional_gui_probe.py`
- 计划追加：`docs/product/PROJECT-PLAN.md` 末「Full-platform GUI/function verification note (2026-08-25)」

### 3.4 业务事件 Token 可追溯修复（Epic 6，本轮新增）

- **定位**：`simulation_runtime.execute_day_events` 为 session 事件也写入带 Token 的 `business_events` 审计行，叠加 task 事件 Token，导致 `business_events.tokens` 约为 `token_usage.tokens` 的 2x。
- **权威口径**：Token 以 `tasks.tokens` 为准，`token_usage.tokens` 按其累加，且完整性检查器 `task_token == token_total` 成立。
- **修复**：仅 `event_type=='task'` 的 `business_events` 记 Token，其余事件记 0；使 `sum(business_events.tokens) == sum(token_usage.tokens) == sum(tasks.tokens)`。
- **自愈**：`_repair_integrity` 新增 `business_event_token_accounting` 修复动作，将既有库非任务事件 Token 归零并写 `integrity_repair_log`，幂等且不删行为记录。
- **验证**：隔离验收 `scripts/qa/verify_enterprise_fresh_init.py` = 48/48 PASS；Seeder 单测 25/25 OK。
- **证据**：`docs/qa/enterprise-fresh-init-verify.json`；QA 报告第 17 节。

#### 3.4.1 线上库 Token 修复实测（真实 BUG，已归零）

线上活动库 `apps\qwenpaw-embedded\workspace\enterprise\enterprise.db`（约 376 MB）存在同一双算问题，本轮通过线上 `/integrity/repair` 与离线修复双重确认：

- **活动环境 `env_e311fc7d35`（demo，佛山泓佳机械）**：`business_events` 全量 token 曾为 `85,394,492`，仅 task token 为 `44,049,411`，非 task 且 token≠0 行 `19,421`。线上修复已在该环境提交：`integrity_repair_log` 记录 `business_event_token_accounting affected=19421（2026-08-25 10:54:35）`。修复后 `business_events` 全量 token = 仅 task token = `token_usage` = `tasks` = **44,049,411**，bad_rows=0。
- **旧环境 `env_4bc33f5caa`（demo，未来智造验收）**：本轮离线修复再处理 `business_event_token_accounting affected=267`，修复后 `business_events` 从 `1,182,208` 降到 `609,749`（task token），非 task 带 token 行=0。
- **两环境完整性报告**：`_integrity_report` 14 项检查全部 PASS（`token_consistency`、`execution_total`、`business_event_scope`、`file_download_consistency` 等）。
- **修复入口**：`POST /api/zhiyun-enterprise-seeder/integrity/repair`（`_repair_integrity`，幂等，写入 `integrity_repair_log`）。

### 3.5 本轮发现的性能 / 并发缺陷（P2，已修复）

在尝试用 `integrity/repair` 修复线上库时，服务出现「事件循环无响应 / CPU 占满」的严重观感问题，定位到 3 个真实缺陷并全部修复：

| # | 严重级 | 根因 | 现象 | 修复 | 位置 |
| --- | --- | --- | --- | --- | --- |
| 1 | P2 | `async def` 路由（`integrity / integrity/daily / integrity/history / integrity/repair`）直接同步调用 DB 重函数 | 修复/报告请求让整个服务无响应，健康端点超时 | 用 `await asyncio.to_thread(...)` 包裹 4 个重型调用，事件循环不再被阻塞 | `plugins/zhiyun-enterprise-seeder/enterprise_plugin.py` |
| 2 | P2 | `file_downloads.download_id` 无索引，`_integrity_report` 的 `business_event_scope` 对 42,646 条带 download_id 的 `business_events` 逐行全表扫描 176,323 行 | 约 `42,646 × 176,323 ≈ 75 亿次` 比较，CPU 打满、报告近分钟无法返回 | 新增索引 `idx_downloads_id ON file_downloads(env_id,data_mode,download_id)` | `enterprise_plugin.py` `SCHEMA_SQL` |
| 3 | P2 | `file_download_consistency` 的下载计数联动子查询仅靠 `file_downloads(file_id)` 单列索引，对 95,011 个文件逐行 COUNT 下载 | `count_dl_mismatch` 查询 >90 秒仍未返回 | 新增复合索引 `idx_downloads_env_file ON file_downloads(env_id,data_mode,file_id)`，该查询降至约 0.11 秒 | `enterprise_plugin.py` `SCHEMA_SQL` |

修复后的量化验证：`_integrity_report` 3.67s 返回；`_repair_integrity`（全量）4.04s 返回；`count_dl_mismatch` 0.11s。两个新索引均已加入 `SCHEMA_SQL`（全新库自动生效），并已在线上库幂等创建。

**本会话验证链**：Seeder 单测 25/25 OK；隔离验收 `scripts/qa/verify_enterprise_fresh_init.py` 48/48 PASS；线上活动环境与旧环境修复后各自 14/14 integrity PASS。

---

## 4. 严重级缺陷记录（本轮）

本轮（真实登录 + 全平台 GUI/功能）探测**未发现 P0/P1/P2**。「功能只有 JSON / 无 GUI」P0 已在前轮修复并持续回归通过。

> 另：隔离验收（Fresh Init + 双态 + Time Machine + Token 可追溯）在 46 项中抓出 1 项 **P2 Token 双算**，已在本轮修复（见 3.4），修复后 48/48 全通过。

仅 3 项 P3 观察：

| 观察 | 等级 | 建议 |
| --- | --- | --- |
| QwenPaw 宿主「试试桌面模式」toast 每次进入应用都出现并覆盖底部 | P3 | 首次进入后 `localStorage` 记忆，或仅桌面模式展示 |
| 5 大模板 Studio 的 Agent 占位提示统一为供应文案「帮我评估这3家供应商…」 | P3 | 在 `_gen_ui.py` 按 `app_id` 输出语境化占位 |
| 订单「载入示例并运行」提示「订单信息不完整，请在表单中补充」 | P3 | 属有意引导；可优化措辞 |

---

## 5. 关键约束与下一步（给最强 GPT）

**硬约束（不要违反）：**

- `_gen_ui.py`（工作区根目录，89,405 字节）是 5 大模板 Studio（finance/sales/supply/service/people）前端的**唯一事实来源**；改前端必须改生成器，并用 `_gen_ui.py` 重新生成后同步 `workspace/plugins/<id>/ui/index.js` 与 `runtime/pawapps/<id>/ui/index.js`（需字节一致）。`zhiyun-data-studio` 独立走自身 `ui/index.js` 与契约测试，不同步该生成器。
- `workspace/plugins/**` 与 `runtime/pawapps/**` 在 `.gitignore`；git 仅跟踪 `start.mjs`、`docs/**`、`scripts/**`、`plugins/<id>/`（auth、seeder 等新增插件会跟踪）。
- 项目计划：`scripts/verify-project-plan.mjs` 读 `plugins/zhiyun-app-discovery/feature_progress.json`（31 项：已完成 13、测试中 17、开发中 1、计划中 0）。**不要为「通过门禁」伪造状态**；把某项改为 `completed` 需满足 Definition of Done（真实持久数据、校验/授权/失败态、端到端路径、`verify-release.mjs` 通过、Win/Linux、迁移回滚、100% progress）。当前 17 项 `testing` 因**等待用户实机验收**而保持 `testing`。
- `verify-release.mjs` / `verify-project-plan.mjs` / `app_catalog.json` / `feature_progress.json` 的门禁逻辑不要改动。
- 产品前台不允许出现「模拟 / Mock / 测试」字样；统一用「演示 / Demo / 真实数据」，底层字段 `data_mode=demo|production`。
- 保持空数据为空，不硬编码造数；演示数据须明确标注。

**下一步（按优先级）：**

1. 服务端强鉴权：把 Role → Agent / 数据 / 知识库边界真正落到 API 层（当前仅前端展示用户卡与权限建议矩阵）。
2. 企业实例配置化：部署时读取企业标识，分配实例级数据目录 / 模型 / Agent 配置（单租户）。
3. 处理 3 项 P3：宿主 toast 记忆、Agent 占位语境化、订单示例提示措辞。
4. 用户实机验收通过后，才把 17 项 `testing` 逐项移动到 `completed`（附证据 note 与 100%）。
5. 审计闭环：审阅人 / 动作 / 工件 / Agent 上下文导出写入 `zhiyun-audit`。
6. 给非核心应用（data-studio / order-studio / integration-hub / agent-kanban / wechat-bot-manager / factory-6s）明确「应用内 Agent 对话框」方案或声明用宿主全局对话即可。

---

## 6. 运行方式（供验收）

```powershell
# 以可写运行时数据目录启动（start.mjs 已注入 *_STUDIO_DB 指向 .qwenpaw-runtime-data）
cd C:\AI\zhiyun-ai-os-workspace\zhiyun-ai-platform
node apps\qwenpaw-embedded\scripts\start.mjs
```

浏览器打开 `http://127.0.0.1:8088`，用 `admin` / `Zhiyun@2026` 登录，按 `/apps/<plugin-id>` 逐个核验；如仍见旧界面请 `Ctrl+F5` 清缓存。
