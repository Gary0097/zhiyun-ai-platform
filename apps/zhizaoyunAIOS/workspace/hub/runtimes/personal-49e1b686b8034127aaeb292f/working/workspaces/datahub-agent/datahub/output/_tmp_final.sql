WITH snap AS (SELECT julianday('2026-09-18T08:00:00+08:00') t),
-- 线路运输时效（已签收运单：dispatched -> received）
tr0 AS (SELECT route_id, julianday(received_at)-julianday(dispatched_at) d,
             ROW_NUMBER() OVER (PARTITION BY route_id ORDER BY julianday(received_at)-julianday(dispatched_at)) rn,
             COUNT(*) OVER (PARTITION BY route_id) n FROM shipments WHERE received_at IS NOT NULL),
tr_p AS (SELECT route_id, MAX(n) n,
                MAX(CASE WHEN rn=CAST(n*0.5 AS INT)+1 THEN d END) p50,
                MAX(CASE WHEN rn=CAST(n*0.9 AS INT)+1 THEN d END) p90 FROM tr0 GROUP BY route_id),
lr AS (SELECT sales_order_id, MAX(received_at) last_recv,
              SUM(CASE WHEN received_at IS NOT NULL THEN quantity ELSE 0 END) signed_qty,
              SUM(quantity) disp_qty, SUM(CASE WHEN received_at IS NULL THEN 1 ELSE 0 END) transit_cnt
       FROM shipments GROUP BY sales_order_id),
shp AS (SELECT sales_order_id, MAX(planned_end_at) ship_planned_end FROM stage_nodes WHERE stage_code='SHIP' GROUP BY 1),
-- 发货计划结束 -> 全量签收 的残余时长（按线路）
res0 AS (SELECT o.route_id, julianday(lr.last_recv)-julianday(shp.ship_planned_end) d,
                ROW_NUMBER() OVER (PARTITION BY o.route_id ORDER BY julianday(lr.last_recv)-julianday(shp.ship_planned_end)) rn,
                COUNT(*)    OVER (PARTITION BY o.route_id) n
         FROM orders o JOIN lr ON lr.sales_order_id=o.sales_order_id
                       JOIN shp ON shp.sales_order_id=o.sales_order_id
         WHERE o.is_effective=1 AND lr.last_recv IS NOT NULL AND shp.ship_planned_end IS NOT NULL
           AND lr.signed_qty>=o.quantity),
res_p AS (SELECT route_id, MAX(n) n,
                 MAX(CASE WHEN rn=CAST(n*0.5 AS INT)+1 THEN d END) p50,
                 MAX(CASE WHEN rn=CAST(n*0.9 AS INT)+1 THEN d END) p90 FROM res0 GROUP BY route_id),
-- ===== 经验曲线1：在途 (buffer x 是否有运输延误事件) -> 迟签收率，拉普拉斯平滑 =====
hist_t AS (
  SELECT s.shipment_id, s.route_id, julianday(o.promised_delivery_at) prom, julianday(s.received_at) recv,
         (SELECT COUNT(*) FROM logistics_events e WHERE e.shipment_id=s.shipment_id AND e.event_status='运输延误')>0 dly
  FROM shipments s JOIN orders o ON o.sales_order_id=s.sales_order_id
  WHERE s.received_at IS NOT NULL),
hist_t2 AS (SELECT h.*, julianday(h.prom) - (julianday(s.dispatched_at) + IFNULL(tp.p50,5)) buf
           FROM hist_t h JOIN shipments s ON s.shipment_id=h.shipment_id LEFT JOIN tr_p tp ON tp.route_id=h.route_id),
curve_t AS (
  SELECT CASE WHEN buf<-5 THEN 'a' WHEN buf<-2 THEN 'b' WHEN buf<0 THEN 'c' WHEN buf<2 THEN 'd'
              WHEN buf<5 THEN 'e' WHEN buf<10 THEN 'f' ELSE 'g' END bk,
         CASE WHEN dly=1 THEN 1 ELSE 0 END dly, COUNT(*) n,
         ROUND(1.0*(SUM(CASE WHEN recv>prom THEN 1 ELSE 0 END)+1)/(COUNT(*)+2),3) p
  FROM hist_t2 GROUP BY 1,2),
-- ===== 经验曲线2：未发货 (buffer) -> 迟签收率，拉普拉斯平滑 =====
hist_p AS (
  SELECT o.sales_order_id, julianday(o.promised_delivery_at) prom, julianday(lr.last_recv) recv,
         julianday(shp.ship_planned_end) + IFNULL(rp.p50,7) pred
  FROM orders o JOIN lr ON lr.sales_order_id=o.sales_order_id
                JOIN shp ON shp.sales_order_id=o.sales_order_id
                LEFT JOIN res_p rp ON rp.route_id=o.route_id
  WHERE o.is_effective=1 AND lr.last_recv IS NOT NULL AND shp.ship_planned_end IS NOT NULL AND lr.signed_qty>=o.quantity),
curve_p AS (
  SELECT CASE WHEN prom-pred<-10 THEN 'a' WHEN prom-pred<-5 THEN 'b' WHEN prom-pred<-2 THEN 'c'
              WHEN prom-pred<0 THEN 'd' WHEN prom-pred<2 THEN 'e' WHEN prom-pred<5 THEN 'f'
              WHEN prom-pred<10 THEN 'g' WHEN prom-pred<20 THEN 'h' ELSE 'i' END bk,
         COUNT(*) n, ROUND(1.0*(SUM(CASE WHEN recv>prom THEN 1 ELSE 0 END)+1)/(COUNT(*)+2),3) p
  FROM hist_p GROUP BY 1),
-- ===== 节点/异常/采购/质检 =====
nd AS (SELECT sn.sales_order_id,
            SUM(CASE WHEN sn.actual_end_at IS NULL THEN 1 ELSE 0 END) open_nodes,
            SUM(CASE WHEN sn.actual_end_at IS NULL AND sn.planned_end_at<(SELECT t FROM snap) THEN 1 ELSE 0 END) overdue_nodes,
            ROUND(MAX(CASE WHEN sn.actual_end_at IS NULL AND sn.stage_code<>'SHIP'
                           THEN (SELECT t FROM snap)-julianday(sn.planned_end_at) END),1) up_overdue_d,
            (SELECT x.stage_name FROM stage_nodes x WHERE x.sales_order_id=sn.sales_order_id
               AND x.actual_end_at IS NULL ORDER BY x.sequence LIMIT 1) cur_stage,
            (SELECT x.stage_status FROM stage_nodes x WHERE x.sales_order_id=sn.sales_order_id
               AND x.actual_end_at IS NULL ORDER BY x.sequence LIMIT 1) cur_status,
            (SELECT x.planned_end_at FROM stage_nodes x WHERE x.sales_order_id=sn.sales_order_id
               AND x.actual_end_at IS NULL ORDER BY x.sequence LIMIT 1) cur_planned_end
     FROM stage_nodes sn GROUP BY sn.sales_order_id),
exc AS (SELECT sales_order_id, SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) open_exc,
               MAX(CASE WHEN closed_at IS NULL THEN severity END) open_sev,
               MAX(CASE WHEN closed_at IS NULL THEN exception_type END) open_exc_type
        FROM exceptions GROUP BY sales_order_id),
prc AS (SELECT sales_order_id,
               SUM(CASE WHEN actual_receipt_at IS NULL THEN 1 ELSE 0 END) open_po,
               MAX(CASE WHEN actual_receipt_at IS NULL AND supplier_confirmed_eta>promised_receipt_at THEN 1 ELSE 0 END) eta_late,
               MAX(CASE WHEN actual_receipt_at IS NULL THEN supplier_confirmed_eta END) last_eta
        FROM procurement_lines GROUP BY sales_order_id),
qc AS (SELECT sales_order_id, SUM(CASE WHEN result='不合格' THEN 1 ELSE 0 END) bad_qc
       FROM quality_inspections GROUP BY sales_order_id),
dev AS (SELECT shipment_id, SUM(CASE WHEN event_status='运输延误' THEN 1 ELSE 0 END) delay_ev,
               (SELECT event_status FROM logistics_events e WHERE e.shipment_id=l.shipment_id ORDER BY event_at DESC LIMIT 1) last_ev_status,
               MAX(event_at) last_ev_at
        FROM logistics_events l GROUP BY shipment_id),
-- ===== 在途 =====
intransit AS (
  SELECT '在途' grp, s.shipment_id ref_id, o.sales_order_id, o.work_order_id, c.customer_name, c.customer_tier,
         o.fulfillment_mode, o.quantity order_qty, s.quantity ship_qty, o.quantity-IFNULL(lr.signed_qty,0) open_qty, o.unit,
         rt.route_name, o.route_id, o.promised_delivery_at, s.dispatched_at, s.carrier_promised_at,
         julianday(s.dispatched_at)+IFNULL(tp.p50,5) pred_p50, julianday(s.dispatched_at)+IFNULL(tp.p90,23) pred_p90,
         IFNULL(tp.n,0) base_n, IFNULL(dv.delay_ev,0) delay_ev, IFNULL(dv.last_ev_status,'-') last_ev_status, dv.last_ev_at,
         IFNULL(ex.open_exc,0) open_exc, IFNULL(ex.open_sev,'-') open_sev, IFNULL(ex.open_exc_type,'-') open_exc_type,
         0 open_po, 0 eta_late, 0 bad_qc, 0 overdue_nodes, 0.0 up_overdue_d,
         CASE WHEN lr.disp_qty>=o.quantity THEN '已全量发运' ELSE '部分发运,余量未发' END cur_stage,
         '-' cur_status, NULL cur_planned_end
  FROM shipments s
  JOIN orders o ON o.sales_order_id=s.sales_order_id
  LEFT JOIN lr ON lr.sales_order_id=o.sales_order_id
  LEFT JOIN customers c ON c.customer_id=o.customer_id
  LEFT JOIN routes rt ON rt.route_id=s.route_id
  LEFT JOIN tr_p tp ON tp.route_id=s.route_id
  LEFT JOIN dev dv ON dv.shipment_id=s.shipment_id
  LEFT JOIN exc ex ON ex.sales_order_id=o.sales_order_id
  WHERE s.received_at IS NULL AND o.is_effective=1),
-- ===== 未发货 =====
unshipped AS (
  SELECT '未发货' grp, o.order_line_id ref_id, o.sales_order_id, o.work_order_id, c.customer_name, c.customer_tier,
         o.fulfillment_mode, o.quantity order_qty, 0 ship_qty, o.quantity open_qty, o.unit,
         rt.route_name, o.route_id, o.promised_delivery_at, NULL dispatched_at, NULL carrier_promised_at,
         MAX(julianday(shp.ship_planned_end)+IFNULL(nd.up_overdue_d,0), (SELECT t FROM snap))+IFNULL(rp.p50,7) pred_p50,
         MAX(julianday(shp.ship_planned_end)+IFNULL(nd.up_overdue_d,0), (SELECT t FROM snap))+IFNULL(rp.p90,26) pred_p90,
         IFNULL(rp.n,0) base_n, 0 delay_ev, '-' last_ev_status, NULL last_ev_at,
         IFNULL(ex.open_exc,0) open_exc, IFNULL(ex.open_sev,'-') open_sev, IFNULL(ex.open_exc_type,'-') open_exc_type,
         IFNULL(pc.open_po,0) open_po, IFNULL(pc.eta_late,0) eta_late, IFNULL(qc.bad_qc,0) bad_qc,
         IFNULL(nd.overdue_nodes,0) overdue_nodes, IFNULL(nd.up_overdue_d,0) up_overdue_d,
         IFNULL(nd.cur_stage,'-') cur_stage, IFNULL(nd.cur_status,'-') cur_status, nd.cur_planned_end
  FROM orders o
  LEFT JOIN customers c ON c.customer_id=o.customer_id
  LEFT JOIN routes rt ON rt.route_id=o.route_id
  LEFT JOIN shp ON shp.sales_order_id=o.sales_order_id
  LEFT JOIN nd  ON nd.sales_order_id=o.sales_order_id
  LEFT JOIN res_p rp ON rp.route_id=o.route_id
  LEFT JOIN exc ex ON ex.sales_order_id=o.sales_order_id
  LEFT JOIN prc pc ON pc.sales_order_id=o.sales_order_id
  LEFT JOIN qc     ON qc.sales_order_id=o.sales_order_id
  WHERE o.is_effective=1 AND NOT EXISTS (SELECT 1 FROM shipments s WHERE s.sales_order_id=o.sales_order_id)),
u AS (SELECT * FROM intransit UNION ALL SELECT * FROM unshipped),
s1 AS (SELECT u.*, ROUND(julianday(promised_delivery_at)-(SELECT t FROM snap),1) days_to_promise,
              CASE WHEN julianday(promised_delivery_at)<(SELECT t FROM snap) THEN 1 ELSE 0 END overdue_fact,
              ROUND(julianday(promised_delivery_at)-pred_p50,1) buffer_d
       FROM u),
s2 AS (SELECT s1.*,
       CASE WHEN overdue_fact=1 THEN 'a'
            WHEN grp='在途' THEN CASE WHEN buffer_d<-5 THEN 'a' WHEN buffer_d<-2 THEN 'b' WHEN buffer_d<0 THEN 'c'
                                      WHEN buffer_d<2 THEN 'd' WHEN buffer_d<5 THEN 'e' WHEN buffer_d<10 THEN 'f' ELSE 'g' END
            ELSE CASE WHEN buffer_d<-10 THEN 'a' WHEN buffer_d<-5 THEN 'b' WHEN buffer_d<-2 THEN 'c' WHEN buffer_d<0 THEN 'd'
                      WHEN buffer_d<2 THEN 'e' WHEN buffer_d<5 THEN 'f' WHEN buffer_d<10 THEN 'g' WHEN buffer_d<20 THEN 'h' ELSE 'i' END
       END bk
       FROM s1),
s3 AS (SELECT s2.*, IFNULL(cv.p,0.5) p_buffer, IFNULL(cv.n,0) curve_n
       FROM s2
       LEFT JOIN curve_t cv ON s2.grp='在途' AND cv.bk=s2.bk AND cv.dly=CASE WHEN s2.delay_ev>0 THEN 1 ELSE 0 END
       LEFT JOIN curve_p cp ON s2.grp='未发货' AND cp.bk=s2.bk
       WHERE s2.grp='在途'
       UNION ALL
       SELECT s2.*, IFNULL(cp.p,0.5) p_buffer, IFNULL(cp.n,0) curve_n
       FROM s2 LEFT JOIN curve_p cp ON cp.bk=s2.bk WHERE s2.grp='未发货')
SELECT grp, sales_order_id, ref_id, customer_name, customer_tier, fulfillment_mode,
       order_qty, ship_qty, open_qty, unit, route_name, promised_delivery_at, days_to_promise,
       cur_stage, cur_status, overdue_nodes, up_overdue_d, cur_planned_end,
       datetime((pred_p50-2440587.5)*86400,'unixepoch','+8 hours') p50_recv,
       datetime((pred_p90-2440587.5)*86400,'unixepoch','+8 hours') p90_recv,
       buffer_d, bk, curve_n, base_n, delay_ev, last_ev_status, last_ev_at,
       open_exc, open_sev, open_exc_type, open_po, eta_late, bad_qc, dispatched_at, carrier_promised_at,
       overdue_fact, p_buffer,
       ROUND(CASE WHEN overdue_fact=1 THEN 1.0
                  ELSE MIN(0.99, p_buffer + 0.10*(open_exc>0) + 0.10*(eta_late>0) + 0.05*(bad_qc>0)) END,3) score,
       CASE WHEN overdue_fact=1 THEN '红-延期事实'
            WHEN ROUND(CASE WHEN overdue_fact=1 THEN 1.0 ELSE MIN(0.99, p_buffer + 0.10*(open_exc>0) + 0.10*(eta_late>0) + 0.05*(bad_qc>0)) END,3)>=0.65 THEN '红'
            WHEN ROUND(CASE WHEN overdue_fact=1 THEN 1.0 ELSE MIN(0.99, p_buffer + 0.10*(open_exc>0) + 0.10*(eta_late>0) + 0.05*(bad_qc>0)) END,3)>=0.30 THEN '黄'
            ELSE '绿' END level
FROM s3 ORDER BY grp, overdue_fact DESC, score DESC, days_to_promise;
