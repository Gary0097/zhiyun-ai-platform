#!/usr/bin/env huoban
# -*- coding: utf-8 -*-
"""伙伴云(Huoban) CRM 直连同步 — 金汉隆数据中台。

认证: Open-Authorization: Bearer {KEY}
端点: POST /openapi/v1/item/list  (table_id + offset/limit 分页)
四张表: 机器下单表/合同表/售后申请表/业务客户池
"""
import json
import os
import sqlite3
import urllib.request
from datetime import datetime

API = "https://api.huoban.com"
KEY = os.environ.get("HUOBAN_KEY", "AWjFOuCJI7pHhdNwgrH4Pp94h2KhZYDIyP2Eclwd")
DB = os.environ.get("DH_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_data.sqlite"))

TABLES = {
    "机器下单表": 2100000040343389,
    "合同表": 2100000021209270,
    "售后申请表": 2100000040438114,
    "业务客户池": 2100000052668950,
}


def _call(ep, body):
    req = urllib.request.Request(API + ep, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Open-Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_stats():
    """拉取各表总数与最新条目(轻量, 供融合页展示)。"""
    out = {}
    for name, tid in TABLES.items():
        try:
            d = _call("/openapi/v1/item/list", {"table_id": tid, "limit": 1, "offset": 0})
            data = d.get("data") or {}
            out[name] = {"table_id": tid, "total": data.get("total", 0),
                         "ok": d.get("code") == 0}
        except Exception as e:  # noqa: BLE001
            out[name] = {"table_id": tid, "total": 0, "ok": False, "error": str(e)[:80]}
    return out


def fetch_recent(table_name, limit=50):
    """拉取指定表最近条目(含字段值, 用于预览)。"""
    tid = TABLES.get(table_name)
    if not tid:
        return []
    d = _call("/openapi/v1/item/list", {"table_id": tid, "limit": limit, "offset": 0})
    return (d.get("data") or {}).get("items") or []


def sync_stats():
    """同步统计写入 SQLite(供看板展示), 返回报告。"""
    stats = fetch_stats()
    now = datetime.now().isoformat(timespec="seconds")
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS crm_live_stats (
        table_name TEXT PRIMARY KEY, table_id INTEGER, total INTEGER,
        ok INTEGER, error TEXT, synced_at TEXT)""")
    for name, s in stats.items():
        cur.execute("""INSERT INTO crm_live_stats(table_name, table_id, total, ok, error, synced_at)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(table_name) DO UPDATE SET total=excluded.total, ok=excluded.ok,
              error=excluded.error, synced_at=excluded.synced_at""",
            (name, s["table_id"], s["total"], 1 if s["ok"] else 0, s.get("error", ""), now))
    cur.execute("""INSERT INTO ingestion_runs
        (run_id, source_system, run_at, input_record_count, loaded_record_count,
         quarantined_record_count, run_status, sync_mode, watermark, note)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        ("run-crm-" + datetime.now().strftime("%Y%m%d%H%M%S"), "CRM:伙伴云API",
         now, sum(s["total"] for s in stats.values()), len(stats), 0,
         "成功" if all(s["ok"] for s in stats.values()) else "部分成功",
         "统计同步", now,
         "伙伴云直连: " + "; ".join("%s=%d条" % (n, s["total"]) for n, s in stats.items())))
    con.commit()
    con.close()
    return {"ok": all(s["ok"] for s in stats.values()), "tables": stats, "synced_at": now}


if __name__ == "__main__":
    print(json.dumps(sync_stats(), ensure_ascii=False, indent=1))
