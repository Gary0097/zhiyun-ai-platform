WITH s AS (
  SELECT sales_order_id,
         SUM(CASE WHEN received_at IS NOT NULL AND received_at<>'' THEN quantity ELSE 0 END) AS recv_qty,
         SUM(CASE WHEN received_at IS NULL OR received_at='' THEN quantity ELSE 0 END) AS open_qty,
         MAX(received_at) AS last_recv,
         COUNT(*) AS ship_cnt
  FROM shipments GROUP BY sales_order_id
)
SELECT o.sales_order_id,
       o.work_order_id,
       o.contract_no,
       c.customer_name,
       p.product_name,
       o.quantity,
       o.unit,
       o.contract_amount,
       o.promised_delivery_at,
       s.last_recv AS delivered_at,
       CAST(julianday(substr(s.last_recv,1,10)) - julianday(substr(o.promised_delivery_at,1,10)) AS INTEGER) AS late_days,
       s.ship_cnt AS shipments
FROM orders o
JOIN s ON s.sales_order_id = o.sales_order_id
LEFT JOIN customers c ON c.customer_id = o.customer_id
LEFT JOIN products p ON p.product_id = o.product_id
WHERE o.is_effective = 1 AND s.recv_qty >= o.quantity AND s.open_qty = 0
ORDER BY s.last_recv DESC
