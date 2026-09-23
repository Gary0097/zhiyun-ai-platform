#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日经营简报（前一自然日）生成 + Mock推送
口径: 完成=全量签收; 新增异常工单=当日 opened 的工单去重; 日末未关闭=日末时点仍开放(opened<=EOD 且 未关闭或关闭时间>EOD)的工单去重; 报销按 submitted_at 当日去重.
用法: python3 daily_brief.py [--db PATH] [--date YYYY-MM-DD] [--no-push]
默认报告日 = 快照日期的前一天; 推送 Mock: http://127.0.0.1:18765/api/mock/wechat/push
"""
import argparse
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta

WB_PUSH = "http://127.0.0.1:18765/api/mock/wechat/push"


def find_db(explicit=None):
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [explicit] if explicit else []
    cands += [
        os.path.join(here, "agent_data.sqlite"),
        os.path.join(os.getcwd(), "agent_data.sqlite"),
        os.path.join(os.getcwd(), "datahub", "agent_data.sqlite"),
        "/data/actions/zhizaoyun-datahub/agent_data.sqlite",
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    raise SystemExit("agent_data.sqlite not found")


def out_dir():
    cands = [os.path.join(os.getcwd(), "datahub", "output"),
             os.path.join(os.path.dirname(os.path.abspath(__file__)), "output"),
             "/data/actions/zhizaoyun-datahub/output"]
    for c in cands:
        try:
            os.makedirs(c, exist_ok=True)
            return c
        except Exception:
            continue
    return "."


def run(db, report_day=None):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    q = lambda s, *a: con.execute(s, a).fetchall()
    snap = q("SELECT config_value FROM configuration WHERE config_key='snapshot_at'")[0][0]
    if not report_day:
        snap_date = snap[:10]
        report_day = (datetime.strptime(snap_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    D = report_day
    EOD = D + "T23:59:59+08:00"

    completed = q("""
WITH lr AS (SELECT sales_order_id, MAX(received_at) last_at, COUNT(*) batches,
       SUM(CASE WHEN status='已签收' AND received_at IS NOT NULL AND received_at<>'' THEN 1 ELSE 0 END) signed
       FROM shipments GROUP BY sales_order_id)
SELECT sales_order_id, last_at FROM lr WHERE signed=batches AND last_at LIKE ? || '%'""", D)
    new_wo = q("SELECT COUNT(DISTINCT work_order_id) FROM exceptions WHERE opened_at LIKE ? || '%'", D)[0][0]
    open_wo = q("""SELECT COUNT(DISTINCT work_order_id) FROM exceptions
WHERE opened_at<=? AND (closed_at IS NULL OR closed_at='' OR closed_at>?)""", EOD, EOD)[0][0]
    reimb = q("SELECT COUNT(*), ROUND(COALESCE(SUM(amount),0),2) FROM expenses WHERE submitted_at LIKE ? || '%'", D)[0]

    unfinished = q("""
WITH lr AS (SELECT sales_order_id, COUNT(*) batches,
       SUM(CASE WHEN status='已签收' AND received_at IS NOT NULL AND received_at<>'' THEN 1 ELSE 0 END) signed
       FROM shipments GROUP BY sales_order_id)
SELECT
 SUM(CASE WHEN s.sales_order_id IS NULL OR s.signed < s.batches THEN 1 ELSE 0 END),
 SUM(CASE WHEN (s.sales_order_id IS NULL OR s.signed < s.batches) AND o.promised_delivery_at < ? THEN 1 ELSE 0 END)
FROM v_current_orders o LEFT JOIN lr s ON s.sales_order_id=o.sales_order_id
WHERE (s.sales_order_id IS NULL OR s.signed < s.batches)""", snap)[0]

    eff = q("SELECT COUNT(*) FROM v_current_orders")[0][0]
    done = q("""
WITH lr AS (SELECT sales_order_id, COUNT(*) batches,
       SUM(CASE WHEN status='已签收' AND received_at IS NOT NULL AND received_at<>'' THEN 1 ELSE 0 END) signed
       FROM shipments GROUP BY sales_order_id)
SELECT COUNT(*) FROM v_current_orders o JOIN lr s ON s.sales_order_id=o.sales_order_id WHERE s.signed=s.batches""")[0][0]

    # WC02 人效（近7有作业日 vs 前7）
    eff_rows = q("""SELECT work_date, SUM(earned_standard_hours), SUM(actual_hours)
FROM labor_logs WHERE workcenter_id='WC02' GROUP BY work_date ORDER BY work_date""")
    series = [se / sa for wd, se, sa in eff_rows if sa]
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0
    r7, p7 = mean(series[-7:]), mean(series[-14:-7])
    chg = (r7 / p7 - 1) * 100 if p7 else 0.0
    con.close()

    lines = [
        "【经营日报｜%s】" % D,
        "· 全量交付 %d 单（完成=全部批次签收）" % len(completed),
        "· 新增异常工单 %d 单；日末未关闭异常工单 %d 单（工单去重）" % (new_wo, open_wo),
        "· 报销提交 %d 笔，金额 %.2f 元" % (reimb[0], reimb[1]),
        "· 当前未全量交付 %d 单（其中已逾期 %d 单）；已生效订单 %d 单、累计全量签收 %d 单" % (unfinished[0], unfinished[1], eff, done),
        "· 加工二组WC02人效近7个有作业日均值 %.6f，较前7日 %.6f 变化 %.2f%%（下降需结合设备停机日志核查）" % (r7, p7, chg),
    ]
    brief = "\n".join(lines)
    if completed:
        brief += "\n· 当日完成订单：" + "、".join(r[0] for r in completed)
    result = {
        "report_date": D, "snapshot_at": snap,
        "completed_orders": len(completed), "completed_list": [r[0] for r in completed],
        "new_abnormal_work_orders": new_wo, "open_abnormal_work_orders_eod": open_wo,
        "reimbursement_count": reimb[0], "reimbursement_amount": reimb[1],
        "unfinished_orders": unfinished[0], "overdue_unfinished": unfinished[1],
        "effective_orders": eff, "completed_total": done,
        "wc02_recent7": round(r7, 6), "wc02_prev7": round(p7, 6), "wc02_change_pct": round(chg, 2),
        "brief": brief,
    }
    return result


def push(result, date_key):
    body = {
        "idempotency_key": "daily-brief-%s" % date_key,
        "recipient_group": "WB_MANAGEMENT",
        "content": result["brief"],
    }
    req = urllib.request.Request(WB_PUSH, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    ap.add_argument("--date", help="报告日 YYYY-MM-DD（默认=快照日前一天）")
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()
    db = find_db(args.db)
    result = run(db, args.date)

    d = out_dir()
    md = os.path.join(d, "daily_brief_%s.md" % result["report_date"])
    with open(md, "w", encoding="utf-8") as f:
        f.write(result["brief"] + "\n")
    result["saved_to"] = md

    if not args.no_push:
        try:
            result["push"] = push(result, result["report_date"].replace("-", ""))
        except Exception as e:
            result["push"] = {"error": str(e)}
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
