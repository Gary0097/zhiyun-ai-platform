-- A. 全量签收判定（批次口径 vs 数量口径）交叉验证
WITH s AS (
  SELECT sales_order_id,
         COUNT(*) batches,
         SUM(CASE WHEN status='已签收' AND received_at IS NOT NULL AND received_at<>'' THEN 1 ELSE 0 END) signed_batches,
         SUM(CASE WHEN status='已签收' AND received_at IS NOT NULL AND received_at<>'' THEN quantity ELSE 0 END) signed_qty,
         MAX(received_at) last_received_at
  FROM shipments GROUP BY sales_order_id)
SELECT o.sales_order_id, o.quantity, s.batches, s.signed_batches, s.signed_qty, s.last_received_at,
       CASE WHEN s.signed_batches=s.batches AND s.signed_qty>=o.quantity THEN 'FULL' ELSE 'PART' END basis
FROM v_current_orders o JOIN s ON s.sales_order_id=o.sales_order_id
WHERE s.last_received_at LIKE '2026-09-17%';
