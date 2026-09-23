---
name: procurement
description: "金汉隆智能采购技能（功能15 供应商评估与智能补货）。用于库存预警、供应商准时率/合格率/综合评分、补货量与最优供应商推荐、比价提示与转人工判定、补货口径解释。双通道：kb_search.py 检索《金汉隆-智能采购》知识库（口径/字段/事实），query.py 对只读计算副本 agent_data.sqlite 执行 SELECT 视图计算。Use for Jinhuanlong procurement: safety-stock alerts, supplier scoring, replenishment quantity & best-supplier recommendation."
metadata:
  builtin_skill_version: "1.0"
  qwenpaw:
    emoji: "🛒"
    requires: {}
---

# 金汉隆智能采购技能（供应商评估与智能补货）

本技能目录 `scripts/` 下两件工具（以本 SKILL.md 所在目录为根；若当前目录不是技能目录，先 find/glob 定位 `procurement/scripts/query.py`）：

| 脚本 | 用途 | 示例 |
|---|---|---|
| `scripts/query.py` | 对只读副本 `procurement/agent_data.sqlite` 执行只读 SQL（仅 SELECT/PRAGMA） | `python3 procurement/scripts/query.py "SELECT * FROM v_inventory_alert"` |
| `scripts/kb_search.py` | 检索《金汉隆-智能采购》知识库（全量表 + 字段字典 + 业务口径） | `python3 procurement/scripts/kb_search.py "补货量怎么算"` |

工作区数据目录 `procurement/`：`agent_data.sqlite`（只读计算副本）、`docs/`（口径/字段字典）、`output/`（输出目录，可写）。

## 使用规则

1. **数字必须来自 query.py 的视图计算**（v_daily_consumption / v_ontime_rate / v_quality_rate / v_supplier_score / v_candidate_pool / v_supplier_recommendation / v_inventory_alert / v_replenishment_advice；明细核对用 v_ontime_detail 准时明细 / v_quality_detail 质检明细），知识库用于口径、字段与证据。被问"准时率/合格率哪来的"时，用明细视图逐批展示（到货 vs 承诺、检验 vs 合格）。
2. 固定快照时间从 `calc_params.snapshot_at` 读取（= 2026-09-18 08:00 北京时间），不得用机器当前日期。
3. 只读纪律：不写库、不回写企业系统；评分输出标注「交期紧迫度评分，未校准」。
4. 无合格候选 → 转人工，不编造；建议量必须扣减在途。
5. 发送动作只允许 Mock 推送：`POST http://127.0.0.1:18765/api/mock/wechat/push`（recipient_group=WB_MANAGEMENT，带 idempotency_key）。
6. 输出附：SKU/供应商编码、快照时间窗口、单位、原始证据（SQL 或文档出处）。

## 不适用场景

- 与企业采购数据无关的通用闲聊/写作（直接回答即可）。
