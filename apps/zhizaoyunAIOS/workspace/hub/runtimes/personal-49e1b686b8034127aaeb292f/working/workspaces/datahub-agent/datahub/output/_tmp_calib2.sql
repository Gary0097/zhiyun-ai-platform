WITH tr0 AS (SELECT route_id, julianday(received_at)-julianday(dispatched_at) d,
             ROW_NUMBER() OVER (PARTITION BY route_id ORDER BY julianday(received_at)-julianday(dispatched_at)) rn,
             COUNT(*) OVER (PARTITION BY route_id) n FROM shipments WHERE received_at IS NOT NULL),
tr_p AS (SELECT route_id, MAX(n) n, MAX(CASE WHEN rn=CAST(n*0.5 AS INT)+1 THEN d END) p50,
                MAX(CASE WHEN rn=CAST(n*0.9 AS INT)+1 THEN d END) p90 FROM tr0 GROUP BY route_id),
b AS (
  SELECT s.shipment_id, s.route_id, s.dispatched_at, s.carrier_promised_at, o.promised_delivery_at, s.received_at,
         julianday(s.dispatched_at) + IFNULL(tp.p50,5) pred_p50,
         julianday(s.dispatched_at) + IFNULL(tp.p90,23) pred_p90,
         julianday(o.promised_delivery_at) prom,
         (SELECT COUNT(*) FROM logistics_events e WHERE e.shipment_id=s.shipment_id AND e.event_status='运输延误') delay_ev
  FROM shipments s JOIN orders o ON o.sales_order_id=s.sales_order_id
  LEFT JOIN tr_p tp ON tp.route_id=s.route_id
  WHERE s.received_at IS NOT NULL)
SELECT CASE WHEN prom-pred_p50 < -5 THEN 'a.<-5'
            WHEN prom-pred_p50 < -2 THEN 'b.-5~-2'
            WHEN prom-pred_p50 < 0  THEN 'c.-2~0'
            WHEN prom-pred_p50 < 2  THEN 'd.0~2'
            WHEN prom-pred_p50 < 5  THEN 'e.2~5'
            WHEN prom-pred_p50 < 10 THEN 'f.5~10'
            ELSE 'g.>=10' END bucket,
       COUNT(*) n,
       SUM(CASE WHEN julianday(received_at)>prom THEN 1 ELSE 0 END) late_n,
       ROUND(1.0*SUM(CASE WHEN julianday(received_at)>prom THEN 1 ELSE 0 END)/COUNT(*),3) late_rate,
       SUM(CASE WHEN delay_ev>0 THEN 1 ELSE 0 END) with_delay_ev,
       ROUND(1.0*SUM(CASE WHEN julianday(received_at)>prom AND delay_ev>0 THEN 1 ELSE 0 END)/NULLIF(SUM(CASE WHEN delay_ev>0 THEN 1 ELSE 0 END),0),3) late_rate_if_delay,
       ROUND(1.0*SUM(CASE WHEN julianday(received_at)<=pred_p90 THEN 1 ELSE 0 END)/COUNT(*),3) cover_p90
FROM b GROUP BY 1 ORDER BY 1;
