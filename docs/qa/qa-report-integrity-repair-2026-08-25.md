# Data Integrity（zhiyun-enterprise-seeder）自动修复 · 每日快照 · 历史轨迹 QA 报告

> 日期：2026-08-25
> 服务：`http://127.0.0.1:8088`（QwenPaw 2.1.0，已重启加载新插件）
> 应用：`/apps/zhiyun-enterprise-seeder`（企业环境初始化器）
> 范围：Epic 6 Data Integrity 收尾——安全自动修复策略 + 每日一致性快照 + 历史轨迹
> 结论：**通过（PASS）**，可标记 Epic 6 为 `completed`。

---

## 一、本轮改动

- 后端 `plugins/zhiyun-enterprise-seeder/enterprise_plugin.py`：
  - 新增表 `integrity_reports`、`integrity_repair_log` 及对应索引（升级时建表）。
  - 新增 `_repair_integrity`（安全自动修复）、`_daily_integrity_report`（每日快照，懒生成+幂等持久化）、`_integrity_history`（历史轨迹）。
  - 新增端点：`GET /integrity/daily`、`GET /integrity/history`、`POST /integrity/repair`（repair 仅管理员）。
  - 新增 Agent 工具：`run_integrity_repair`、`query_daily_integrity_report`、`query_integrity_history`。
  - 启动钩子 `_ensure_schema` 尾部调用 `_daily_integrity_report()`（try/except 包裹），实现“每日自动生成”。
- 前端 `ui/index.js`：数据一致性卡片新增三按钮（自动修复 / 运行检查 / 今日快照），并在按钮下渲染「今日快照」摘要行；自动修复结果写入 Agent 抽屉。
- 新单测 `plugins/zhiyun-enterprise-seeder/test_integrity.py`。

## 二、安全自动修复规则（不伪造数据）

| 检查项 | 规则 |
| --- | --- |
| `session_user_scope` / `session_agent_scope` | 删除无归属（孤儿）会话 |
| `task_session_scope` | 删除无归属任务 |
| `file_task_scope` | 删除无归属文件 |
| `file_download_scope` | 删除无归属下载记录 |
| `file_download_consistency` | 依据下载事件回写 `files.download_count` |
| `user_agent_binding` | 回填同环境首个可用智能体 |

人工决策项（`login_binding` / `permission_scope` / `success_rate_variance` / `daily_volatility` / `business_event_scope`）一律不改动，全部行为写入 `integrity_repair_log` 审计。

## 三、单元测试

运行环境：`apps/qwenpaw-embedded/runtime/qwenpaw/venv/Scripts/python.exe`

```bash
python -m unittest test_integrity -v
# test_daily_report_idempotent_and_history ... ok
# test_repair_cleans_orphans_and_recalcs ... ok
# test_repair_empty_env ... ok
# Ran 3 tests ... OK
```

旧基线回归：

```bash
python -m unittest test_agent_factory test_simulation_runtime test_analytics -v
# Ran 20 tests ... OK
```

合计 **23/23**。`python -m py_compile enterprise_plugin.py` 通过。

## 四、实机接口证据（服务重启后）

鉴权：`Authorization: Bearer <zhiyun-auth token>`（管理员，见 `.admin_token.txt`）

1. **每日快照** `GET /api/zhiyun-enterprise-seeder/integrity/daily?env_id=env_4bc33f5caa&data_mode=demo`
   - `status=ready`，`total=14`，`passed=14`，`failed=0`，`healthy=true`，`report_day=2026-08-25`，`persist=inserted`。
   - 14 项全部 `pass`，如 `execution_total`（37897=34906+2991）、`token_consistency`（43169005）、`file_download_consistency`（39932=39932）、`business_event_scope`（1764，孤儿引用 0）。

2. **幂等**：同日再次调用 → `persist=updated`，`passed=14/14`（同一天重复生成为更新，而非新增）。

3. **自动修复** `POST /api/zhiyun-enterprise-seeder/integrity/repair`（body `{env_id, data_mode}`）
   - `{ok:true, status:ready, run_by:admin, fixed_checks:[], remaining_checks:[]}`，`report` 15 项检查 `passed=14/14`。
   - 修复项如 `user_agent_binding` 回填目标 `sales_quote`，当环境已健康时 `affected=0`。

4. **历史轨迹** `GET /api/zhiyun-enterprise-seeder/integrity/history?env_id=env_4bc33f5caa&data_mode=demo&limit=5`
   - `count=1`，行含 `report_day / total / passed / failed / healthy / created_at / updated_at`，按 `report_day DESC` 排序。

5. **鉴权**：无 token 调用 `/integrity/daily` → `HTTP 401`（强制鉴权，repair 仅管理员）。

6. **默认环境**：不带 `env_id/data_mode` 调用 `/integrity/daily` → 自动取最新 `enterprise_meta`（`env_9955444109 / production`），`passed=14/14`，`persist=updated`。

## 五、GUI 校验

- `node --check ui/index.js`：通过（语法校验）。
- 新增依赖符号（`toast` / `request` / `statusCard` / `pushAgentMessage` / `setDailyIntegrity`，均在作用域内）核验无引用错误。
- 源码与运行副本 `apps/qwenpaw-embedded/workspace/plugins/zhiyun-enterprise-seeder/*` SHA256 完全一致，`/api/version=2.1.0` 健康。
- 本轮未采集浏览器截图（工作区未安装 headless 浏览器），由人工在 `/apps/zhiyun-enterprise-seeder` 复核三按钮与「今日快照」渲染。

## 六、发现并修复的问题（分级）

| 级别 | 问题 | 修复 |
| --- | --- | --- |
| P2 | 前一轮 Data Core 升 `0.8.0`，但 `app_catalog.json` 与 `verify-phase2-acceptance.mjs`、`test_search_engine.py` 仍硬编码 `0.7.0`，导致 `verify-release.mjs` 发布门禁失败（`0.7.0 !== 0.8.0`）。 | 将 catalog 与 Phase2 验收断言同步为 `0.8.0`。 |
| P2 | `test_search_engine.py` 审计路由断言 `/apps/audit` 过时（zhiyun-audit 已改名）。 | 更新为 `/apps/zhiyun-audit`。 |
| P2 | Epic 6 仅只剩 `/integrity` 检查，缺自动修复与每日快照。 | 本轮补齐 `/integrity/repair`、`/integrity/daily`、`/integrity/history` 与前端入口。 |

## 七、验证清单回归

- `node scripts/verify-release.mjs` → **通过**（AI-OS 发布门禁通过）。
- `node scripts/verify-project-plan.mjs` → **通过**（31 项能力；已完成 13，测试中 17，开发中 1，计划中 0）。
- 服务健康：`/api/version=2.1.0`，13/13 核心端点 `available`。

---
*本报告所有数字均取自 2026-08-25 服务重启后的真实接口响应，未做硬编码或伪造。*
