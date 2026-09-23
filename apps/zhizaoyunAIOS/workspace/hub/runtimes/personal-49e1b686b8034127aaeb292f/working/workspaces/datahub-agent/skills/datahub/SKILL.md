---
name: datahub
description: "金汉隆AI数据中枢技能。用于订单进度看板、交付风险预警、多源数据采集、跨部门融合指标、每日08点简报、关键指标趋势分析六类数据分析任务。双通道协作：kb_search.py 检索《金汉隆-数据中枢》知识库（口径/字段/事实），query.py 与 calc.py 对计算副本 agent_data.sqlite 做只读SQL聚合与统计回归。Use for Jinhuanlong data-hub analytics: order progress board, delivery risk early-warning, multi-source collection, cross-department metrics, daily brief, KPI trends."
metadata:
  builtin_skill_version: "1.0"
  qwenpaw:
    emoji: "📊"
    requires: {}
---

# 金汉隆 AI 数据中枢技能

本技能目录 `scripts/` 下五件工具（以本 SKILL.md 所在目录为根；若当前目录不是技能目录，先 find/glob 定位 `datahub/scripts/query.py`）：

| 脚本 | 用途 | 示例 |
|---|---|---|
| `scripts/query.py` | 对计算副本 `datahub/agent_data.sqlite` 执行只读 SQL（mode=ro，仅 SELECT/PRAGMA） | `python3 datahub/scripts/query.py "SELECT COUNT(*) FROM orders"` |
| `scripts/kb_search.py` | 检索《金汉隆-数据中枢》知识库（含30张表全量数据与口径文档） | `python3 datahub/scripts/kb_search.py "订单完成的口径是什么"` |
| `scripts/calc.py` | 均值 / 最小二乘斜率 / 变化率（支持 7 点均值、14 点回归场景） | `python3 datahub/scripts/calc.py 0.47,0.45,0.42` |
| `scripts/collect.py` | 多源采集演练：raw -> 标准化/去重/坏样本隔离 -> datahub/output/ | `python3 datahub/scripts/collect.py` |
| `scripts/delivery_risk.py` | 需求2 交付风险红黄绿：在途/未发货订单延期概率、P50/P90 预计签收、依据与样本量 | `python3 datahub/scripts/delivery_risk.py [--json]` → `datahub/output/delivery_risk_<YYYYMMDD>.md/.csv` |

工作区数据目录 `datahub/`：`agent_data.sqlite`（计算副本）、`docs/`（schema/字段字典/口径/示例SQL）、`raw/`（采集源样本）、`output/`（输出目录，可写）。

## 使用规则

1. **数字必须来自 query.py / calc.py 的真实计算**，不得凭知识库片段心算全量汇总；知识库用于口径、字段说明与证据。
2. 固定快照时间从 `configuration.snapshot_at` 读取（= 2026-09-18 08:00 北京时间），不得用机器当前日期。
3. 只读纪律：query.py 以 mode=ro 打开数据库，不得写库、不得回写企业系统。
4. 发送动作只允许 Mock 推送：`POST http://127.0.0.1:18765/api/mock/wechat/push`，`recipient_group=WB_MANAGEMENT`，带 `idempotency_key`（重复请求会被幂等忽略）。
5. 输出附：订单号/工单号、时间窗口、单位、原始证据（SQL 或文档出处）；概率类输出标注"交期紧迫度评分，未校准"。

## 不适用场景

- 与企业数据无关的通用闲聊/写作（直接回答即可）。
