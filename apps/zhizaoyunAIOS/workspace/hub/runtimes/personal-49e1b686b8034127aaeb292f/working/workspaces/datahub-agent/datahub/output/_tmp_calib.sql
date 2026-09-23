-- 经验校准曲线：用已完成(全量签收)订单，看"预测P50签收日 vs 承诺日"的缓冲天数 与 实际是否迟签收 的关系
WITH snap AS (SELECT julianday('2026-09-18T08:00:00+08:00') t),
slip0 AS (
  SELECT sn.stage_code, o.fulfillment_mode,
         julianday(sn.actual_end_at)-julianday(sn.planned_end_at) d,
         ROW_NUMBER() OVER (PARTITION BY sn.stage_code,o.fulfillment_mode ORDER BY julianday(sn.actual_end_at)-julianday(sn.planned_end_at)) rn,
         COUNT(*)    OVER (PARTITION BY sn.stage_code,o.fulfillment_mode) n
  FROM stage_nodes sn JOIN orders o ON o.sales_order_id=sn.sales_order_id
  WHERE sn.actual_end_at IS NOT NULL AND o.is_effective=1),
slip_p AS (SELECT stage_code, fulfillment_mode, MAX(n) n,
            MAX(CASE WHEN rn=CAST(n*0.5 AS INT)+1 THEN d END) p50,
            MAX(CASE WHEN rn=CAST(n*0.9 AS INT)+1 THEN d END) p90 FROM slip0 GROUP BY 1,2),
tr0 AS (SELECT route_id, julianday(received_at)-julianday(dispatched_at) d,
        ROW_NUMBER() OVER (PARTITION BY route_id ORDER BY julianday(received_at)-julianday(dispatched_at)) rn,
        COUNT(*) OVER (PARTITION BY route_id) n FROM shipments WHERE received_at IS NOT NULL),
tr_p AS (SELECT route_id, MAX(n) n, MAX(CASE WHEN rn=CAST(n*0.5 AS INT)+1 THEN d END) p50,
         MAX(CASE WHEN rn=CAST(n*0.9 AS INT)+1 THEN d END) p90 FROM tr0 GROUP BY 1),
ship AS (SELECT sales_order_id, MAX(planned_end_at) ship_planned_end FROM stage_nodes WHERE stage_code='SHIP' GROUP BY 1),
lastrecv AS (SELECT sales_order_id, MAX(received_at) last_recv FROM shipments GROUP BY 1),
q AS (
  SELECT o.sales_order_id, o.fulfillment_mode, o.route_id, o.promised_delivery_at,
         lr.last_recv, sh.ship_planned_end,
         julianday(sh.ship_planned_end) + IFNULL(sp.p50,1.5) + IFNULL(tp.p50,5) AS pred_p50,
         julianday(sh.ship_planned_end) + IFNULL(sp.p90,6.0) + IFNULL(tp.p90,23) AS pred_p90
  FROM orders o
  JOIN ship sh ON sh.sales_order_id=o.sales_order_id
  JOIN lastrecv lr ON lr.sales_order_id=o.sales_order_id
  LEFT JOIN slip_p sp ON sp.stage_code='SHIP' AND sp.fulfillment_mode=o.fulfillment_mode
  LEFT JOIN tr_p tp ON tp.route_id=o.route_id
  WHERE o.is_effective=1 AND lr.last_recv IS NOT NULL
    AND sh.ship_planned_end IS NOT NULL
    AND (SELECT SUM(quantity) FROM shipments s WHERE s.sales_order_id=o.sales_order_id AND s.received_at IS NOT NULL) >= o.quantity)
SELECT CASE WHEN julianday(promised_delivery_at)-pred_p50 < -7 THEN 'a.<-7'
            WHEN julianday(promised_delivery_at)-pred_p50 < -3 THEN 'b.-7~-3'
            WHEN julianday(promised_delivery_at)-pred_p50 < 0  THEN 'c.-3~0'
            WHEN julianday(promised_delivery_at)-pred_p50 < 3  THEN 'd.0~3'
            WHEN julianday(promised_delivery_at)-pred_p50 < 7  THEN 'e.3~7'
            WHEN julianday(promised_delivery_at)-pred_p50 < 14 THEN 'f.7~14'
            WHEN julianday(promised_delivery_at)-pred_p50 < 30 THEN 'g.14~30'
            ELSE 'h.>=30' END AS buffer_bucket,
       COUNT(*) n,
       SUM(CASE WHEN julianday(last_recv) > julianday(promised_delivery_at) THEN 1 ELSE 0 END) late_n,
       ROUND(1.0*SUM(CASE WHEN julianday(last_recv) > julianday(promised_delivery_at) THEN 1 ELSE 0 END)/COUNT(*),3) late_rate,
       ROUND(AVG(julianday(last_recv)-julianday(pred_p50)),1) avg_err_p50,
       ROUND(AVG(julianday(last_recv)-julianday(pred_p90)),1) avg_err_p90,
       ROUND(1.0*SUM(CASE WHEN julianday(last_recv)<=julianday(pred_p90) THEN 1 ELSE 0 END)/COUNT(*),3) p90_cover
FROM q GROUP BY 1 ORDER BY 1;
