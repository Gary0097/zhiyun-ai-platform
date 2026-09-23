WITH d AS (
  SELECT route_id,
         julianday(received_at)-julianday(dispatched_at) AS dd,
         ROW_NUMBER() OVER (PARTITION BY route_id ORDER BY julianday(received_at)-julianday(dispatched_at)) AS rn,
         COUNT(*)    OVER (PARTITION BY route_id) AS n
  FROM shipments
  WHERE received_at IS NOT NULL
),
rs AS (
  SELECT route_id, MAX(n) AS n,
         MAX(CASE WHEN rn = CAST(n*0.5 AS INT)+1 THEN dd END) AS p50,
         MAX(CASE WHEN rn = CAST(n*0.9 AS INT)+1 THEN dd END) AS p90
  FROM d GROUP BY route_id
),
last_ev AS (
  SELECT shipment_id, MAX(event_at) AS last_event_at,
         (SELECT event_status FROM logistics_events e WHERE e.shipment_id = l.shipment_id
           ORDER BY e.event_at DESC LIMIT 1) AS last_status
  FROM logistics_events l GROUP BY shipment_id
),
exc AS (
  SELECT sales_order_id,
         SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) AS open_exc,
         SUM(CASE WHEN severity IN ('高','critical','high') THEN 1 ELSE 0 END) AS hi_exc
  FROM exceptions GROUP BY sales_order_id
),
recv AS (
  SELECT sales_order_id, SUM(quantity) AS signed_qty FROM shipments
  WHERE received_at IS NOT NULL GROUP BY sales_order_id
),
disp AS (
  SELECT sales_order_id, SUM(quantity) AS disp_qty FROM shipments GROUP BY sales_order_id
)
SELECT s.shipment_id, s.sales_order_id, c.customer_name, o.unit, o.quantity AS order_qty,
       dp.disp_qty, IFNULL(rv.signed_qty,0) AS signed_qty,
       s.route_id, rt.route_name, rt.transport_mode, rt.baseline_transit_days,
       rs.n AS transit_sample_n, rs.p50, rs.p90,
       s.dispatched_at, s.carrier_promised_at, o.promised_delivery_at,
       ROUND(julianday('2026-09-18T08:00:00+08:00') - julianday(s.dispatched_at), 1) AS days_since_dispatch,
       ROUND(julianday(o.promised_delivery_at) - julianday('2026-09-18T08:00:00+08:00'), 1) AS days_to_promise,
       IFNULL(le.last_event_at, '(无事件)') AS last_event_at, IFNULL(le.last_status,'-') AS last_status,
       IFNULL(ex.open_exc,0) AS open_exc, IFNULL(ex.hi_exc,0) AS hi_exc
FROM shipments s
JOIN orders o            ON o.sales_order_id = s.sales_order_id
LEFT JOIN customers c    ON c.customer_id = o.customer_id
LEFT JOIN routes rt      ON rt.route_id = s.route_id
LEFT JOIN rs             ON rs.route_id = s.route_id
LEFT JOIN last_ev le     ON le.shipment_id = s.shipment_id
LEFT JOIN exc ex         ON ex.sales_order_id = s.sales_order_id
LEFT JOIN disp dp        ON dp.sales_order_id = s.sales_order_id
LEFT JOIN recv rv        ON rv.sales_order_id = s.sales_order_id
WHERE s.received_at IS NULL
ORDER BY days_to_promise;
