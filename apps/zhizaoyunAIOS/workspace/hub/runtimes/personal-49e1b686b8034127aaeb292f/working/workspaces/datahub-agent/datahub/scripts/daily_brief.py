#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日经营简报（前一自然日）生成 + Mock推送
口径: 完成=全量签收; 新增异常工单=当日 opened 的工单去重; 日末未关闭=日末时点仍开放(opened<=EOD 且 未关闭或关闭时间>EOD)的工单去重; 报销按 submitted_at 当日去重.
用法: python3 daily_brief.py [--db PATH] [--date YYYY-MM-DD] [--no-push] [--force] [--status]
默认报告日 = 快照日期的前一天; 推送 Mock: http://127.0.0.1:18765/api/mock/wechat/push

本地幂等（同一天只出一份日报）:
  1) claim 文件 output/.daily_brief_<key>.claim —— 认领即生效，防并发/重复触发重复计算与覆盖 md；
  2) 发送账本 output/daily_brief_ledger.jsonl —— 记录每次真实推送结果，可审计；
  3) Mock 服务端 idempotency_key=daily-brief-<YYYYMMDD> —— 最后一道防线。
  推送失败会自动释放 claim，允许当日重试；确需重发用 --force。
"""
import argparse
import json
import os
import socket
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

WB_PUSH = "http://127.0.0.1:18765/api/mock/wechat/push"
CST = timezone(timedelta(hours=8))
# Mock 服务端这些状态都代表"消息已在 outbox"，视为已发送
PUSHED_OK = {"saved_to_local_outbox", "sent", "queued", "duplicate_ignored"}


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


def now_cst():
    return datetime.now(CST).isoformat(timespec="seconds")


def claim_file(d, date_key):
    """date_key = 报告日 YYYYMMDD（不含 daily-brief- 前缀）。"""
    return os.path.join(d, ".daily_brief_%s.claim" % date_key)


def ledger_file(d):
    return os.path.join(d, "daily_brief_ledger.jsonl")


def read_ledger(d):
    recs, p = [], ledger_file(d)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except Exception:
                    pass
    return recs


def append_ledger(d, rec):
    with open(ledger_file(d), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def claim(d, date_key):
    """原子认领当日日报。返回 (claimed, existing_info)。"""
    p = claim_file(d, date_key)
    info = {"idempotency_key": "daily-brief-%s" % date_key, "claimed_at": now_cst(),
            "pid": os.getpid(), "host": socket.gethostname()}
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            with open(p, encoding="utf-8") as f:
                info = json.load(f)
        except Exception:
            pass
        return False, info
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False)
    return True, info


def release(d, date_key):
    try:
        os.remove(claim_file(d, date_key))
    except OSError:
        pass


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
    ap.add_argument("--force", action="store_true", help="忽略本地幂等，强制重算重发（会覆盖 md）")
    ap.add_argument("--status", action="store_true", help="只查当日幂等状态，不生成不推送")
    args = ap.parse_args()

    d = out_dir()
    db = find_db(args.db)

    # 报告日先确定（不查库无法定 key），用一次轻量只读查询拿快照
    if args.date:
        report_day = args.date
    else:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        snap = con.execute("SELECT config_value FROM configuration WHERE config_key='snapshot_at'").fetchone()[0]
        con.close()
        report_day = (datetime.strptime(snap[:10], "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    date_key = report_day.replace("-", "")
    key = "daily-brief-%s" % date_key
    md = os.path.join(d, "daily_brief_%s.md" % report_day)
    prior_push = [r for r in read_ledger(d)
                  if r.get("idempotency_key") == key and r.get("push_status") in PUSHED_OK]

    if args.status:
        print(json.dumps({"idempotency_key": key, "report_date": report_day,
                          "claimed": os.path.isfile(claim_file(d, date_key)),
                          "md_exists": os.path.isfile(md), "md_path": md,
                          "ledger_pushes": prior_push}, ensure_ascii=False, indent=1))
        return

    already = os.path.isfile(claim_file(d, date_key))
    if already and not args.force:
        print(json.dumps({
            "report_date": report_day, "idempotency_key": key,
            "skipped": "already_generated",
            "reason": "当日日报已生成并处理过（本地认领存在），本次为重复触发：未重算、未覆盖 md、未推送。",
            "md_path": md if os.path.isfile(md) else None,
            "ledger_pushes": prior_push,
            "hint": "确需重发请加 --force",
        }, ensure_ascii=False, indent=1))
        return

    if not already or args.force:
        claimed, _ = claim(d, date_key)
        if not claimed and not args.force:
            print(json.dumps({"report_date": report_day, "idempotency_key": key,
                              "skipped": "concurrent_run",
                              "reason": "另一进程已认领当日日报。"}, ensure_ascii=False, indent=1))
            return

    result = run(db, report_day)

    with open(md, "w", encoding="utf-8") as f:
        f.write(result["brief"] + "\n")
    result["saved_to"] = md
    result["idempotency_key"] = key

    if not args.no_push:
        try:
            resp = push(result, date_key)
            result["push"] = resp
            status = resp.get("status", "unknown")
        except Exception as e:
            result["push"] = {"error": str(e)}
            status = "error"
            release(d, date_key)  # 失败释放认领，允许当日重试
        append_ledger(d, {"idempotency_key": key, "report_date": report_day,
                          "pushed_at": now_cst(), "push_status": status,
                          "message_id": (result["push"] or {}).get("message_id"),
                          "md_path": md, "force": bool(args.force)})
    else:
        release(d, date_key)  # 未推送不占用认领
        result["push"] = {"status": "skipped_no_push"}

    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
