# -*- coding: utf-8 -*-
"""订单底表存储（SQLite，本地卷持久化）。"""
import json
import os
import sqlite3
import threading
import time
import uuid

DB_PATH = os.environ.get("OC_DB", "/app/data/orders.db")
_lock = threading.Lock()
_conn = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  so_no TEXT,
  mo_no TEXT,
  created_at TEXT,
  source_filename TEXT,
  source_type TEXT,
  raw_text TEXT,
  parsed_json TEXT,
  adapted_json TEXT,
  template TEXT,
  customer TEXT,
  product TEXT,
  quantity REAL,
  unit TEXT,
  due_date TEXT,
  cost REAL,
  status TEXT,
  warnings TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC);
"""


def init_db(path=None):
    global _conn
    p = path or DB_PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    _conn = sqlite3.connect(p, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.executescript(SCHEMA)
    # ERP 推送状态列：历史订单默认“已正确推送”（erp_pushed=1）
    cols = {r[1] for r in _conn.execute("PRAGMA table_info(orders)").fetchall()}
    with _lock:
        if "erp_pushed" not in cols:
            _conn.execute("ALTER TABLE orders ADD COLUMN erp_pushed INTEGER NOT NULL DEFAULT 1")
        if "erp_pushed_at" not in cols:
            _conn.execute("ALTER TABLE orders ADD COLUMN erp_pushed_at TEXT")
        _conn.execute("UPDATE orders SET erp_pushed_at=COALESCE(erp_pushed_at, created_at) WHERE erp_pushed=1")
    _conn.commit()
    return _conn


def push_erp(oid):
    """标记订单为已推送 ERP（幂等），返回最新状态。"""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _lock:
        cur = _conn.execute(
            "UPDATE orders SET erp_pushed=1, erp_pushed_at=? WHERE id=?", (now, oid))
        _conn.commit()
        if cur.rowcount == 0:
            return None
    r = _conn.execute(
        "SELECT id, so_no, erp_pushed, erp_pushed_at FROM orders WHERE id=?", (oid,)).fetchone()
    return dict(r)


def conn():
    if _conn is None:
        init_db()
    return _conn


def next_seq(day_prefix):
    """当日序号（SO/MO 共用，按已存在订单顺延）。"""
    with _lock:
        row = conn().execute(
            "SELECT COUNT(*) c FROM orders WHERE so_no LIKE ?", (day_prefix + "%",)).fetchone()
    return (row["c"] or 0) + 1


def make_numbers(now=None):
    t = time.localtime(now or time.time())
    prefix = "SO%04d%02d%02d" % (t.tm_year, t.tm_mon, t.tm_mday)
    n = next_seq(prefix)
    so = "%s-%04d" % (prefix, n)
    mo = so.replace("SO", "MO", 1)
    return so, mo


def get_order_by_so(so_no):
    r = conn().execute("SELECT * FROM orders WHERE so_no=?", (so_no,)).fetchone()
    return dict(r) if r else None


def existing_so_nos():
    with _lock:
        rows = conn().execute("SELECT so_no FROM orders WHERE so_no IS NOT NULL AND so_no<>''").fetchall()
    return {r["so_no"] for r in rows}


def save_order(rec):
    with _lock:
        conn().execute(
            """INSERT INTO orders (id, so_no, mo_no, created_at, source_filename, source_type,
               raw_text, parsed_json, adapted_json, template, customer, product, quantity, unit,
               due_date, cost, status, warnings)
               VALUES (:id,:so_no,:mo_no,:created_at,:source_filename,:source_type,:raw_text,
               :parsed_json,:adapted_json,:template,:customer,:product,:quantity,:unit,
               :due_date,:cost,:status,:warnings)""", rec)
        conn().commit()
    return rec["id"]


def list_orders(limit=200):
    rows = conn().execute(
        "SELECT id, so_no, mo_no, created_at, source_filename, source_type, template, customer,"
        " product, quantity, unit, due_date, cost, status, warnings, erp_pushed, erp_pushed_at"
        " FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_order(oid):
    r = conn().execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    for k in ("parsed_json", "adapted_json", "warnings"):
        try:
            d[k] = json.loads(d[k]) if d[k] else ([] if k == "warnings" else {})
        except Exception:  # noqa: BLE001
            d[k] = [] if k == "warnings" else {}
    return d


def delete_order(oid):
    with _lock:
        cur = conn().execute("DELETE FROM orders WHERE id=?", (oid,))
        conn().commit()
    return cur.rowcount > 0


def stats():
    c = conn()
    total = c.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    by_tpl = c.execute("SELECT template t, COUNT(*) c FROM orders GROUP BY template").fetchall()
    cost = c.execute("SELECT COALESCE(SUM(cost),0) s FROM orders").fetchone()["s"]
    return {"total": total,
            "by_template": {r["t"] or "未分类": r["c"] for r in by_tpl},
            "total_cost": round(cost or 0, 2)}


def new_id():
    return uuid.uuid4().hex[:12]
