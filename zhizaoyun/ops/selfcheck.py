#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量自检: 覆盖审计报告全部轮次(A/B/C/D/E/F/G/H/N) + 跨系统 + 页面, 14实例"""
import json, urllib.request, sqlite3

accounts = json.load(open('/tmp/ent/accounts.json'))
PORTS = [('主库', 18790)] + [(a['ent'], a['port']) for a in accounts]

# (编号, 说明, SQL, 期望值/谓词)
def EQ(v): return ('eq', v)
def GT(v): return ('gt', v)
def LE(v): return ('le', v)
def BETWEEN(lo, hi): return ('between', (lo, hi))

CHECKS = [
 # A 集成
 ('A1', '悬空运单', "SELECT COUNT(*) AS n FROM shipments s LEFT JOIN orders o ON s.sales_order_id=o.sales_order_id WHERE o.sales_order_id IS NULL", EQ(0)),
 ('E1a', '无工单订单', "SELECT COUNT(*) AS n FROM orders o LEFT JOIN work_orders w ON w.sales_order_id=o.sales_order_id WHERE w.work_order_id IS NULL", EQ(0)),
 ('E1b', '悬空工单', "SELECT COUNT(*) AS n FROM work_orders w LEFT JOIN orders o ON w.sales_order_id=o.sales_order_id WHERE o.sales_order_id IS NULL", EQ(0)),
 ('E1c', '无节点订单', "SELECT COUNT(*) AS n FROM orders o LEFT JOIN stage_nodes s ON s.sales_order_id=o.sales_order_id WHERE s.sales_order_id IS NULL", EQ(0)),
 # B 时序
 ('B1', '签收早于发货', "SELECT COUNT(*) AS n FROM shipments WHERE received_at IS NOT NULL AND received_at<dispatched_at", EQ(0)),
 ('B2', '交期早于下单', "SELECT COUNT(*) AS n FROM orders WHERE promised_delivery_at<created_at", EQ(0)),
 ('B3', '负库存', "SELECT COUNT(*) AS n FROM inventory_snapshot WHERE 当天库存<0", EQ(0)),
 ('B4', '空发布工单', "SELECT COUNT(*) AS n FROM work_orders WHERE released_at IS NULL OR released_at=''", EQ(0)),
 # C/D
 ('C5', '待审批报销', "SELECT COUNT(*) AS n FROM expenses WHERE status='待审批'", EQ(0)),
 ('D1', '采购迟到率%', "SELECT ROUND(SUM(CASE WHEN actual_receipt_at>supplier_confirmed_eta THEN 1 ELSE 0 END)*100.0/COUNT(*),0) AS n FROM procurement_lines WHERE actual_receipt_at IS NOT NULL", LE(15)),
 ('D3', '空采购行', "SELECT COUNT(*) AS n FROM procurement_lines WHERE COALESCE(required_quantity,0)=0 AND COALESCE(ordered_quantity,0)=0 AND (unit_cost IS NULL OR unit_cost=0)", EQ(0)),
 # E
 ('E2a', '考勤行数', "SELECT COUNT(*) AS n FROM attendance", GT(15000)),
 ('E2b', '考勤起始月', "SELECT CAST(substr(MIN(work_date),6,2) AS INTEGER) AS n FROM attendance", EQ(1)),
 # F/G
 ('G2', '负未收', "SELECT COUNT(*) AS n FROM contracts WHERE unpaid_amount<0", EQ(0)),
 ('G3', '缺客户名', "SELECT COUNT(*) AS n FROM contracts WHERE customer_name IS NULL OR customer_name=''", EQ(0)),
 ('G4', '合同号唯一差', "SELECT (SELECT COUNT(*) FROM contracts)-(SELECT COUNT(DISTINCT contract_no) FROM contracts) AS n", EQ(0)),
 ('G4b', '收支不平', "SELECT COUNT(*) AS n FROM contracts WHERE ABS(COALESCE(received_amount,0)+COALESCE(unpaid_amount,0)-contract_amount)>1", EQ(0)),
 ('B2b', '越快照订单', "SELECT COUNT(*) AS n FROM orders WHERE created_at>'2026-10-07T08:00:00'", EQ(0)),
 # H 系列
 ('H1', '头部4人销售占比%', "SELECT (SELECT SUM(c) FROM (SELECT COUNT(*) c FROM orders GROUP BY sales_owner ORDER BY c DESC LIMIT 4))*100.0/(SELECT COUNT(*) FROM orders) AS n", LE(60)),
 ('H3', '渠道前缀残留', "SELECT COUNT(*) AS n FROM customers WHERE customer_name REGEXP '^(BG|FB|KL|AL|SY|PDD)[- ]'" if False else "SELECT COUNT(*) AS n FROM customers WHERE (customer_name LIKE 'BG %' OR customer_name LIKE 'FB %' OR customer_name LIKE 'KL %' OR customer_name LIKE 'PDD %' OR customer_name LIKE 'AL %')", EQ(0)),
 ('H4', '运单缺承运商', "SELECT COUNT(*) AS n FROM shipments WHERE carrier IS NULL OR carrier=''", EQ(0)),
 ('H4b', '运单缺运费', "SELECT COUNT(*) AS n FROM shipments WHERE freight_cost IS NULL OR freight_cost=0", EQ(0)),
 ('H6', '质检员缺失', "SELECT COUNT(*) AS n FROM quality_inspections WHERE inspector_employee_id IS NULL", EQ(0)),
 ('H7a', '检验类型数', "SELECT COUNT(DISTINCT inspection_type) AS n FROM quality_inspections", GT(2)),
 ('H7b', '缺陷码数', "SELECT COUNT(DISTINCT defect_code) AS n FROM quality_inspections WHERE defect_code IS NOT NULL AND defect_code<>''", GT(3)),
 ('H8', '特采无依据', "SELECT COUNT(*) AS n FROM quality_inspections WHERE result='特采' AND (defect_description IS NULL OR defect_description NOT LIKE '%评审单%')", EQ(0)),
 ('H10', '工时部门悬空', "SELECT COUNT(*) AS n FROM labor_logs l LEFT JOIN departments d ON l.department_id=d.department_id WHERE d.department_id IS NULL", EQ(0)),
 ('H11', '试用期离职率%', "SELECT ROUND(SUM(CASE WHEN probation_result='试用期离职' THEN 1 ELSE 0 END)*100.0/COUNT(*),0) AS n FROM hiring_records", LE(20)),
 ('H12', '离职样本量', "SELECT COUNT(*) AS n FROM turnover_records", GT(40)),
 ('H13', '差旅贴线数', "SELECT COUNT(*) AS n FROM expenses WHERE expense_type LIKE '%差旅%' AND amount BETWEEN 5900 AND 6000", EQ(0)),
 ('H14', 'purchase_status代码残留', "SELECT COUNT(*) AS n FROM contracts WHERE purchase_status IN ('1','2') OR purchase_status IS NULL", EQ(0)),
 ('H16', '履约形态数', "SELECT COUNT(DISTINCT fulfillment_mode) AS n FROM orders", GT(2)),
 # 主数据
 ('MD1', '员工数', "SELECT COUNT(*) AS n FROM employees", EQ(87)),
 ('MD2', '部门数', "SELECT COUNT(DISTINCT department_id) AS n FROM employees", EQ(12)),
 ('MD3', '设备数', "SELECT COUNT(*) AS n FROM equipment", GT(10)),
 ('MD4', '路线数', "SELECT COUNT(*) AS n FROM routes", GT(8)),
 ('MD5', '待推送队列', "SELECT COUNT(*) AS n FROM erp_entry_queue WHERE status='待推送'", EQ(0)),
 ('MD6', '采集半途', "SELECT COUNT(*) AS n FROM source_file_profile WHERE status LIKE '%待%'", EQ(0)),
 ('MD7', '空mes', "SELECT COUNT(*) AS n FROM mes_events", GT(20)),
 ('MD8', '空logistics', "SELECT COUNT(*) AS n FROM logistics_events", GT(50)),
 # 第四轮新增
 ('R4a', '实际时序倒挂', "SELECT COUNT(*) AS n FROM (SELECT a.stage_id FROM stage_nodes a JOIN stage_nodes b ON a.sales_order_id=b.sales_order_id AND a.sequence=b.sequence+1 WHERE a.actual_start_at IS NOT NULL AND b.actual_start_at IS NOT NULL AND a.actual_start_at<b.actual_start_at)", EQ(0)),
 ('R4b', '计划时序倒挂', "SELECT COUNT(*) AS n FROM (SELECT a.stage_id FROM stage_nodes a JOIN stage_nodes b ON a.sales_order_id=b.sales_order_id AND a.sequence=b.sequence+1 WHERE a.planned_start_at<b.planned_start_at)", EQ(0)),
 ('R4c', '实际时间超快照', "SELECT COUNT(*) AS n FROM stage_nodes WHERE actual_end_at>'2026-10-06T23:59:59'", EQ(0)),
 ('R4d', '挂起处理中工单', "SELECT COUNT(*) AS n FROM exceptions WHERE status='处理中'", EQ(0)),
 # N 口径
 ('N1', '无计划节点(未完成)', "SELECT COUNT(*) AS n FROM stage_nodes WHERE stage_status<>'已完成' AND (planned_end_at IS NULL OR planned_end_at='')", EQ(0)),
 ('N2', '越界日期节点', "SELECT COUNT(*) AS n FROM stage_nodes WHERE planned_start_at<'2018-01-01' OR planned_end_at>'2027-12-31'", EQ(0)),
]


def sql(p, s):
    req = urllib.request.Request(f'http://127.0.0.1:{p}/api/sql',
                                 data=json.dumps({"sql": s}).encode(),
                                 headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())['rows'][0]['n']


def judge(v, pred):
    kind, val = pred
    if kind == 'eq':
        return v == val
    if kind == 'gt':
        return v > val
    if kind == 'le':
        return v <= val
    if kind == 'between':
        return val[0] <= v <= val[1]
    return False


total_fail = 0
for name, p in PORTS:
    fails = []
    for code, label, q, pred in CHECKS:
        try:
            v = sql(p, q)
            if not judge(v, pred):
                fails.append(f'{code}({label})={v}')
        except Exception as e:
            fails.append(f'{code}({label})=ERR:{str(e)[:30]}')
    if fails:
        total_fail += 1
        print(f'{name:<5} ✗ {fails}')
    else:
        print(f'{name:<5} ✓ {len(CHECKS)}项全过')
print(f'\n数据自检: {len(PORTS) - total_fail}/{len(PORTS)} 实例通过 ({len(CHECKS)}项/实例)')
