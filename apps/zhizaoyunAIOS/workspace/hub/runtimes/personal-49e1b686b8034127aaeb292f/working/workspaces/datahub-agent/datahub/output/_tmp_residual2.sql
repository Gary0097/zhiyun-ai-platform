WITH lastrecv AS (
  SELECT sales_order_id, MAX(received_at) last_recv, SUM(CASE WHEN received_at IS NOT NULL THEN quantity ELSE 0 END) signed_qty
  FROM shipments GROUP BY sales_order_id),
ship AS (SELECT sales_order_id, MAX(planned_end_at) ship_planned_end FROM stage_nodes WHERE stage_code='SHIP' GROUP BY 1),
r AS (
  SELECT o.fulfillment_mode, o.route_id,
         julianday(lr.last_recv) - julianday(sh.ship_planned_end) AS d,
         ROW_NUMBER() OVER (PARTITION BY o.fulfillment_mode ORDER BY julianday(lr.last_recv)-julianday(sh.ship_planned_end)) rn_m,
         COUNT(*)    OVER (PARTITION BY o.fulfillment_mode) n_m,
         ROW_NUMBER() OVER (PARTITION BY o.route_id ORDER BY julianday(lr.last_recv)-julianday(sh.ship_planned_end)) rn_r,
         COUNT(*)    OVER (PARTITION BY o.route_id) n_r
  FROM orders o
  JOIN lastrecv lr ON lr.sales_order_id=o.sales_order_id
  JOIN ship sh     ON sh.sales_order_id=o.sales_order_id
  WHERE o.is_effective=1 AND lr.last_recv IS NOT NULL AND sh.ship_planned_end IS NOT NULL AND lr.signed_qty>=o.quantity)
SELECT 'BY_MODE' k, fulfillment_mode g, MAX(n_m) n,
       ROUND(AVG(d),1) mean, ROUND(MAX(CASE WHEN rn_m=CAST(n_m*0.5 AS INT)+1 THEN d END),1) p50,
       ROUND(MAX(CASE WHEN rn_m=CAST(n_m*0.9 AS INT)+1 THEN d END),1) p90,
       ROUND(MAX(CASE WHEN rn_m=n_m THEN d END),1) max_d
FROM r GROUP BY fulfillment_mode
UNION ALL
SELECT 'BY_ROUTE', route_id, MAX(n_r),
       ROUND(AVG(d),1), ROUND(MAX(CASE WHEN rn_r=CAST(n_r*0.5 AS INT)+1 THEN d END),1),
       ROUND(MAX(CASE WHEN rn_r=CAST(n_r*0.9 AS INT)+1 THEN d END),1),
       ROUND(MAX(CASE WHEN rn_r=n_r THEN d END),1)
FROM r GROUP BY route_id ORDER BY k, n;
