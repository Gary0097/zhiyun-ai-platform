#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读 SQL 查询 agent_data.sqlite（金汉隆智能采购·计算副本）

用法:
  python3 procurement/scripts/query.py "SELECT * FROM v_inventory_alert"
  python3 procurement/scripts/query.py --json "SELECT ..."     # JSON 输出（默认表格）
  python3 procurement/scripts/query.py --db /path/agent_data.sqlite "SELECT ..."
  echo "SELECT ..." | python3 procurement/scripts/query.py

说明: 只读连接（mode=ro），默认最多返回 200 行；写操作会报错（库本身只读）。
"""
import argparse
import json
import os
import sqlite3
import sys


def find_db(explicit=None):
    cands = []
    if explicit:
        cands.append(explicit)
    if os.environ.get("PURCHASE_DB"):
        cands.append(os.environ["PURCHASE_DB"])
    here = os.path.dirname(os.path.abspath(__file__))
    cands += [
        os.path.join(os.getcwd(), "procurement", "agent_data.sqlite"),
        os.path.join(os.getcwd(), "agent_data.sqlite"),
        os.path.join(here, "agent_data.sqlite"),
        os.path.join(os.path.dirname(here), "agent_data.sqlite"),
        "/data/actions/zhizaoyun-purchase/agent_data.sqlite",
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sql", nargs="?", help="SQL 语句（SELECT/PRAGMA；留空则从 stdin 读）")
    ap.add_argument("--db")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    sql = args.sql or sys.stdin.read()
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        print("ERROR: empty sql", file=sys.stderr)
        sys.exit(1)
    low = sql.lower().lstrip()
    if not (low.startswith("select") or low.startswith("with") or low.startswith("pragma")):
        print("ERROR: only read-only SELECT/PRAGMA allowed", file=sys.stderr)
        sys.exit(1)

    db = find_db(args.db)
    if not db:
        print("ERROR: agent_data.sqlite not found (use --db or set PURCHASE_DB)", file=sys.stderr)
        sys.exit(1)

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(sql)
        rows = [dict(r) for r in cur.fetchmany(args.limit)]
        cols = [d[0] for d in cur.description] if cur.description else []
    except sqlite3.Error as exc:
        print(f"SQL ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        con.close()

    if args.json:
        print(json.dumps({"columns": cols, "rows": rows, "row_count": len(rows)},
                         ensure_ascii=False, default=str, indent=1))
    else:
        print(" | ".join(cols))
        print("-" * 40)
        for r in rows:
            print(" | ".join("" if r[c] is None else str(r[c]) for c in cols))
        print(f"({len(rows)} rows)")


if __name__ == "__main__":
    main()
