WITH snap AS (SELECT julianday('2026-09-18T08:00:00+08:00') AS t),
slip0 AS (
  SELECT sn.stage_code, o.fulfillment_mode,
         julianday(sn.actual_end_at)-julianday(sn.planned_end_at) AS d,
         ROW_NUMBER() OVER (PARTITION BY sn.stage_code,o.fulfillment_mode
                            ORDER BY julianday(sn.actual_end_at)-julianday(sn.planned_end_at)) rn,
         COUNT(*)    OVER (PARTITION BY sn.stage_code,o.fulfillment_mode) n
  FROM stage_nodes sn JOIN orders o ON o.sales_order_id=sn.sales_order_id
  WHERE sn.actual_end_at IS NOT NULL AND o.is_effective=1),
slip_p AS (
  SELECT stage_code, fulfillment_mode, MAX(n) n,
         MAX(CASE WHEN rn=CAST(n*0.5 AS INT)+1 THEN d END) p50,
         MAX(CASE WHEN rn=CAST(n*0.9 AS INT)+1 THEN d END) p90
  FROM slip0 GROUP BY stage_code, fulfillment_mode),
tr0 AS (
  SELECT route_id, julianday(received_at)-julianday(dispatched_at) d,
         ROW_NUMBER() OVER (PARTITION BY route_id ORDER BY julianday(received_at)-julianday(dispatched_at)) rn,
         COUNT(*)    OVER (PARTITION BY route_id) n
  FROM shipments WHERE received_at IS NOT NULL),
tr_p AS (SELECT route_id, MAX(n) n,
         MAX(CASE WHEN rn=CAST(n*0.5 AS INT)+1 THEN d END) p50,
         MAX(CASE WHEN rn=CAST(n*0.9 AS INT)+1 THEN d END) p90 FROM tr0 GROUP BY route_id),
node AS (
  SELECT sn.sales_order_id,
         SUM(CASE WHEN sn.actual_end_at IS NULL THEN 1 ELSE 0 END) open_nodes,
         SUM(CASE WHEN sn.actual_end_at IS NULL AND sn.planned_end_at < (SELECT t FROM snap) THEN 1 ELSE 0 END) overdue_nodes,
         ROUND(MAX(CASE WHEN sn.actual_end_at IS NULL THEN (SELECT t FROM snap)-julianday(sn.planned_end_at) END),1) max_overdue_d,
         MIN(CASE WHEN sn.actual_end_at IS NULL THEN sn.planned_end_at END) next_due_at,
         (SELECT stage_name||'(seq'||sequence||')' FROM stage_nodes x
            WHERE x.sales_order_id=sn.sales_order_id AND x.actual_end_at IS NULL
            ORDER BY x.sequence LIMIT 1) cur_stage,
         (SELECT stage_status FROM stage_nodes x
            WHERE x.sales_order_id=sn.sales_order_id AND x.actual_end_at IS NULL
            ORDER BY x.sequence LIMIT 1) cur_stage_status,
         MAX(CASE WHEN sn.stage_code='SHIP' THEN sn.planned_end_at END) ship_planned_end,
         SUM(CASE WHEN sn.stage_status='进行中' THEN 1 ELSE 0 END) running_nodes
  FROM stage_nodes sn GROUP BY sn.sales_order_id),
proc AS (
  SELECT sales_order_id,
         SUM(CASE WHEN actual_receipt_at IS NULL THEN 1 ELSE 0 END) open_po,
         MAX(CASE WHEN actual_receipt_at IS NULL THEN supplier_confirmed_eta END) last_eta,
         ROUND(MAX(CASE WHEN actual_receipt_at IS NULL THEN julianday(supplier_confirmed_eta)-julianday(promised_receipt_at) END),1) eta_slip_d
  FROM procurement_lines GROUP BY sales_order_id),
qc AS (SELECT sales_order_id, SUM(CASE WHEN result='不合格' THEN 1 ELSE 0 END) bad_qc
       FROM quality_inspections GROUP BY sales_order_id),
exc AS (SELECT sales_order_id, SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) open_exc,
        MAX(CASE WHEN closed_at IS NULL THEN severity END) open_sev
        FROM exceptions GROUP BY sales_order_id)
SELECT o.sales_order_id, o.work_order_id, c.customer_name, c.customer_tier,
       o.fulfillment_mode, o.quantity, o.unit, o.route_id, rt.route_name,
       o.promised_delivery_at,
       ROUND(julianday(o.promised_delivery_at)-(SELECT t FROM snap),1) AS days_to_promise,
       IFNULL(nd.cur_stage,'-') cur_stage, IFNULL(nd.cur_stage_status,'-') cur_status,
       IFNULL(nd.open_nodes,0) open_nodes, IFNULL(nd.overdue_nodes,0) overdue_nodes,
       IFNULL(nd.max_overdue_d,0) max_overdue_d, IFNULL(nd.running_nodes,0) running_nodes,
       nd.next_due_at, nd.ship_planned_end,
       ROUND(sp.p50,2) ship_slip_p50, ROUND(sp.p90,2) ship_slip_p90, sp.n slip_n,
       ROUND(tp.p50,1) transit_p50, ROUND(tp.p90,1) transit_p90, tp.n transit_n,
       IFNULL(pr.open_po,0) open_po, pr.last_eta, pr.eta_slip_d,
       IFNULL(qc.bad_qc,0) bad_qc, IFNULL(ex.open_exc,0) open_exc, IFNULL(ex.open_sev,'-') open_sev,
       IFNULL(o.source_risk_flag,'-') src_flag, IFNULL(o.source_risk_reason,'-') src_reason, o.delivery_basis
FROM orders o
LEFT JOIN customers c     ON c.customer_id=o.customer_id
LEFT JOIN routes rt       ON rt.route_id=o.route_id
LEFT JOIN node nd         ON nd.sales_order_id=o.sales_order_id
LEFT JOIN slip_p sp       ON sp.stage_code='SHIP' AND sp.fulfillment_mode=o.fulfillment_mode
LEFT JOIN tr_p tp         ON tp.route_id=o.route_id
LEFT JOIN proc pr         ON pr.sales_order_id=o.sales_order_id
LEFT JOIN qc              ON qc.sales_order_id=o.sales_order_id
LEFT JOIN exc ex          ON ex.sales_order_id=o.sales_order_id
WHERE o.is_effective=1
  AND NOT EXISTS (SELECT 1 FROM shipments s WHERE s.sales_order_id=o.sales_order_id)
ORDER BY days_to_promise;
