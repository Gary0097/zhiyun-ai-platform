WITH lastrecv AS (
  SELECT sales_order_id, MAX(received_at) last_recv,
         SUM(CASE WHEN received_at IS NOT NULL THEN quantity ELSE 0 END) signed_qty
  FROM shipments GROUP BY sales_order_id),
ship AS (SELECT sales_order_id, MAX(planned_end_at) ship_planned_end FROM stage_nodes WHERE stage_code='SHIP' GROUP BY 1),
tr0 AS (SELECT route_id, julianday(received_at)-julianday(dispatched_at) d,
        ROW_NUMBER() OVER (PARTITION BY route_id ORDER BY julianday(received_at)-julianday(dispatched_at)) rn,
        COUNT(*) OVER (PARTITION BY route_id) n FROM shipments WHERE received_at IS NOT NULL),
tr_p AS (SELECT route_id, MAX(n) n, MAX(CASE WHEN rn=CAST(n*0.5 AS INT)+1 THEN d END) p50 FROM tr0 GROUP BY route_id),
res0 AS (
  SELECT o.route_id, julianday(lr.last_recv)-julianday(sh.ship_planned_end) d,
         ROW_NUMBER() OVER (PARTITION BY o.route_id ORDER BY julianday(lr.last_recv)-julianday(sh.ship_planned_end)) rn,
         COUNT(*)    OVER (PARTITION BY o.route_id) n
  FROM orders o JOIN lastrecv lr ON lr.sales_order_id=o.sales_order_id
                JOIN ship sh ON sh.sales_order_id=o.sales_order_id
  WHERE o.is_effective=1 AND lr.last_recv IS NOT NULL AND sh.ship_planned_end IS NOT NULL AND lr.signed_qty>=o.quantity),
res_p AS (SELECT route_id, MAX(n) n, MAX(CASE WHEN rn=CAST(n*0.5 AS INT)+1 THEN d END) p50,
          MAX(CASE WHEN rn=CAST(n*0.9 AS INT)+1 THEN d END) p90 FROM res0 GROUP BY route_id),
base AS (
  SELECT o.sales_order_id, o.promised_delivery_at, lr.last_recv,
         julianday(sh.ship_planned_end) + IFNULL(rp.p50, 7.0) AS pred_p50,
         julianday(sh.ship_planned_end) + IFNULL(rp.p90, 26.0) AS pred_p90,
         julianday(o.promised_delivery_at) AS prom
  FROM orders o
  JOIN lastrecv lr ON lr.sales_order_id=o.sales_order_id
  JOIN ship sh ON sh.sales_order_id=o.sales_order_id
  LEFT JOIN res_p rp ON rp.route_id=o.route_id
  WHERE o.is_effective=1 AND lr.last_recv IS NOT NULL AND sh.ship_planned_end IS NOT NULL AND lr.signed_qty>=o.quantity)
SELECT CASE WHEN prom-pred_p50 < -10 THEN 'a.<-10'
            WHEN prom-pred_p50 < -5  THEN 'b.-10~-5'
            WHEN prom-pred_p50 < -2  THEN 'c.-5~-2'
            WHEN prom-pred_p50 < 0   THEN 'd.-2~0'
            WHEN prom-pred_p50 < 2   THEN 'e.0~2'
            WHEN prom-pred_p50 < 5   THEN 'f.2~5'
            WHEN prom-pred_p50 < 10  THEN 'g.5~10'
            WHEN prom-pred_p50 < 20  THEN 'h.10~20'
            ELSE 'i.>=20' END bucket,
       COUNT(*) n,
       SUM(CASE WHEN julianday(last_recv)>prom THEN 1 ELSE 0 END) late_n,
       ROUND(1.0*SUM(CASE WHEN julianday(last_recv)>prom THEN 1 ELSE 0 END)/COUNT(*),3) late_rate,
       ROUND(1.0*SUM(CASE WHEN julianday(last_recv)<=pred_p90 THEN 1 ELSE 0 END)/COUNT(*),3) cover_p90
FROM base GROUP BY 1 ORDER BY 1;
