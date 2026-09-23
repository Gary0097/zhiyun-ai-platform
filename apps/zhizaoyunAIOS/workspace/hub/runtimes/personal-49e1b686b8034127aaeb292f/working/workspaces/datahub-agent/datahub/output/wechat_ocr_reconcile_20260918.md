# 微信截图 × ERP 订单核对报告

- 快照时间：2026-09-18 08:00（北京时间，取自 `configuration.snapshot_at`）
- 样本范围：`datahub/raw/wechat/CHAT_001.png` ~ `CHAT_012.png`（12 张，1080×1080 PNG）
- 登记台账：`source_documents` DOC001–DOC012，`ingestion_status` 原值均为「待识别」
- 核对方式：图片视觉识别（直读，非 OCR 库）→ 与 `orders` + `customers` + `products` + `work_orders` + `shipments` 逐字段比对
- 数据源声明：截图页眉标注「WB｜非真实微信聊天记录｜禁止用于业务凭证」，本报告仅作识别与核对演练，不作为业务凭证，不写回企业系统

## 一、结论先行

1. **12/12 订单号在 ERP 精确命中，无一缺失、无一重复。** 800 张有效订单中 `sales_order_id` 唯一（COUNT=800，DISTINCT=800），每单对应 1 条订单行 + 1 张工单（MO…），客户名、设备名、单位 12/12 全对。截图要求「不要重复新建」已满足——**不需要新建任何订单**。
2. **8 张完全一致**：DOC001–DOC008（订单号 00671 / 00254 / 00709 / 00258 / 00591 / 00470 / 0210 / 0208）四要素（客户、设备、数量+单位、交期）与 ERP 逐字段相符。
3. **2 处数量冲突（进人工复核，不静默覆盖）**：DOC009、DOC010 截图均为「3」，ERP 均为「2」。已放大像素复核确认非误读；且 ERP 侧 `orders.quantity` 与 `work_orders.planned_quantity` 同为 2，即 ERP 内部自洽，截图是离群值。
4. **2 处交期模糊（进人工复核）**：DOC011、DOC012 截图交期写作「月底前，具体日期再确认」，未指明年月，无法与 ERP 具体日期判定一致或冲突。若按快照月理解为 2026-09-30 前，则 ERP 承诺日（10-19、10-04）均晚于客户期望，属交付风险信号——但此为推定，须客户确认。
5. **12 单全部未发货**：`shipments` 命中数均为 0，无签收记录，全部为在途未交付订单，因此数量/交期差异仍可在生产前修正。
6. **4 单 ERP 已带来源风险标记**（与截图核对结果相互独立）：00573「客户配置变更」、0208「客户变更配置」、0204「交付条款偏紧」、0210「交付条款偏紧」。其中 00573 同时是本批数量冲突单，两条线索指向同一单，建议优先复核。
7. **3 单 ERP 内部排产晚于承诺交期**（截图核对之外的问题）：00691 承诺 10-04／计划完工 10-11（晚 7 天）、00258 承诺 10-07／完工 10-12（晚 5 天）、00709 承诺 10-07／完工 10-13（晚 6 天）。后两单的截图与 ERP 四要素是**完全一致**的，风险出在 ERP 自身的排产与承诺不匹配，且 `delivery_basis` 为全量签收、尚无发货记录，需生产侧确认能否压缩或与客户改期。

## 二、逐张核对明细

图列为识别用文件名；ERP 交期取 `promised_delivery_at` 日期部分（原值含 18:00:00+08:00 时刻）。

| 图 | DOC | 订单号 | 客户（截图 → ERP） | 设备（截图 → ERP） | 数量·单位（截图 → ERP） | 交期（截图 → ERP） | 判定 |
|---|---|---|---|---|---|---|---|
| CHAT_001 | DOC001 | SO20260917-00671 | Simon Co.,Ltd. ✓ | 600六列背封螺杆包装机 ✓ | 1台 ✓ | 2026-10-17 ✓ | 一致 |
| CHAT_002 | DOC002 | SO20260917-00254 | KV Nutrition Trading ✓ | 高速圆角背封宠物膏体包装机 ✓ | 1台 ✓ | 2026-11-16 ✓ | 一致 |
| CHAT_003 | DOC003 | SO20260917-00709 | 广东润泽新禾电子材料有限公司 ✓ | 600六列背封螺杆包装机 ✓ | 3台 ✓ | 2026-10-07 ✓ | 一致 |
| CHAT_004 | DOC004 | SO20260917-00258 | YAM AGRO S.A. ✓ | 高速圆角背封宠物膏体包装机 ✓ | 3台 ✓ | 2026-10-07 ✓ | 一致 |
| CHAT_005 | DOC005 | SO20260915-00591 | 湖南锦华锦华电子材料有限公司 ✓ | 配件采购单 ✓ | 5件 ✓ | 2026-11-14 ✓ | 一致 |
| CHAT_006 | DOC006 | SO20260915-00470 | 安徽鸿辰金瑞精细化工有限公司 ✓ | 自动灌装旋盖装盒线 ✓ | 5套 ✓ | 2026-11-29 ✓ | 一致 |
| CHAT_007 | DOC007 | SO20260915-0210 | YAM AGRO S.A. ✓ | 配件 ✓ | 8件 ✓ | 2026-10-30 ✓ | 一致 |
| CHAT_008 | DOC008 | SO20260914-0208 | 广东瑞丰盛泽生物科技有限公司 ✓ | 240螺杆包装机 ✓ | 1台 ✓ | 2026-11-13 ✓ | 一致（ERP另有风险标记） |
| CHAT_009 | DOC009 | SO20260914-0198 | 湖南泰启优谷食品有限公司 ✓ | 双列背封颗粒/粉末包装机 ✓ | **3台 → 2台 ✗** | 2026-11-13 ✓ | **数量冲突** |
| CHAT_010 | DOC010 | SO20260914-00573 | 广东金瑞康宁精细化工有限公司 ✓ | 配件采购单 ✓ | **3件 → 2件 ✗** | 2026-10-29 ✓ | **数量冲突**（ERP另有风险标记） |
| CHAT_011 | DOC011 | SO20260914-0204 | 浙江海誉康宁包装材料有限公司 ✓ | 电子辅料点数包装机 ✓ | 2件 ✓ | **月底前，具体日期再确认 → 2026-10-19** | **交期模糊**（ERP另有风险标记） |
| CHAT_012 | DOC012 | SO20260914-00691 | 河南华盛康莱生物科技有限公司 ✓ | 圆角磁力泵包装机 ✓ | 5台 ✓ | **月底前，具体日期再确认 → 2026-10-04** | **交期模糊** |

## 三、人工复核清单（4 条）

| 序 | 订单号 / 工单号 | 复核项 | 截图值 | ERP 值 | 证据 | 建议动作 |
|---|---|---|---|---|---|---|
| R1 | SO20260914-0198 / MO20260914-0198 | 数量 | 3台 | 2台（orders 与 work_orders 一致） | CHAT_009.png 放大复核「数量：3台」 | 向客户/销售确认是否追加 1 台；未确认前不改库 |
| R2 | SO20260914-00573 / MO20260914-00573 | 数量 | 3件 | 2件（orders 与 work_orders 一致） | CHAT_010.png 放大复核「数量：3件」 | 该单 ERP 已标「客户配置变更」，与数量差异同向，优先核实 |
| R3 | SO20260914-0204 / MO20260914-0204 | 交期 | 「月底前」（未指明年月） | 2026-10-19 | CHAT_011.png | 请客户给出确定日期；ERP 已标「交付条款偏紧」 |
| R4 | SO20260914-00691 / MO20260914-00691 | 交期 | 「月底前」（未指明年月） | 2026-10-04 | CHAT_012.png | 请客户给出确定日期；计划完工 2026-10-11 晚于承诺交期，需排产确认 |

补充观察（非冲突）：同客户同产品存在多张在效订单，均非重复单，但建议销售侧确认是否可并单——
C0182×P012：SO20260915-0210（8件，10-30）与 SO20260901-0217（5件，10-11）；
C0161×P013：SO20260915-00591（5件，11-14）与 SO20260218-00542（5件，04-04）；
C0025×P007：SO20260914-00691（5台，10-04）与 SO20260709-00317（2台，09-22）。

### 三之二、ERP 内部排产风险（截图核对一致，但承诺与完工不匹配）

| 订单号 / 工单号 | 承诺交期 | 计划完工 | 差 | 截图核对结果 | 建议 |
|---|---|---|---|---|---|
| SO20260914-00691 / MO20260914-00691 | 2026-10-04 | 2026-10-11 | 晚 7 天 | 交期模糊（R4） | 先定交期，再重排产 |
| SO20260917-00258 / MO20260917-00258 | 2026-10-07 | 2026-10-12 | 晚 5 天 | 四要素一致 | 生产压缩或与客户改期 |
| SO20260917-00709 / MO20260917-00709 | 2026-10-07 | 2026-10-13 | 晚 6 天 | 四要素一致 | 生产压缩或与客户改期 |

三单 `shipments` 命中均为 0，尚未发货，交期仍可协商。

## 四、原始证据（SQL）

```sql
-- 1) 12 单命中与主数据比对
SELECT o.sales_order_id, o.customer_id, c.customer_name, o.product_id, p.product_name,
       p.unit AS prod_unit, o.packaged_goods, o.quantity AS erp_qty, o.unit AS erp_unit,
       substr(o.promised_delivery_at,1,10) AS erp_date
FROM orders o
LEFT JOIN customers c ON c.customer_id = o.customer_id
LEFT JOIN products  p ON p.product_id  = o.product_id
WHERE o.sales_order_id IN ('SO20260917-00671','SO20260917-00254','SO20260917-00709',
  'SO20260917-00258','SO20260915-00591','SO20260915-00470','SO20260915-0210',
  'SO20260914-0208','SO20260914-0198','SO20260914-00573','SO20260914-0204','SO20260914-00691');
-- 返回 12 行

-- 2) 唯一性 / 重复新建风险
SELECT COUNT(*) n, COUNT(DISTINCT sales_order_id) d FROM orders;   -- 800 | 800

-- 3) 工单与发货状态
SELECT o.sales_order_id, w.work_order_id, w.planned_quantity, w.unit,
       substr(w.released_at,1,10) released, substr(w.planned_finish_at,1,10) plan_finish,
       (SELECT COUNT(*) FROM shipments s WHERE s.sales_order_id=o.sales_order_id) n_ship
FROM orders o LEFT JOIN work_orders w ON w.sales_order_id=o.sales_order_id
WHERE o.sales_order_id IN (…上述 12 单…);
-- 12 行，n_ship 全为 0

-- 4) 来源风险标记
SELECT sales_order_id, order_source, source_risk_flag, source_risk_reason
FROM orders WHERE source_risk_flag='是' AND sales_order_id IN (…上述 12 单…);
-- 00573 客户配置变更 / 0204 交付条款偏紧 / 0208 客户变更配置 / 0210 交付条款偏紧

-- 5) 图片登记台账
SELECT document_id, sales_order_id, source_system, file_path, ingestion_status
FROM source_documents ORDER BY document_id;   -- DOC001-012，全部「待识别」

-- 6) ERP 内部排产 vs 承诺交期
SELECT o.sales_order_id, substr(o.promised_delivery_at,1,10) promised,
       substr(w.planned_finish_at,1,10) plan_finish
FROM orders o JOIN work_orders w ON w.sales_order_id = o.sales_order_id
WHERE o.sales_order_id IN (…上述 12 单…)
  AND date(substr(w.planned_finish_at,1,10)) > date(substr(o.promised_delivery_at,1,10));
-- 00691: 2026-10-04 / 2026-10-11 ; 00258: 2026-10-07 / 2026-10-12 ; 00709: 2026-10-07 / 2026-10-13
```

口径依据：`delivery_basis` 12 单均为「全量签收」，分批发货不计完成；台/套/件不跨单位折算。

## 五、未执行的动作

- 未修改 `source_documents.ingestion_status`（计算副本只读，`query.py` 以 mode=ro 打开）。如需把 8 张一致单标为「已核对」、4 张标为「人工复核中」，请在可写通道执行或授权导出后回传。
- 未向任何群组推送。若需推送本结论到管理层群，走 Mock 接口 `POST http://127.0.0.1:18765/api/mock/wechat/push`（`recipient_group=WB_MANAGEMENT`，带 `idempotency_key`）。
