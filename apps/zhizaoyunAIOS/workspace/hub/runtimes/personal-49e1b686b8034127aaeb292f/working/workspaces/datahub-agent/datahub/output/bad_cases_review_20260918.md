# 9 条采集坏样本 · 处置复核单

- 固定快照：`configuration.snapshot_at` = 2026-09-18T08:00:00+08:00（北京时间）
- 输入：`datahub/raw/ingestion_bad_cases.jsonl`（9 条）→ `datahub/output/quarantine.jsonl`（隔离 8 条）+ 重复忽略 1 条
- 计算副本：`datahub/agent_data.sqlite`（只读 mode=ro）
- 结论先行：**9 条全部维持"不写入干净事实表"**；其中 **1 条无需任何动作**（重复忽略判定正确）、**2 条建议直接驳回**（权威记录已在库 / 不可能是实际事件）、**6 条进入人工复核清单**（需上游改键或重发）。**可确定性自动修复的只有 1 条，且修复后仍应幂等忽略**。对已发布看板/简报数字影响 = **0 条**。

## 0. 干净表未被污染（先给安全结论）

```sql
SELECT 'orders' t,COUNT(*) n FROM orders WHERE sales_order_id LIKE 'BAD-%' OR work_order_id LIKE 'BAD-%'
UNION ALL SELECT 'work_orders',COUNT(*) FROM work_orders WHERE work_order_id LIKE 'BAD-%'
UNION ALL SELECT 'wms_transactions',COUNT(*) FROM wms_transactions WHERE transaction_id LIKE 'BAD-%'
UNION ALL SELECT 'mes_events',COUNT(*) FROM mes_events WHERE mes_event_id LIKE 'BAD-%'
UNION ALL SELECT 'oa_forms',COUNT(*) FROM oa_forms WHERE form_id LIKE 'BAD-%'
UNION ALL SELECT 'exceptions',COUNT(*) FROM exceptions WHERE source_record_id LIKE 'BAD-%'
UNION ALL SELECT 'shipments',COUNT(*) FROM shipments WHERE shipment_id LIKE 'BAD-%'
UNION ALL SELECT 'logistics_events',COUNT(*) FROM logistics_events WHERE logistics_event_id LIKE 'BAD-%';
-- 8 张表全部 0 命中
```
旁证：`ingestion_runs` ING007（脏数据测试）= 输入 9 / 入库 0 / 隔离 8，备注"坏样本不写入干净事实表"。

---

## 1. WMS / WMS0000001 —— 重复忽略（判定正确，无需动作）

- 现象：`flow_id=WMS0000001` 与库内已有流水同键。
- 库内权威记录：`WMS0000001 | SO20251221-0001 | MO20251221-0001 | M004 | 采购入库 | +20 | 件 | 2025-12-23T06:05:31+08:00`
  ```sql
  SELECT transaction_id,movement_type,signed_quantity,unit,occurred_at
  FROM wms_transactions WHERE transaction_id IN ('WMS0000001','WMS0000002');
  ```
- 处置：**幂等忽略，库存不重复增减**（口径文档《业务口径要点.md》第 59 行：库存流水按 `transaction_id` 避免重复记账）。
- ⚠️ 隐患：本条之所以能被识别，只是因为 `flow_id` 没变。见第 2、8 条——上游一旦改写 `flow_id`，现有去重逻辑就会漏判。

## 2. WMS / BAD-WMS-NEG —— 负数量 + 数量冲突（人工复核，禁止覆盖）

- 采集器判定：负绝对数量。
- 复核结论：**判定成立，但只说对了一半**。
  - 源契约：WMS 原始流 `qty` 必须为非负，符号由 `direction` 决定（口径文档第 58 行）。实测 `datahub/raw/wms/transactions.jsonl` 5418 条中 `qty<0` = **0 条** → 本条 `-8` 是契约违规。
  - 更严重：本条 `payload.source_record_id = WMS0000002`，而库内 `WMS0000002` = 外购转成品 **-20 件**（同 `so_no/mo_no/item/lot/ref/event_time=2025-12-23T14:05:31+08:00`）。即这是一条**改写 flow_id 后重发、且数量被改成 8** 的冲突记录。
  ```sql
  SELECT transaction_id,movement_type,signed_quantity,unit,occurred_at,reference_id
  FROM wms_transactions WHERE transaction_id='WMS0000002';   -- -20 件
  ```
- 处置：**人工复核（仓储/WMS 主数据责任人）**。数量冲突 8 vs 20 不静默覆盖；若按 -8 入库将同时造成重复记账与少计 12 件领用，直接影响该单成本与损耗率。
- 单位/时间窗口：件；2025-12-23。

## 3. ERP / BAD-ERP-ORDER —— 未知订单（人工复核，候选键已定位）

- 采集器判定：未知订单（订单号不存在）。
- 复核：`SO-NOT-EXISTS` 在 `orders`（800 单，空键 0）无匹配，`LIKE 'SO-NOT%'` 亦 0 条。
- 关键线索：除 `billNo/saleNo` 外，本条与真实工单 **MO20251221-0001 ↔ SO20251221-0001** 逐字段相同：
  ```sql
  SELECT work_order_id,sales_order_id,product_id,planned_quantity,unit,released_at,planned_finish_at,fulfillment_mode
  FROM work_orders WHERE work_order_id='MO20251221-0001';
  -- MO20251221-0001 | SO20251221-0001 | P012 | 20 | 件 | 2025-12-21T10:00 | 2026-01-08T04:00 | 外购
  ```
  且真实 ERP 源 `datahub/raw/erp/work_orders.json` 中 `billNo` 就是工单号（769 条，无重复、`saleNo` 空值 0），本条 `billNo="BAD-ERP-ORDER"` 不符合 `MO…` 规范。
- 处置：**人工复核（ERP 计划员）**——按候选键 `MO20251221-0001` 由上游确认后重发；**不自动改键**（无效关联键 → 人工复核）。

## 4. ERP / BAD-ERP-SKU —— 未知 SKU（人工复核，候选 SKU 已定位）

- 复核：`P-NOT-EXISTS` 不在 `products`（16 个 SKU）。`saleNo=SO20251221-0001` 有效，其主数据产品 = **P012 配件 / 件**，数量 20 与本条一致。
  ```sql
  SELECT product_id,product_name,unit FROM products WHERE product_id IN ('P012','P-NOT-EXISTS');  -- 仅 P012 命中
  SELECT sales_order_id,product_id,quantity,unit FROM orders WHERE sales_order_id='SO20251221-0001';
  ```
- 处置：**人工复核（销售/技术主数据）**——疑似 SKU 误填，候选 `P012`；未经确认不得改写，否则订单产品结构失真。

## 5. MES / BAD-MES-TIME —— 时间倒置（建议驳回：权威记录已在库）

- 复核：`start_ms=1764679781000` = 2025-12-02T20:49:41+08:00，`end_ms=1764679721000` = 20:48:41（比 start 早 60 秒）。
- 定位：本条与库内 **MES000001** 同源——`equipment_id=EQ03 / wc=WC02 / mo=MO20251201-00432 / duration=25.0min / kwh=4.3333` 全同，正确 `end_ms` 应为 `1764681281000`（21:14:41）。
  ```sql
  SELECT mes_event_id,start_at,end_at,duration_minutes,energy_kwh FROM mes_events
  WHERE work_order_id='MO20251201-00432' AND start_at<'2025-12-03';  -- MES000001 20:49:41→21:14:41, 25.0
  ```
- 自洽性依据：clean 源 `datahub/raw/mes/equipment_logs.jsonl` 9127 条中 `start>end` = 0、`end-start ≠ duration_sec*1000` = 0 → `duration_sec` 可信，可确定性修复 `end = start + duration_sec*1000`。
- 处置：**驳回（损坏重发）**。修复后与 MES000001 同键，仍应幂等忽略；机时/能耗不得重复计入。

## 6. OA / BAD-OA-DATE —— 无效日期（人工复核：需整单重取）

- 复核：`2026-02-30` 不是历日（2026 非闰年，2 月仅 28 天）。除日期外还有 3 处契约不符：
  - `submitted_at` 缺时分秒与时区——库内 840 条 OA 表单 `length(submitted_at)=10` 的有 **0 条**，全部为带时区 ISO8601；
  - `form_id="BAD-OA-DATE"` 不符合 `OA-REIMxxxxx` 规范；
  - 缺 `form_type / applicant_employee_id / status / form_payload`（库内 840 条这三项空值均为 0）。
- 非重复：`form_id` 不在 `oa_forms`；金额 890 与最接近的 `OA-REIM00656`（890.05 元，2026-02-21，已支付）**不等**。
  ```sql
  SELECT form_id,submitted_at,status,form_payload FROM oa_forms WHERE form_payload LIKE '%890%';
  ```
- 处置：**人工复核（财务/OA 管理员）**——意图日期歧义（02-28 / 03-01 皆可能），不猜日期；由 OA 按 `form_id` 重取全字段。报销笔数与金额类简报在补齐前不计入本条。

## 7. ERP / BAD-ERP-MISSING —— 缺业务键（建议驳回：无任何有效关联键）

- 复核：`saleNo` 为空，`billNo="BAD-ERP-MISSING"` 既不在 `orders`/`work_orders`，也不符合真实源 `billNo=MO…` 规范（`LIKE '%BAD-ERP%'` 在 orders 命中 0）。
- 与第 3 条的区别：第 3 条至少 `billNo` 位置有值且其余字段能对齐到唯一工单；本条 `billNo` 与 `saleNo` **双双失效**，只剩 `sku=P012 + qty=20 + 时间`，而 P012 关联订单不止一单可能——按属性猜单会造成错误归属。
- 处置：**驳回 + 要求 ERP 重发带 `billNo/saleNo` 的版本**；不得凭 sku+时间反推订单。

## 8. WMS / BAD-WMS-UNIT —— 单位冲突（人工复核：禁止按公斤入库）

- 复核：`uom=公斤` 不在系统单位域。库内 `wms_transactions` 单位分布仅 **件 635 / 台 984 / 套 3752 / 批 47**（合计 5418，与源流条数一致，无"公斤"）；物料主数据 `M004 外购物料套包` 单位 = **件**。
- 同时是"改写 flow_id 的重复"：除 `uom` 外，与 `WMS0000001` 的 `so_no/mo_no/item/lot/direction=IN/biz_type=采购入库/qty=20/unit_price=14.4089/event_time=2025-12-23T06:05:31+08:00/ref` **逐字段相同**，且 `payload.source_record_id=WMS0000001`。
  ```sql
  SELECT material_id,material_name,unit FROM materials WHERE material_id='M004';   -- 件
  SELECT unit,COUNT(*) FROM wms_transactions GROUP BY unit;                        -- 无公斤
  ```
- 处置：**人工复核（仓储 + 物料主数据）**。公斤↔件无经批准的换算系数（跨产品折算只允许用"标准工时产出"，质量单位不适用），故**不得折算入库**；若确为同一笔，按重复忽略；若确为另一笔公斤计量流水，需上游补主数据后再采。

## 9. MES / BAD-MES-FUTURE —— 未来实际事件（建议驳回：不可能是实际事件）

- 复核：`start_ms=1789776000000` = 2026-09-19T08:00:00+08:00，晚于快照 2026-09-18T08:00 整 24 小时；clean 源 9127 条中快照后事件 = **0 条**，库内 `mes_events` 快照后 = **0 条**。
- 双重不符：`end-start = 3600s` 与 `duration_sec = 1500` 矛盾（clean 源该矛盾为 0）。
- 业务上不可能：工单 `MO20251201-00432` 计划完工 2025-12-28T07:00，最后实际机加事件 2025-12-20T09:57:33，成品入库 2026-01-02（+5 台），销售出库 2026-01-03，**2026-01-06 全量签收（status=已签收，5 台）**——订单已按"全量签收"口径完成。
  ```sql
  SELECT shipment_id,quantity,unit,dispatched_at,received_at,status FROM shipments WHERE sales_order_id='SO20251201-00432';
  SELECT MAX(end_at) FROM mes_events WHERE work_order_id='MO20251201-00432';   -- 2025-12-20T09:57:33+08:00
  ```
- 处置：**驳回，不进入任何实际指标**（未来事件不得当作实际发生）。转 MES 责任人排查：疑似测试数据或机台时钟/时区漂移；若属时钟问题，需回查该 EQ03 同期其他事件。

---

## 处置汇总

| 处置 | 条数 | 记录 |
|---|---|---|
| 幂等忽略（维持，无需动作） | 1 | WMS0000001 |
| 驳回（权威记录已在库 / 不可能是实际事件） | 2 | BAD-MES-TIME、BAD-MES-FUTURE |
| 人工复核——数量/单位冲突 | 2 | BAD-WMS-NEG、BAD-WMS-UNIT |
| 人工复核——关联键/主数据失效，需上游重发 | 3 | BAD-ERP-ORDER、BAD-ERP-SKU、BAD-ERP-MISSING |
| 人工复核——字段契约不全，需整单重取 | 1 | BAD-OA-DATE |
| 可确定性自动修复 | 1 | BAD-MES-TIME（`end=start+duration_sec`），但修复后仍应幂等忽略 |

## 采集规则改进（防复发，5 条）

1. **R1 去重键补全（最高优先）**：WMS 去重不能只看 `flow_id`。须同时校验 `payload.source_record_id` 与业务指纹 `(so_no,mo_no,item,lot,event_time,qty,uom)`；`flow_id` 被改写而指纹命中 → 判为"冲突重发"，隔离 + 人工复核，**永不覆盖已入库值**。本次 BAD-WMS-NEG、BAD-WMS-UNIT 正是靠此规则才定性（现逻辑漏判为全新记录）。
2. **R2 符号契约**：WMS `qty ≥ 0`，符号由 `direction` 决定（IN 正 / OUT 负）；出现负值即契约违规并触发指纹查重。
3. **R3 时间自洽 + 快照闸门**：MES 校验 `start ≤ end ≤ 快照` 且 `end-start = duration_sec*1000`；可修复的标 `repairable`，入库前仍须按 `mes_event_id` 与既有事件比对，命中即忽略。
4. **R4 键与主数据校验**：ERP 要求 `saleNo ∈ orders`、`sku ∈ products`、`billNo` 匹配 `^MO\d{8}-\d{5}$`；任一无效 → 人工复核清单，禁止按属性猜键。
5. **R5 单位与日期域校验**：`uom ∈ {台,套,件,批}`，跨单位只用"标准工时产出"折算；日期必须为带时区 ISO8601 且为真实历日，`form_id` 匹配 `^OA-[A-Z]{2,6}\d{5}$`。

## 待人工回填（复核清单需上游确认的 4 个问题）

1. WMS：`WMS0000002` 外购转成品实际是 20 件还是 8 件？（影响 SO20251221-0001 成本/损耗率）
2. WMS：`M004` 是否存在公斤计量的另一笔入库？若有，换算系数由谁维护？
3. ERP：`BAD-ERP-ORDER`/`BAD-ERP-MISSING` 的原始工单号与销售订单号是什么？是否即 `MO20251221-0001 / SO20251221-0001`？
4. OA：`BAD-OA-DATE` 的真实提交日期与申请人？（金额 890 元整，非 890.05）

> 本单由自动化流程处理：全程只读 `agent_data.sqlite`，未写库、未回写企业系统。
