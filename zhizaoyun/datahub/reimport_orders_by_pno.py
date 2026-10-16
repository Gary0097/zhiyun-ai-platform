#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按最新机器下单表(20260920150930.xlsx)重导订单进度看板数据。

动作:
  1) 解析表格(标准库): source_row → 生产编号/成交日期/下单时间/交货日期;
  2) 订单重键: XL-MO-%05d → 生产编号(表内重复的生产编号追加 -2/-3 后缀保持唯一),
     created_at←成交日期(缺则下单时间), promised←交货日期;
  3) 删除旧合成流转(SN-XL 节点 / SH-XL 发货)后重跑 fix_order_flow 逻辑,
     使五节点窗口与新的创建/承诺日期自洽;
  4) ingestion_runs 记录本次重导。
"""
import random
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta

DB = "/data/actions/zhizaoyun-datahub/agent_data.sqlite"
XLSX = "/tmp/machine_orders.xlsx"
SNAP_TS = "2026-09-20T08:00:00+08:00"
S_DAY = date(2026, 9, 20)
R = random.Random(20260920)

D0 = lambda d: d.strftime("%Y-%m-%dT00:00:00+08:00")
EOD = lambda d: d.strftime("%Y-%m-%dT23:59:59+08:00")
CARRIERS = ["德邦物流", "顺丰速运", "安得物流", "跨越速运", "专线自送", "盛丰物流"]
STAGES = [("PLAN", "计划", "D01", 0.00, 0.15), ("PROCESS", "加工", "D03", 0.15, 0.55),
          ("QC", "质检", "D04", 0.55, 0.65), ("SHIP", "发货", "D05", 0.65, 0.80),
          ("SIGN", "签收", "D05", 0.80, 1.00)]
WC_POOL = ["WC01"] * 5 + ["WC03"] * 3 + ["WC04"] * 2
BEI = ["待图纸", "待确认", "待回料", "待物料验收"]
JIA = ["待组装", "组装中", "待调试", "调试中"]


def xl_date(v):
    if v is None or v == "":
        return None
    try:
        return date(1899, 12, 30) + timedelta(days=int(float(v)))
    except (ValueError, TypeError):
        return None


def parse_sheet():
    """返回 {excel_row: (生产编号, 成交, 下单, 交货)}。"""
    z = zipfile.ZipFile(XLSX)
    M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    hdr, colmap = None, {}
    rows_out = {}
    for row in root.findall(".//" + M + "row"):
        cells = {}
        for c in row.findall(M + "c"):
            ref = c.get("r") or ""
            col = "".join(ch for ch in ref if ch.isalpha())
            if c.get("t") == "inlineStr":
                val = "".join(t.text or "" for t in c.iter(M + "t"))
            else:
                v = c.find(M + "v")
                val = (v.text or "") if v is not None else ""
            cells[col] = val.strip() if isinstance(val, str) else val
        rno = int("".join(ch for ch in (row.get("r") or "0") if ch.isdigit()))
        if hdr is None:
            hdr = cells
            for col, name in hdr.items():
                if name == "生产编号":
                    colmap["pno"] = col
                elif name == "成交日期":
                    colmap["deal"] = col
                elif name == "下单时间":
                    colmap["ord"] = col
                elif name == "交货日期":
                    colmap["due"] = col
            continue
        pno = cells.get(colmap.get("pno", ""), "")
        if not pno:
            continue
        rows_out[rno] = (pno, xl_date(cells.get(colmap.get("deal", ""))),
                         xl_date(cells.get(colmap.get("ord", ""))),
                         xl_date(cells.get(colmap.get("due", ""))))
    return rows_out


def pick(weights):
    x = R.random() * sum(weights)
    for i, w in enumerate(weights):
        x -= w
        if x <= 0:
            return i
    return len(weights) - 1


def phase_for(promised):
    days = (promised - S_DAY).days
    if days < -45:
        k = pick([90, 4, 2, 2, 2])
    elif days < 0:
        k = pick([50, 20, 12, 10, 8])
    else:
        k = pick([15, 35, 15, 10, 25])
    return ["done", "proc", "ship", "qc", "plan"][k]


def build_flow(cur, emps):
    orders = [dict(r) for r in cur.execute(
        "SELECT sales_order_id, quantity, unit, created_at, promised_delivery_at "
        "FROM v_current_orders ORDER BY sales_order_id")]
    sn, sh = 1, 1
    stats = {"done": 0, "proc": 0, "qc": 0, "ship": 0, "plan": 0}
    for o in orders:
        so = o["sales_order_id"]
        c = date.fromisoformat(o["created_at"][:10])
        p = date.fromisoformat((o["promised_delivery_at"] or o["created_at"])[:10])
        if (p - c).days < 7:
            p = c + timedelta(days=7)
        span = (p - c).days
        phase = phase_for(p)
        stats[phase] += 1
        if phase == "done":
            raw = "已签收"
            sign_day = min(p - timedelta(days=R.randint(0, max(1, span // 5))), S_DAY - timedelta(days=1))
            if sign_day <= c + timedelta(days=3):
                sign_day = min(c + timedelta(days=R.randint(3, min(span, 30))), S_DAY - timedelta(days=1))
        else:
            raw = {"plan": R.choice(BEI), "proc": R.choice(JIA),
                   "qc": "待验收", "ship": "待出货"}[phase]
        phase_idx = {"plan": 0, "proc": 1, "qc": 2, "ship": 3, "done": 5}[phase]
        wc = R.choice(WC_POOL)
        prev_end, rows = c, []
        for i, (code, name, dept, lo, hi) in enumerate(STAGES):
            ws = c + timedelta(days=int(span * lo))
            we = c + timedelta(days=max(int(span * hi), int(span * lo) + 1))
            if i < phase_idx:
                a_s = max(ws, prev_end + timedelta(days=1 if prev_end >= ws else 0))
                a_e = min(we, a_s + timedelta(days=max(1, (we - a_s).days // 2 + R.randint(0, 3))))
                if phase == "done":
                    a_e = min(a_e, sign_day)
                    if a_s > a_e:
                        a_s, a_e = a_e, a_e
                st, a_start, a_end = "已完成", D0(a_s), EOD(a_e)
                prev_end = a_e
            elif i == phase_idx:
                st = "进行中"
                a_start = D0(min(max(ws, S_DAY - timedelta(days=R.randint(1, 12))),
                                 S_DAY - timedelta(days=1)))
                a_end = None
                prev_end = S_DAY
            else:
                st, a_start, a_end = "未开始", None, None
            rows.append((f"SN-KL-{sn:06d}", so, code, name, i + 1, dept,
                         wc if code == "PROCESS" else None,
                         D0(ws), EOD(we), a_start, a_end, st,
                         R.choice(emps), SNAP_TS, raw))
            sn += 1
        cur.executemany("""INSERT INTO stage_nodes
            (stage_id, sales_order_id, stage_code, stage_name, sequence, department_id,
             workcenter_id, planned_start_at, planned_end_at, actual_start_at, actual_end_at,
             stage_status, owner_employee_id, updated_at, source_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
        qty, unit = o["quantity"] or 1, o["unit"] or "台"
        if phase == "done":
            disp = max(c, sign_day - timedelta(days=R.randint(1, 6)))
            cur.execute("""INSERT INTO shipments
                (shipment_id, sales_order_id, carrier, tracking_no, quantity, unit,
                 dispatched_at, carrier_promised_at, received_at, freight_cost, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (f"SH-KL-{sh:06d}", so, R.choice(CARRIERS),
                 "KL%012d" % R.randrange(10 ** 11, 10 ** 12), qty, unit,
                 D0(disp), D0(p), D0(sign_day),
                 R.choice([200, 350, 500, 800, 1200, 1800]), "已签收"))
            sh += 1
        elif phase == "ship" and R.random() < 0.4:
            disp = S_DAY - timedelta(days=R.randint(1, 5))
            cur.execute("""INSERT INTO shipments
                (shipment_id, sales_order_id, carrier, tracking_no, quantity, unit,
                 dispatched_at, carrier_promised_at, received_at, freight_cost, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (f"SH-KL-{sh:06d}", so, R.choice(CARRIERS),
                 "KL%012d" % R.randrange(10 ** 11, 10 ** 12), qty, unit,
                 D0(disp), D0(p), None, R.choice([200, 350, 500, 800]), "已发货"))
            sh += 1
    return stats


def main():
    sheet = parse_sheet()
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # 1) 重键: XL-MO → 生产编号(重复加后缀)
    renames, seen = {}, {}
    updated_dates = 0
    for r in cur.execute("SELECT sales_order_id, source_row FROM orders ORDER BY source_row"):
        row = r["source_row"]
        if row not in sheet:
            continue
        pno, deal, ordered, due = sheet[row]
        seen[pno] = seen.get(pno, 0) + 1
        new_id = pno if seen[pno] == 1 else "%s-%d" % (pno, seen[pno])
        renames[r["sales_order_id"]] = (new_id, deal, ordered, due)
    for old, (new_id, deal, ordered, due) in renames.items():
        created = deal or ordered
        if created:
            cur.execute("UPDATE orders SET sales_order_id=?, created_at=?, promised_delivery_at=?, "
                        "data_origin='真实:机器下单表_20260920150930.xlsx(订单号=生产编号)' "
                        "WHERE sales_order_id=?",
                        (new_id, D0(created), D0(due or created + timedelta(days=30)), old))
            updated_dates += 1
        else:
            cur.execute("UPDATE orders SET sales_order_id=? WHERE sales_order_id=?", (new_id, old))

    # 2) 清旧合成流转, 按新基表重建
    cur.execute("DELETE FROM stage_nodes WHERE stage_id LIKE 'SN-XL%' OR stage_id LIKE 'SN-KL%'")
    cur.execute("DELETE FROM shipments WHERE shipment_id LIKE 'SH-XL%' OR shipment_id LIKE 'SH-KL%'")
    emps = [r[0] for r in cur.execute("SELECT employee_id FROM employees")]
    stats = build_flow(cur, emps)

    cur.execute("""INSERT INTO ingestion_runs
        (run_id, source_system, run_at, input_record_count, loaded_record_count,
         quarantined_record_count, run_status, sync_mode, watermark, note)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        ("run-rekey-20260920", "机器下单表_20260920150930.xlsx(重导)", "2026-09-20T18:30:00+08:00",
         len(sheet), len(renames), 0, "成功(订单号=生产编号)", "全量重建",
         "2026-09-20", "订单号由内部序号重键为表内生产编号;重复生产编号加-2/-3后缀;流转五节点按成交/交期重建"))
    con.commit()

    print("重键订单:", len(renames), "| 日期刷新:", updated_dates, "| 重复后缀:", sum(1 for v in seen.values() if v > 1))
    print("流转位相:", stats)
    for r in cur.execute("SELECT sales_order_id, customer_id, promised_delivery_at FROM orders ORDER BY source_row LIMIT 3"):
        print("  ", r["sales_order_id"], r["customer_id"], r["promised_delivery_at"][:10])
    kpi = cur.execute("""WITH s AS (SELECT sales_order_id, COUNT(*) b,
        SUM(CASE WHEN status='已签收' AND received_at<>'' THEN 1 ELSE 0 END) g
        FROM shipments GROUP BY 1)
        SELECT (SELECT COUNT(*) FROM v_current_orders),
               (SELECT COUNT(*) FROM v_current_orders o JOIN s USING(sales_order_id) WHERE s.g=s.b)""").fetchone()
    print("KPI: 生效 %d / 已完成 %d" % tuple(kpi))
    con.close()


if __name__ == "__main__":
    main()
