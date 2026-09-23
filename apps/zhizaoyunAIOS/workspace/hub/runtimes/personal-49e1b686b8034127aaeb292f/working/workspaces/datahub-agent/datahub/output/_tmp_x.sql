WITH tr0 AS (SELECT route_id, julianday(received_at)-julianday(dispatched_at) d,
             ROW_NUMBER() OVER (PARTITION BY route_id ORDER BY julianday(received_at)-julianday(dispatched_at)) rn,
             COUNT(*) OVER (PARTITION BY route_id) n FROM shipments WHERE received_at IS NOT NULL),
tr_p AS (SELECT route_id, MAX(n) n, MAX(CASE WHEN rn=CAST(n*0.5 AS INT)+1 THEN d END) p50 FROM tr0 GROUP BY route_id),
b AS (
  SELECT s.shipment_id, s.route_id, s.received_at,
         julianday(o.promised_delivery_at) - (julianday(s.dispatched_at) + IFNULL(tp.p50,5)) AS buf,
         (SELECT COUNT(*) FROM logistics_events e WHERE e.shipment_id=s.shipment_id AND e.event_status='运输延误')>0 AS dly
  FROM shipments s JOIN orders o ON o.sales_order_id=s.sales_order_id
  LEFT JOIN tr_p tp ON tp.route_id=s.route_id
  WHERE s.received_at IS NOT NULL)
SELECT CASE WHEN buf<-5 THEN 'a.<-5' WHEN buf<-2 THEN 'b.-5~-2' WHEN buf<0 THEN 'c.-2~0'
            WHEN buf<2 THEN 'd.0~2' WHEN buf<5 THEN 'e.2~5' WHEN buf<10 THEN 'f.5~10' ELSE 'g.>=10' END bucket,
       dly, COUNT(*) n,
       ROUND(1.0*SUM(CASE WHEN julianday(received_at) > julianday('2099-01-01') THEN 0 ELSE 0 END),3) x,
       ROUND(1.0*SUM(CASE WHEN julianday(received_at) > (SELECT 1) THEN 1 ELSE 0 END),3) dummy
FROM b GROUP BY 1,2 ORDER BY 1,2;
