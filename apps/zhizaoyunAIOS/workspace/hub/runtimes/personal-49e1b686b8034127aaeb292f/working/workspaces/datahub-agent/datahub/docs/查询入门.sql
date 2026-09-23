-- Query examples; run against agent_data.sqlite (read-only recommended).
-- 1. Effective orders. Future examples are excluded.
SELECT sales_order_id, work_order_id, customer_id, product_id, quantity, unit, promised_delivery_at
FROM v_current_orders
LIMIT 20;

-- 2. Stock at warehouse / lot / item grain. Signed quantities are already normalized.
SELECT warehouse_id,lot_id,material_id,product_id,
       ROUND(SUM(signed_quantity),6) AS balance
FROM wms_transactions
GROUP BY warehouse_id,lot_id,material_id,product_id
ORDER BY warehouse_id,lot_id;

-- 3. Observe schema before choosing columns and JOIN keys.
PRAGMA table_info(stage_nodes);
PRAGMA table_info(shipments);
PRAGMA foreign_key_list(work_orders);

-- Do not join multiple fact tables directly and then SUM.
-- Aggregate labor, warehouse movements and freight separately to sales_order_id first.
