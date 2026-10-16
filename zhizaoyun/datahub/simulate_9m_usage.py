#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""经营简报 9 个月使用数据模拟（2026-01-01 ~ 2026-09-19，快照 2026-09-20T08:00）

目的: 让"每日经营简报"三项指标(当日签收完成/当日售后工单/当日报销)及 WC02 人效
      在近 9 个月每个报告日都有合理数据, 覆盖此前为空的域:
  1) shipments  —— 签收回填: 窗口内"已发货"未签收记录按 2~9 天在途补签收;
                   并为窗口内承诺交付但无发货记录的有效订单补生成发货+签收;
                   留少量快照前 2 周发货的在途单。
  2) exceptions —— 补齐 work_order_id/severity/closed_at(与 status 一致);
                   为 9 个月中无工单的日期补 1~3 单(工作日)。
  3) expenses   —— 全新生成 9 个月报销流水(工作日 1~5 笔), 状态按账龄演进。
  4) labor_logs —— 全新生成 4 个工作中心工时日志(WC02 近 3 周人效缓降,
                   触发简报"人效下降需核查"口径)。
确定性: 全部随机取自 random.Random(20260920), 重跑结果一致。
时间格式: 与库内既有约定一致, 精确到日 T00:00:00+08:00。
"""
import json
import random
import sqlite3
from datetime import date, timedelta

DB = "/data/actions/zhizaoyun-datahub/agent_data.sqlite"
W0, W1 = date(2026, 1, 1), date(2026, 9, 19)   # 模拟窗口(报告日范围)
SNAP = date(2026, 9, 20)                        # 快照日, 任何业务时间 < SNAP
R = random.Random(20260920)
TS = lambda d: d.strftime("%Y-%m-%dT00:00:00+08:00")

CARRIERS = ["德邦物流", "顺丰速运", "安得物流", "跨越速运", "专线自送", "盛丰物流"]
REASONS = ["客户报修-设备异响", "客户报修-加热异常", "更换配件", "退换机申请",
           "安装调试支持", "客户培训诉求", "设备保养到期", "客户端软件升级"]
EXP_KINDS = [("差旅费", 0.30, 400, 6000), ("招待费", 0.12, 300, 3500),
             ("运输费", 0.20, 200, 4500), ("办公费", 0.13, 60, 900),
             ("售后配件费", 0.15, 150, 3200), ("车辆使用费", 0.10, 100, 800)]


def days_range(a, b):
    d, out = a, []
    while d <= b:
        out.append(d)
        d += timedelta(days=1)
    return out


WINDOW = days_range(W0, W1)
WEEKDAYS = [d for d in WINDOW if d.weekday() < 6]  # 周一~周六为作业日

# 2026 法定假日(模拟口径): 假日无签收/无工时/无报销/无新工单
def _rng(a, b):
    d, out = date.fromisoformat(a), []
    while d <= date.fromisoformat(b):
        out.append(d)
        d += timedelta(days=1)
    return out

HOLIDAYS = (set(_rng("2026-01-01", "2026-01-03"))      # 元旦
            | set(_rng("2026-02-16", "2026-02-22"))     # 春节(初一 02-17)
            | set(_rng("2026-04-04", "2026-04-06"))     # 清明
            | set(_rng("2026-05-01", "2026-05-05"))     # 劳动节
            | set(_rng("2026-06-19", "2026-06-21"))     # 端午
            | set(_rng("2026-09-25", "2026-09-27")))    # 中秋
WORKDAYS = [d for d in WEEKDAYS if d not in HOLIDAYS]


def pick_weighted(pairs):
    x = R.random() * sum(w for _, w, *_ in pairs)
    for item in pairs:
        x -= item[1]
        if x <= 0:
            return item
    return pairs[-1]


def amount_for(kind):
    for k, w, lo, hi in EXP_KINDS:
        if k == kind:
            v = R.uniform(lo, hi)
            return round(v - 0.5 if v > 200 else v, 2)
    return 100.0


def main():
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=OFF")
    q = lambda s, *a: con.execute(s, a).fetchall()
    cur = con.cursor()
    stats = {}

    # ---------- 1) shipments 签收 ----------
    # 1a. 窗口内已存在但未签收的发货
    rows = q("""SELECT shipment_id, dispatched_at FROM shipments
                WHERE status='已发货' AND dispatched_at >= '2026-01-01' AND dispatched_at < '2026-09-20'""")
    signed_old = 0
    intransit_old = 0
    for sid, disp in rows:
        d0 = date.fromisoformat(disp[:10])
        late = d0 >= date(2026, 9, 8)
        if late and R.random() < 0.40:   # 快照前两周发货, 部分仍在途
            intransit_old += 1
            continue
        recv = d0 + timedelta(days=R.choice([2, 2, 3, 3, 4, 4, 5, 6, 7, 8, 9]))
        if recv > W1:
            intransit_old += 1
            continue
        cur.execute("UPDATE shipments SET received_at=?, status='已签收' WHERE shipment_id=?",
                    (TS(recv), sid))
        signed_old += 1

    # 1b. 为窗口内承诺交付但无发货的有效订单补发货
    cand = q("""SELECT sales_order_id, quantity, unit, promised_delivery_at FROM orders
                WHERE sales_order_id NOT IN (SELECT DISTINCT sales_order_id FROM shipments)
                  AND is_effective=1 AND promised_delivery_at IS NOT NULL
                  AND substr(promised_delivery_at,1,10) BETWEEN '2026-01-01' AND '2026-09-30'""")
    # 2025Q4 滞后交付的背单 + 2026-10 提前发的单, 让窗口头部/尾部发货不断档
    cand += q("""SELECT sales_order_id, quantity, unit, promised_delivery_at FROM orders
                 WHERE sales_order_id NOT IN (SELECT DISTINCT sales_order_id FROM shipments)
                   AND is_effective=1
                   AND substr(promised_delivery_at,1,7) IN ('2025-10','2025-11','2025-12')""")
    cand += q("""SELECT sales_order_id, quantity, unit, promised_delivery_at FROM orders
                 WHERE sales_order_id NOT IN (SELECT DISTINCT sales_order_id FROM shipments)
                   AND is_effective=1 AND substr(promised_delivery_at,1,7)='2026-10'""")
    seq = 1
    new_ship = 0
    for so, qty, unit, prom in cand:
        pd_ = date.fromisoformat(prom[:10])
        if pd_ < date(2025, 10, 1) or pd_ > date(2026, 10, 31):
            continue
        if pd_ >= W0:                       # 窗口内承诺: 发货=承诺前 2~6 天
            disp = max(W0, pd_ - timedelta(days=R.randint(2, 6)))
            if disp > W1:                   # 10 月承诺: 改为 9 月中上旬提前发
                disp = W1 - timedelta(days=R.randint(2, 20))
        else:                               # 2025Q4 滞后背单: 1~3 月补发
            disp = W0 + timedelta(days=R.randint(0, 79))
        transit = R.choice([2, 2, 3, 3, 4, 4, 5, 6, 7, 8, 9])
        recv = disp + timedelta(days=transit)
        recent = disp >= date(2026, 9, 8)
        in_transit = recent and R.random() < 0.40
        if recv > W1:
            in_transit = True
        sid = "SH-SIM-%06d" % seq
        seq += 1
        cur.execute("""INSERT INTO shipments
            (shipment_id, sales_order_id, carrier, tracking_no, quantity, unit,
             dispatched_at, carrier_promised_at, received_at, freight_cost, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, so, R.choice(CARRIERS), "SIM%012d" % R.randrange(10 ** 11, 10 ** 12),
             qty or 1, unit or "台", TS(disp), TS(disp + timedelta(days=5)),
             None if in_transit else TS(recv),
             R.choice([200, 350, 500, 800, 1200, 1800, 2600, 3200]),
             "已发货" if in_transit else "已签收"))
        new_ship += 1

    # 1c. 补空窗: 周一~周六每个报告日至少 1 单完成
    def recompute():
        m = {}
        for (rd_,) in q("""SELECT substr(received_at,1,10) FROM shipments
                           WHERE received_at IS NOT NULL AND received_at<>'' AND received_at>='2026-01-01'"""):
            d = date.fromisoformat(rd_)
            m[d] = m.get(d, 0) + 1
        return m

    per_day = recompute()
    moved, used = 0, set()

    def borrow(d, surplus_only):
        """借一单改签到 d, 返回 (sid, 原签收日); 先借后面, 不行借前面。
        surplus_only=True 时只从当日完成数>1 的日子借, 避免拆东墙补西墙。"""
        for lo, hi in ((d + timedelta(days=1), d + timedelta(days=12)),
                       (d - timedelta(days=12), d - timedelta(days=1))):
            row = q("""SELECT shipment_id, substr(received_at,1,10) FROM shipments
                       WHERE status='已签收' AND substr(received_at,1,10) BETWEEN ? AND ?
                         AND substr(dispatched_at,1,10) < ?
                       ORDER BY ABS(julianday(received_at)-julianday(?)) LIMIT 30""",
                    lo.isoformat(), hi.isoformat(), d.isoformat(), d.isoformat())
            for sid, src in row:
                src_day = date.fromisoformat(src)
                if sid in used:
                    continue
                if surplus_only and per_day.get(src_day, 0) <= 1:
                    continue
                return sid, src_day
        return None, None

    for _ in range(6):
        progress = False
        for d in WORKDAYS:
            if per_day.get(d, 0) > 0:
                continue
            sid, src = borrow(d, surplus_only=True)
            if not sid:
                sid, src = borrow(d, surplus_only=False)
            if sid:
                cur.execute("UPDATE shipments SET received_at=? WHERE shipment_id=?",
                            (TS(d), sid))
                used.add(sid)
                per_day[d] = per_day.get(d, 0) + 1
                per_day[src] = per_day.get(src, 0) - 1
                moved += 1
                progress = True
        if not progress:
            break

    # 仍空洞的工作日: 用尚无发货的陈年积压订单补一发运当日签收
    backlog = [r[0] for r in q("""SELECT sales_order_id FROM orders
                                  WHERE sales_order_id NOT IN
                                        (SELECT DISTINCT sales_order_id FROM shipments)
                                    AND is_effective=1 ORDER BY sales_order_id""")]
    bi, backlog_filled = 0, 0
    bseq = 90001
    for d in WORKDAYS:
        if per_day.get(d, 0) > 0 or bi >= len(backlog):
            continue
        so = backlog[bi]
        bi += 1
        disp = max(W0, d - timedelta(days=R.randint(3, 10)))
        cur.execute("""INSERT INTO shipments
            (shipment_id, sales_order_id, carrier, tracking_no, quantity, unit,
             dispatched_at, carrier_promised_at, received_at, freight_cost, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            ("SH-SIM-%06d" % bseq, so, R.choice(CARRIERS),
             "SIM%012d" % R.randrange(10 ** 11, 10 ** 12), 1, "台",
             TS(disp), TS(disp + timedelta(days=5)), TS(d),
             R.choice([200, 350, 500, 800, 1200, 1800]), "已签收"))
        bseq += 1
        per_day[d] = per_day.get(d, 0) + 1
        new_ship += 1
        backlog_filled += 1
    stats["shipments"] = {"signed_backfill": signed_old, "in_transit": intransit_old,
                          "new_generated": new_ship, "moved_for_coverage": moved,
                          "backlog_filled": backlog_filled}

    # ---------- 2) exceptions 售后工单 ----------
    def close_delay():
        r = R.random()
        if r < 0.30: return 0
        if r < 0.50: return 1
        if r < 0.75: return R.randint(2, 3)
        if r < 0.90: return R.randint(4, 7)
        if r < 0.97: return R.randint(8, 14)
        return R.randint(15, 25)

    for eid, opened in q("SELECT exception_id, opened_at FROM exceptions"):
        d0 = date.fromisoformat(opened[:10])
        delay = close_delay()
        closed = d0 + timedelta(days=delay)
        if closed >= SNAP:
            cur.execute("""UPDATE exceptions SET work_order_id=?, severity=?,
                           closed_at=NULL, status='处理中' WHERE exception_id=?""",
                        ("WO-" + eid, "严重" if R.random() < 0.12 else "一般", eid))
        else:
            cur.execute("""UPDATE exceptions SET work_order_id=?, severity=?,
                           closed_at=?, status='已关闭' WHERE exception_id=?""",
                        ("WO-" + eid, "严重" if R.random() < 0.12 else "一般",
                         TS(closed), eid))

    have = {date.fromisoformat(r[0]) for r in
            q("SELECT DISTINCT substr(opened_at,1,10) FROM exceptions WHERE opened_at>='2026-01-01'")}
    added_exc = 0
    eseq = 30001
    for d in WINDOW:
        if d in have or d in HOLIDAYS:
            continue
        n = R.randint(1, 3) if d.weekday() < 5 else R.randint(1, 2)  # 周六售后值班必有工单
        for _ in range(n):
            eid = "EX-SIM-%05d" % eseq
            eseq += 1
            delay = close_delay()
            closed = d + timedelta(days=delay)
            is_open = closed >= SNAP
            cur.execute("""INSERT INTO exceptions
                (exception_id, work_order_id, exception_type, severity, opened_at,
                 closed_at, status, reason, source_record_id)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (eid, "WO-" + eid, "售后申请",
                 "严重" if R.random() < 0.12 else "一般", TS(d),
                 None if is_open else TS(closed),
                 "处理中" if is_open else "已关闭",
                 R.choice(REASONS), "SIM9M"))
            added_exc += 1
    stats["exceptions"] = {"gap_days_filled": added_exc}

    # ---------- 3) expenses 报销 ----------
    emps = [r[0] for r in q("SELECT employee_id FROM employees")]
    sos = [r[0] for r in q("""SELECT sales_order_id FROM shipments
                              WHERE received_at>='2026-01-01' AND received_at<'2026-09-20'""")]
    xseq, n_exp = 50001, 0
    for d in WINDOW:
        if d in HOLIDAYS:
            continue
        wd = d.weekday()
        n = R.randint(1, 5) if wd < 5 else (R.randint(1, 3) if wd == 5 else (0 if R.random() < 0.7 else 1))
        for _ in range(n):
            kind = pick_weighted(EXP_KINDS)[0]
            emp = R.choice(emps)
            sub = d
            age = (SNAP - sub).days
            so_ref = R.choice(sos) if (sos and R.random() < 0.25) else None
            if age <= 5:
                status, appr, paid, inv = "待审批", None, None, None
            elif age <= 12:
                status, appr, paid, inv = "已审批", TS(min(sub + timedelta(days=R.randint(1, 3)), W1)), None, None
            else:
                a = sub + timedelta(days=R.randint(1, 3))
                p = a + timedelta(days=R.randint(3, 15))
                status, appr = ("已支付", TS(a))
                paid = TS(min(p, W1))
                inv = "INV26%08d" % R.randrange(10 ** 7, 10 ** 8 - 1)
            cur.execute("""INSERT INTO expenses
                (expense_id, employee_id, department_id, sales_order_id, expense_type,
                 amount, currency, submitted_at, approved_at, paid_at, status, invoice_no)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("EXP-SIM-%05d" % xseq, emp, "D06", so_ref, kind,
                 amount_for(kind), "CNY", TS(sub), appr, paid, status, inv))
            xseq += 1
            n_exp += 1
    stats["expenses"] = {"inserted": n_exp}

    # ---------- 4) labor_logs 工时 ----------
    emps_all = emps[:]
    R.shuffle(emps_all)
    teams = {"WC01": emps_all[:9], "WC02": emps_all[9:17],
             "WC03": emps_all[17:27], "WC04": emps_all[27:36]}
    wc_dept = {"WC01": "D03", "WC02": "D02", "WC03": "D03", "WC04": "D03"}
    wc_eff = {"WC01": 0.92, "WC02": 0.90, "WC03": 0.96, "WC04": 0.90}
    rate_of = {e: round(R.uniform(28, 55), 1) for e in emps_all[:36]}
    svr_of = {e: round(R.uniform(45, 80), 1) for e in emps_all[:36]}
    wos = q("""SELECT work_order_id, sales_order_id, date(released_at), date(planned_finish_at)
               FROM work_orders WHERE released_at IS NOT NULL AND planned_finish_at IS NOT NULL""")
    wos = [(w, s, date.fromisoformat(a), date.fromisoformat(b)) for w, s, a, b in wos]

    lseq, n_lab = 70001, 0
    wc02_recent = WORKDAYS[-21:]
    for d in WORKDAYS:
        for wc, team in teams.items():
            for emp in team:
                if R.random() > 0.92:
                    continue
                actual = 4.0 if R.random() < 0.03 else round(R.uniform(7.0, 8.5), 2)
                eff = wc_eff[wc] + R.gauss(0, 0.05)
                if wc == "WC02" and d in wc02_recent:
                    k = 1 - wc02_recent.index(d) * 0.004  # 三周缓降, 最新一天 ~-8%
                    eff *= k
                eff = max(0.6, min(1.15, eff))
                wo = so = None
                cands = [x for x in wos if x[2] <= d <= x[3] + timedelta(days=20)]
                if cands:
                    wo, so = R.choice(cands)[:2]
                cur.execute("""INSERT INTO labor_logs
                    (labor_log_id, work_date, sales_order_id, work_order_id, employee_id,
                     department_id, workcenter_id, stage_code, actual_hours,
                     earned_standard_hours, hourly_rate, standard_value_rate,
                     reported_at, approved)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                    ("LL-SIM-%06d" % lseq, d.isoformat(), so, wo, emp,
                     wc_dept[wc], wc, "PROCESS", actual,
                     round(actual * eff, 2), rate_of[emp], svr_of[emp],
                     d.isoformat() + "T18:00:00+08:00"))
                lseq += 1
                n_lab += 1
    stats["labor_logs"] = {"inserted": n_lab}

    con.commit()

    # ---------- 校验: 三指标每日分布(与简报同口径) ----------
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    per_day = recompute()
    zero_workday = [d for d in WORKDAYS if per_day.get(d, 0) == 0]
    print("completion coverage workdays:", len(WORKDAYS) - len(zero_workday), "/", len(WORKDAYS),
          "empty:", [str(x) for x in zero_workday[:10]])
    comp_vals = [v for d, v in per_day.items() if d in WINDOW]
    comp_vals.sort()
    if comp_vals:
        print("completions/day min/median/max:", comp_vals[0],
              comp_vals[len(comp_vals) // 2], comp_vals[-1])
    con.close()


if __name__ == "__main__":
    main()
