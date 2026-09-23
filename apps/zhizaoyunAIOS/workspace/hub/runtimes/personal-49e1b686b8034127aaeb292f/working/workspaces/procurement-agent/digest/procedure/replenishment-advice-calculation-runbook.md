---
description: 每日补货建议的标准算法链 runbook：以 calc_params.snapshot_at 锚定快照，从 v_inventory_alert
  等视图取数并用基表复算校验，按「近30天生产领用均值→ROP→扣库存与在途→按包装批量向上取整且满足MOQ」算建议量，含跨单位消耗与视图舍入差异等陷阱。
kind: procedure
name: 补货建议量计算 runbook（取数视图 + 消耗口径 + ROP/取整规则）
snapshot_anchor: calc_params.snapshot_at
traps:
- 跨单位数量不可合计
- 视图与流水直算舍入差异
- 紧急判定口径冲突
---

# 补货建议量计算 runbook（取数视图 + 消耗口径 + ROP/取整规则）

## Trigger

需要产出某快照日的每日补货建议 / 补货单（含供应商候选与交期缺口）时。

## Pre-conditions

- `calc_params` 可读：提供 `snapshot_at`、安全库存阈值、评分权重。
- 视图：`v_inventory_alert`、`v_replenishment_advice`、`v_supplier_recommendation`、`v_candidate_pool_all`。
- 基表：`inventory_snapshot`（JOIN `material_master`）、`inventory_txn`。

## Steps

1. 读 `calc_params.snapshot_at` 锚定快照时刻，一切"当前/今日"以它为准，不用系统时间；同时记下 `inventory_txn` 最晚日期与区间笔数。
2. 从 `v_inventory_alert` 取「当前库存 < 安全库存阈值」的 SKU（视图定义即此 WHERE + 缺口数量/可用天数/采用日均消耗/预警状态），按可用天数升序排。
3. 用基表复算校验视图：`inventory_snapshot` JOIN `material_master` 重跑同一条件，比对行数与逐字段值（12 SKU / 6 预警 / 4 紧急 这类计数）。
4. 算日均消耗 = 近 30 天「生产领用」均值，该 SKU 无数据则回退 90 天；「采购入库」一律不计消耗。
5. 算 `ROP = 日均消耗 × 采购提前期 + 安全库存阈值`。
6. 若 `当前库存 + 在途 ≥ ROP` → 建议量 0，明确写"在途覆盖"（M06：36+121=157 ≥ 145.2，故不下单）。
7. 否则 `建议量 = ⌈(ROP − 当前库存 − 在途) / 包装批量⌉ × 包装批量`，再抬到不低于 MOQ（如 M01 MOQ30/批量15、M02 40/20）。
8. 关联 `v_supplier_recommendation` 取 TOP3 与价格校验标注；用 `v_candidate_pool_all` 数该品类合格候选数，为 0 时转人工，不编造推荐。
9. 比对建议下单日与耗尽日，按提前期推算交期缺口天数，给出加急 / 分批发货 / 产线借料 / 临时提高阈值的动作。
10. 输出时原样沿用数据库现有预警状态，把发现的口径分歧单列"待复核"，不擅自改判。

## Failure modes / caveats

- `inventory_txn.数量` 跨单位（件/套/支/台）：任何"合计消耗"必须先按 SKU+单位分组，绝不能当单一单位相加（217 这类数字只是笔数聚合的假总量）。
- 视图口径与流水直算会有四舍五入级差异（全厂日均 110.13 vs 3524÷30=117.5）：复算不一致先查舍入，再怀疑逻辑。
- 供应商评分是交期紧迫度评分且未校准（0.45 准时 + 0.35 合格 + 0.20 价格竞争力），不等于质量结论；近 180 天仅 1 批的薄样本可拿到满分，需小批验证。
- 紧急判定存在口径冲突：文档为「可用天数<5 或 库存<阈值×50%」，数据只执行了 `<50%` 分支，会让低可用天数 SKU（M01 3.9 天/51.1%、M06 3.6 天/54.5%）漏升级为紧急。
- 单日领用峰值（M09 领 45 = 日均 6.1×）会使按昨日速率重估的可用天数骤降：默认仍用 30 天均值，把速率重估作为敏感性对比。

## Sources

- [[memory/2026-09-18.md|2026-09-18 当日笔记]] 汇总了该快照下 6 项低于安全库存、5 项下单共 940 件、M06 在途覆盖为 0 的结论，并记录了可复用 SQL 清单与紧急口径冲突，是本 runbook 步骤 2/6/10 的证据来源。
- [[memory/2026-09-18/replenishment-advice-supplier-shortlist.md|补货与供应商推荐明细]] 给出逐步细节：`calc_params.snapshot_at` 锚点、`v_inventory_alert` 视图定义与基表复算一致、ROP/建议量/MOQ 取整公式、跨单位消耗陷阱与 110.13 vs 117.5 的舍入差异，支撑步骤 1/3/4/5/7 与上述 caveats。
