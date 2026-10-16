#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""订单全流程流转数据修复（2026-09-20）。

背景: 订单表被重灌为 331 单新机器下单表(XL-MO-xxxxx)后, stage_nodes 仍指向旧订单号
(CRM-MO-*/KL-*, 87 单 435 行成为孤儿), 新订单没有任何流程节点——全流程页面/进度
KPI(完成 0)/状态分布全部失真。

修复:
  1) 删除孤儿 stage_nodes(订单号已不在 v_current_orders);
  2) 为 331 张当前订单按「创建日→承诺交期」合成五节点流转
     (PLAN计划→PROCESS加工→QC质检→SHIP发货→SIGN签收), 位相分布贴合交期远近:
     远期交付多为已完成(已签收), 近期/未来交付分布在 备料/加工/验收/待出货;
  3) 已完成单生成签收 shipment(全量签收口径), 待出货单部分生成在途 shipment;
  4) 不动 9 个月经营简报历史(shipments/exceptions/expenses/labor_logs 旧数据保留)。
确定性: random.Random(20260920)。
"""
import random
import sqlite3
from datetime import date, datetime, timedelta

DB = "/data/actions/zhizaoyun-datahub/agent_data.sqlite"
SNAP_TS = "2026-09-20T08:00:00+08:00"
S_DAY = date(2026, 9, 20)          # 快照日(业务时间须早于它)
R = random.Random(20260920)

D0 = lambda d: d.strftime("%Y-%m-%dT00:00:00+08:00")
EOD = lambda d: d.strftime("%Y-%m-%dT23:59:59+08:00")
DAY = lambda ts: date.fromisoformat(ts[:10])

CARRIERS = ["德邦物流", "顺丰速运", "安得物流", "跨越速运", "专线自送", "盛丰物流"]
STAGES = [  # (code, name, dept, frac_lo, frac_hi)
    ("PLAN", "计划", "D01", 0.00, 0.15),
    ("PROCESS", "加工", "D03", 0.15, 0.55),
    ("QC", "质检", "D04", 0.55, 0.65),
    ("SHIP", "发货", "D05", 0.65, 0.80),
    ("SIGN", "签收", "D05", 0.80, 1.00),
]
WC_POOL = ["WC01"] * 5 + ["WC03"] * 3 + ["WC04"] * 2

BEI = ["待图纸", "待确认", "待回料", "待物料验收"]            # 备料/图纸/确认
JIA = ["待组装", "组装中", "待调试", "调试中"]                # 加工/调试
YAN, CHU, WAN = ["待验收"], ["待出货"], ["已签收"]            # 验收 / 待出货 / 已完成


def pick(weights):
    x = R.random() * sum(weights)
    for i, w in enumerate(weights):
        x -= w
        if x <= 0:
            return i
    return len(weights) - 1


def phase_for(promised):
    """按承诺交期相对快照的远近定当前位相。"""
    days = (promised - S_DAY).days
    if days < -45:                       # 早已到期: 绝大多数已交付
        k = pick([90, 4, 2, 2, 2])
    elif days < 0:                       # 近期到期: 过半交付, 其余在制
        k = pick([50, 20, 12, 10, 8])
    else:                                # 未来交期: 少量提前交付
        k = pick([15, 35, 15, 10, 25])
    return ["done", "proc", "ship", "qc", "plan"][k]


def build():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # ---------- 1) 清理孤儿节点 ----------
    orphans = cur.execute("""DELETE FROM stage_nodes WHERE sales_order_id NOT IN
        (SELECT sales_order_id FROM v_current_orders)""").rowcount
    old_ship = cur.execute("""SELECT COUNT(*) FROM shipments WHERE sales_order_id NOT IN
        (SELECT sales_order_id FROM v_current_orders)""").fetchone()[0]

    # ---------- 2) 为当前订单合成流转 ----------
    orders = [dict(r) for r in cur.execute(
        "SELECT sales_order_id, quantity, unit, created_at, promised_delivery_at "
        "FROM v_current_orders ORDER BY sales_order_id")]
    emps = [r[0] for r in cur.execute("SELECT employee_id FROM employees")]

    stats = {"done": 0, "proc": 0, "qc": 0, "ship": 0, "plan": 0}
    sn_seq, sh_seq = 1, 1
    new_ships = 0
    for o in orders:
        so = o["sales_order_id"]
        c = DAY(o["created_at"])
        p = DAY(o["promised_delivery_at"] or o["created_at"])
        if (p - c).days < 7:
            p = c + timedelta(days=7)
        span = (p - c).days
        phase = phase_for(p)
        stats[phase] += 1

        # 订单级当天状态原文(挂在每个节点上, 与生产总表惯例一致)
        if phase == "done":
            raw = R.choice(WAN)
            sign_day = min(p - timedelta(days=R.randint(0, max(1, span // 5))), S_DAY - timedelta(days=1))
            if sign_day <= c + timedelta(days=3):
                sign_day = min(c + timedelta(days=R.randint(3, min(span, 30))), S_DAY - timedelta(days=1))
        else:
            raw = {"plan": R.choice(BEI), "proc": R.choice(JIA),
                   "qc": R.choice(YAN), "ship": R.choice(CHU)}[phase]

        # 各节点计划窗口
        wins = []
        for code, name, dept, lo, hi in STAGES:
            ws = c + timedelta(days=int(span * lo))
            we = c + timedelta(days=max(int(span * hi), int(span * lo) + 1))
            wins.append([code, name, dept, ws, we])

        # 逐节点落状态
        phase_idx = {"plan": 0, "proc": 1, "qc": 2, "ship": 3, "done": 5}[phase]
        wc = R.choice(WC_POOL)
        prev_end = c
        rows = []
        for i, (code, name, dept, ws, we) in enumerate(wins):
            if i < phase_idx:      # 已走完
                a_s = max(ws, prev_end + timedelta(days=1 if prev_end >= ws else 0))
                a_e = min(we, a_s + timedelta(days=max(1, (we - a_s).days // 2 + R.randint(0, 3))))
                if phase == "done":
                    a_e = min(a_e, sign_day)
                    if a_s > a_e:
                        a_s, a_e = a_e, a_e
                st, a_start, a_end = "已完成", D0(a_s), EOD(a_e)
                prev_end = a_e
            elif i == phase_idx:   # 当前进行中
                st = "进行中"
                a_s = max(ws, S_DAY - timedelta(days=R.randint(1, 12)))
                a_start, a_end = D0(min(a_s, S_DAY - timedelta(days=1))), None
                prev_end = S_DAY
            else:                  # 未开始
                st, a_start, a_end = "未开始", None, None
            rows.append((f"SN-XL-{sn_seq:06d}", so, None, code, name, i + 1, dept,
                         wc if code == "PROCESS" else None,
                         D0(ws), EOD(we), a_start, a_end, st,
                         R.choice(emps), SNAP_TS, raw))
            sn_seq += 1
        cur.executemany("""INSERT INTO stage_nodes
            (stage_id, sales_order_id, work_order_id, stage_code, stage_name, sequence,
             department_id, workcenter_id, planned_start_at, planned_end_at,
             actual_start_at, actual_end_at, stage_status, owner_employee_id, updated_at, source_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)

        # ---------- 3) 发货/签收 ----------
        qty = o["quantity"] or 1
        unit = o["unit"] or "台"
        if phase == "done":
            disp = max(c, sign_day - timedelta(days=R.randint(1, 6)))
            cur.execute("""INSERT INTO shipments
                (shipment_id, sales_order_id, carrier, tracking_no, quantity, unit,
                 dispatched_at, carrier_promised_at, received_at, freight_cost, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (f"SH-XL-{sh_seq:06d}", so, R.choice(CARRIERS),
                 "XL%012d" % R.randrange(10 ** 11, 10 ** 12), qty, unit,
                 D0(disp), D0(p), D0(sign_day),
                 R.choice([200, 350, 500, 800, 1200, 1800]), "已签收"))
            sh_seq += 1
            new_ships += 1
        elif phase == "ship" and R.random() < 0.4:      # 待出货且已在途
            disp = S_DAY - timedelta(days=R.randint(1, 5))
            cur.execute("""INSERT INTO shipments
                (shipment_id, sales_order_id, carrier, tracking_no, quantity, unit,
                 dispatched_at, carrier_promised_at, received_at, freight_cost, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (f"SH-XL-{sh_seq:06d}", so, R.choice(CARRIERS),
                 "XL%012d" % R.randrange(10 ** 11, 10 ** 12), qty, unit,
                 D0(disp), D0(p), None,
                 R.choice([200, 350, 500, 800]), "已发货"))
            sh_seq += 1
            new_ships += 1

    con.commit()

    # ---------- 校验 ----------
    print("孤儿节点删除:", orphans, "| 旧发货(保留作简报历史):", old_ship)
    print("位相分布:", stats, "| 合计:", sum(stats.values()))
    print("新增 shipment:", new_ships)
    kpi = cur.execute("""WITH s AS (SELECT sales_order_id, COUNT(*) b,
        SUM(CASE WHEN status='已签收' AND received_at<>'' THEN 1 ELSE 0 END) g
        FROM shipments GROUP BY 1)
        SELECT (SELECT COUNT(*) FROM v_current_orders),
               (SELECT COUNT(*) FROM v_current_orders o JOIN s USING(sales_order_id) WHERE s.g=s.b),
               (SELECT COUNT(*) FROM v_current_orders o LEFT JOIN s USING(sales_order_id)
                 WHERE s.sales_order_id IS NULL OR s.g<s.b)""").fetchone()
    print("KPI: 生效 %d / 已完成 %d / 未完成 %d" % tuple(kpi))
    for r in cur.execute("""SELECT stage_code, COUNT(*) total,
        SUM(stage_status='已完成') done, SUM(stage_status='进行中') run, SUM(stage_status='未开始') pend
        FROM stage_nodes GROUP BY 1"""):
        print("  ", tuple(r))
    con.close()


if __name__ == "__main__":
    build()
