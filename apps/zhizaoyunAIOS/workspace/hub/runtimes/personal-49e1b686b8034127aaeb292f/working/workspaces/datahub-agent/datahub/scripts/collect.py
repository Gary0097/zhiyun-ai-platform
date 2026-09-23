#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多源采集流程：坏样本去重/隔离 + 事件流幂等 + 采集报告

用法:
  python3 datahub/collect.py                 # 默认读取 datahub/raw，输出到 datahub/output
  python3 datahub/collect.py --raw datahub/raw --out datahub/output

产出:
  stdout                       JSON 摘要
  <out>/quarantine.jsonl       被隔离的坏样本（含原因）
  <out>/collection_log.jsonl   逐条处理日志
  <out>/collection_report.md   一页采集报告

口径:
  - WMS 库存流水业务去重键 = transaction_id（对应原始 flow_id）；重复记录忽略、不得重复记账
  - 事件流按 event_id 识别重复；"开始/完成"事件不能因业务键相同就忽略
  - 未来实际事件（晚于固定快照 2026-09-18 08:00）不得进入干净表
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

SNAPSHOT = datetime(2026, 9, 18, 8, 0, 0, tzinfo=timezone(timedelta(hours=8)))


def load_jsonl(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def read_set(db, sql):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {r[0] for r in con.execute(sql)}
    finally:
        con.close()


def find_db(explicit=None):
    cands = [explicit] if explicit else []
    cands += ["datahub/agent_data.sqlite", "agent_data.sqlite",
              "/data/actions/zhizaoyun-datahub/agent_data.sqlite"]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="datahub/raw")
    ap.add_argument("--db", default=None)
    ap.add_argument("--out", default="datahub/output")
    a = ap.parse_args()
    db = find_db(a.db)
    if not db:
        print("ERROR: agent_data.sqlite not found", file=sys.stderr)
        sys.exit(1)
    os.makedirs(a.out, exist_ok=True)

    known_tx = read_set(db, "select transaction_id from wms_transactions")
    known_so = read_set(db, "select sales_order_id from orders")
    known_sku = read_set(db, "select product_id from products")
    unit_map = {}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for pid, u in con.execute("select product_id, unit from products"):
        unit_map[pid] = u
    for mid, u in con.execute("select material_id, unit from materials"):
        unit_map[mid] = u
    con.close()

    # ---------- 1) 坏样本：去重 + 隔离 ----------
    cases = load_jsonl(os.path.join(a.raw, "ingestion_bad_cases.jsonl"))
    ignored, quarantined, accepted = [], [], []
    logs = []
    for c in cases:
        src = c.get("source", "?")
        pl = c.get("payload") or {}
        rid = str(c.get("source_record_id") or "")
        reasons = []
        if src == "WMS":
            fid = str(pl.get("flow_id") or "")
            if fid in known_tx or rid in known_tx:
                ignored.append({**c, "_reason": "重复事件（transaction_id 已存在）"})
                logs.append({"source": src, "record": rid, "action": "ignored-duplicate"})
                continue
            if float(pl.get("qty") or 0) < 0:
                reasons.append("负绝对数量")
            item = pl.get("item")
            if item in unit_map and pl.get("uom") and pl.get("uom") != unit_map[item]:
                reasons.append(f"单位冲突（源={pl.get('uom')}，库内={unit_map[item]}）")
        elif src == "ERP":
            if not pl.get("saleNo"):
                reasons.append("缺业务键（订单号为空）")
            elif pl.get("saleNo") not in known_so:
                reasons.append("未知订单（订单号不存在）")
            if pl.get("sku") and pl.get("sku") not in known_sku:
                reasons.append("未知SKU")
        elif src == "MES":
            try:
                if int(pl.get("start_ms") or 0) > int(pl.get("end_ms") or 0):
                    reasons.append("时间倒置（start > end）")
            except (TypeError, ValueError):
                pass
            v = pl.get("start_ms") or pl.get("end_ms")
            if v:
                try:
                    t = datetime.fromtimestamp(int(v) / 1000, tz=timezone(timedelta(hours=8)))
                    if t > SNAPSHOT:
                        reasons.append(f"未来实际事件（{t:%Y-%m-%d %H:%M} 晚于快照）")
                except (TypeError, ValueError, OSError):
                    reasons.append("时间戳无效")
        elif src == "OA":
            sd = str(pl.get("submitted_at") or "")
            if sd:
                try:
                    datetime.strptime(sd, "%Y-%m-%d")
                except ValueError:
                    reasons.append(f"无效日期（{sd}）")
        if reasons:
            quarantined.append({**c, "_reasons": reasons})
            logs.append({"source": src, "record": rid, "action": "quarantined", "reasons": reasons})
        else:
            accepted.append(c)
            logs.append({"source": src, "record": rid, "action": "accepted"})

    # ---------- 2) 事件流幂等统计 ----------
    main_ev = load_jsonl(os.path.join(a.raw, "event_stream.jsonl"))
    retry_ev = load_jsonl(os.path.join(a.raw, "event_stream_retry.jsonl"))
    main_ids = {e.get("event_id") for e in main_ev}
    retry_dup = [e for e in retry_ev if e.get("event_id") in main_ids]
    retry_new = [e for e in retry_ev if e.get("event_id") not in main_ids]
    # 同一业务键的"开始/完成"事件并存说明：不能按业务键一刀切去重
    bk_types = {}
    for e in main_ev:
        bk = e.get("business_key")
        bk_types.setdefault(bk, set()).add(e.get("event_type"))
    multi_state_bk = sum(1 for v in bk_types.values() if len(v) > 1)

    # ---------- 3) 写出 ----------
    with open(os.path.join(a.out, "quarantine.jsonl"), "w", encoding="utf-8") as f:
        for row in quarantined:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(os.path.join(a.out, "collection_log.jsonl"), "w", encoding="utf-8") as f:
        for row in logs:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "snapshot_at": "2026-09-18T08:00:00+08:00",
        "bad_cases_total": len(cases),
        "duplicates_ignored": len(ignored),
        "quarantined": len(quarantined),
        "accepted": len(accepted),
        "quarantine_reasons": sorted({r for q in quarantined for r in q["_reasons"]}),
        "event_stream": {
            "total": len(main_ev),
            "retry_total": len(retry_ev),
            "retry_duplicates_ignored": len(retry_dup),
            "retry_new": len(retry_new),
            "business_keys_with_multiple_states": multi_state_bk,
        },
    }
    lines = ["# 多源采集报告", "",
             f"- 固定快照：{summary['snapshot_at']}",
             f"- 坏样本共 {len(cases)} 条：**重复忽略 {len(ignored)} 条**，**隔离 {len(quarantined)} 条**，接收 {len(accepted)} 条",
             f"- 隔离原因：{('、'.join(summary['quarantine_reasons']) or '无')}",
             f"- 事件重放：主事件流 {len(main_ev)} 条；重试流 {len(retry_ev)} 条中重复忽略 {len(retry_dup)} 条、新增 {len(retry_new)} 条",
             f"- 同一业务键含多状态（开始/完成并存）的键数：{multi_state_bk}（不能按业务键一刀切去重）", "",
             "> 本报告由数据采集任务自动生成。"]
    with open(os.path.join(a.out, "collection_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
