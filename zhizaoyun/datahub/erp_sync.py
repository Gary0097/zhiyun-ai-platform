#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ERP 销售合同直连同步(金汉隆 数据中枢)。

数据中枢订单数据直连系统服务(zbintel117_erp, SQL Server):
  1) 拉取「销售合同」全量列表(自动发现表与列: 表名含 合同/Contract, 列含 名称/编号/客户/金额/日期);
  2) 按「合同名称」匹配本地订单(订单基表=机器下单表, 合同名称=合同信息列, 即 公司-日期-业务员),
     归一化精确匹配 → 客户+日期包含匹配;
  3) 同步结果: 补全/校正 orders.contract_name 与 contract_no, 缓存于 erp_contracts;
  4) 血缘写 ingestion_runs。
连接参数可用环境变量覆盖: ERP_HOST/ERP_PORT/ERP_DB/ERP_USER/ERP_PASS。
用法: python3 erp_sync.py            # 立即同步
      python3 erp_sync.py --status   # 查看最近同步状态
"""
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

DB = os.environ.get("DH_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_data.sqlite"))
ERP_HOST = os.environ.get("ERP_HOST", "192.167.30.7")
ERP_PORT = int(os.environ.get("ERP_PORT", "1433"))
ERP_DB = os.environ.get("ERP_DB", "zbintel117_erp")
ERP_USER = os.environ.get("ERP_USER", "zbmlthftij")
ERP_PASS = os.environ.get("ERP_PASS", "zMLbTHiQYnLAtFTeIJl")

NAME_HINTS = ("合同名称", "名称")
NO_HINTS = ("合同编号", "合同号", "编号", "单号", "code", "Code")
CUST_HINTS = ("客户", "往来", "单位", "供应商")
AMT_HINTS = ("金额", "价税", "含税")
DATE_HINTS = ("签订", "日期", "date", "Date")


def norm(s):
    return re.sub(r"[\s\-_/／()（）:：,，.。]+", "", str(s or "")).upper()


def connect():
    import pymssql
    return pymssql.connect(server=ERP_HOST, port=ERP_PORT, user=ERP_USER,
                           password=ERP_PASS, database=ERP_DB,
                           timeout=15, login_timeout=10, charset="utf8",
                           tds_version=os.environ.get("ERP_TDS", "7.0"))


EXPLICIT = {"schema": "dbo", "table": "contract",
            "colmap": {"name": "title", "no": "htid", "amt": "money1",
                       "date": "date1", "cust": "company"}}


def discover(con):
    """返回 (schema, table, colmap)。优先 销售合同 命名的表。"""
    try:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME=%s", ("contract",))
        if cur.fetchone()[0]:
            return EXPLICIT["schema"], EXPLICIT["table"], dict(EXPLICIT["colmap"])
    except Exception:  # noqa: BLE001
        pass
    tables = [r[0] for r in con.execute(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'").fetchall()]
    cands = sorted({t for t in tables if "合同" in t or "contract" in t.lower()},
                   key=lambda t: (0 if "销售" in t else 1, len(t)))
    if not cands:
        raise RuntimeError("ERP 中未发现含「合同/Contract」的表, 可用表: %s" % ", ".join(tables[:30]))
    for t in cands:
        schema = next((s for s, tt in
                       [(r[0], r[1]) for r in con.execute(
                           "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES").fetchall()]
                       if tt == t), "dbo")
        cols = [r[0] for r in con.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s", (schema, t)).fetchall()]
        colmap = {}
        for c in cols:
            if any(h in c for h in NAME_HINTS) and "name" not in colmap:
                colmap["name"] = c
        for key, hints in (("no", NO_HINTS), ("cust", CUST_HINTS),
                           ("amt", AMT_HINTS), ("date", DATE_HINTS)):
            for c in cols:
                if any(h in c for h in hints) and key not in colmap:
                    colmap[key] = c
                    break
        if "name" in colmap:
            return schema, t, colmap, cols
    raise RuntimeError("候选表 %s 中均无「名称」列" % ", ".join(cands))


def fetch_contracts():
    con = connect()
    try:
        schema, table, colmap = discover(con)
        sql = 'SELECT %s FROM [%s].[%s]' % (
            ", ".join("[%s]" % colmap[k] for k in ("name", "no", "amt", "date")), schema, table)
        cur = con.cursor()
        cur.execute(sql)
        out = []
        for r in cur.fetchall():
            out.append({"name": r[0], "no": r[1], "amt": r[2], "date": r[3]})
        return {"schema": schema, "table": table, "colmap": colmap,
                "count": len(out), "rows": out}
    finally:
        con.close()


def sync(verbose=True):
    report = {"ok": False, "started_at": datetime.now().isoformat(timespec="seconds")}
    try:
        data = fetch_contracts()
    except Exception as e:  # noqa: BLE001
        report["error"] = str(e)[:400]
        return report
    def g(row, *keys):
        for k in keys:
            v = row.get(k, "")
            if v:
                return v
        return ""
    now = datetime.now().isoformat(timespec="seconds")
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS erp_contracts (
        contract_no TEXT, contract_name TEXT, customer_name TEXT, amount REAL,
        signed_at TEXT, extra_json TEXT, synced_at TEXT,
        UNIQUE(contract_no, contract_name))""")
    upserted = 0
    erp_norm = {}
    for row in data["rows"]:
        cname = str(g(row, "name") or "").strip()
        if not cname:
            continue
        cno = str(g(row, "no") or "").strip()
        cust = str(g(row, "cust") or "").strip()
        amt = g(row, "amt")
        try:
            amt = float(amt) if amt not in ("", None) else None
        except (TypeError, ValueError):
            amt = None
        sdate = str(g(row, "date") or "")[:19]
        cur.execute("""INSERT INTO erp_contracts
            (contract_no, contract_name, customer_name, amount, signed_at, extra_json, synced_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(contract_no, contract_name) DO UPDATE SET
              customer_name=excluded.customer_name, amount=excluded.amount,
              signed_at=excluded.signed_at, extra_json=excluded.extra_json,
              synced_at=excluded.synced_at""",
            (cno, cname, cust, amt, sdate,
             json.dumps({"date": str(g(row, "date"))[:19]}, ensure_ascii=False), now))
        upserted += 1
        erp_norm.setdefault(norm(cname), (cname, cno, cust))
    # 匹配订单: 主键=合同编号(归一化精确), 兜底=合同名称归一化/客户+日期包含
    erp_no = {}
    for n, (cn, cno_, cu) in erp_norm.items():
        if cno_:
            erp_no.setdefault(norm(cno_), (cn, cno_, cu))
    matched = updated_no = 0
    for so, local_name, local_no in cur.execute(
            "SELECT sales_order_id, contract_name, contract_no FROM orders").fetchall():
        hit = erp_no.get(norm(local_no or "")) or erp_norm.get(norm(local_name or ""))
        if not hit and local_name:
            cust = (local_name.split("-")[0] or "").strip()
            date_frag = next((p for p in local_name.split("-") if re.match(r"\d{4}-\d{2}-\d{2}", p)), "")
            if cust and date_frag:
                for n, (cn, cno_, cu) in erp_norm.items():
                    if norm(cust) in n and date_frag.replace("-", "") in n.replace("-", ""):
                        hit = (cn, cno_, cu)
                        break
        if hit:
            matched += 1
            cur.execute("UPDATE orders SET contract_name=?, contract_no=COALESCE(NULLIF(?,''), contract_no) "
                        "WHERE sales_order_id=?", (hit[0], hit[1], so))
            updated_no += 1
    cur.execute("""INSERT INTO ingestion_runs
        (run_id, source_system, run_at, input_record_count, loaded_record_count,
         quarantined_record_count, run_status, sync_mode, watermark, note)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        ("run-erp-contracts-" + datetime.now().strftime("%Y%m%d%H%M%S"),
         "ERP:%s.%s" % (ERP_DB, data["table"]), report["started_at"],
         data["count"], upserted, 0, "成功", "增量upsert", now,
         "销售合同直连同步; 表=%s.%s; 列映射=%s; 按合同名称匹配订单 %d 单(补编号 %d)"
         % (data["schema"], data["table"], json.dumps(data["colmap"], ensure_ascii=False), matched, updated_no)))
    con.commit()
    total = cur.execute("SELECT COUNT(*) FROM erp_contracts").fetchone()[0]
    con.close()
    report.update({"ok": True, "table": "%s.%s" % (data["schema"], data["table"]),
                   "colmap": data["colmap"], "pulled": data["count"], "upserted": upserted,
                   "orders_matched": matched, "orders_no_filled": updated_no,
                   "cached_total": total})
    return report


def status():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = [dict(zip([c[0] for c in con.execute("SELECT * FROM ingestion_runs LIMIT 0").description],
                     r)) for r in con.execute(
        "SELECT * FROM ingestion_runs WHERE source_system LIKE 'ERP:%' ORDER BY run_at DESC LIMIT 3")]
    try:
        cached = con.execute("SELECT COUNT(*) FROM erp_contracts").fetchone()[0]
    except sqlite3.OperationalError:
        cached = 0
    con.close()
    return {"erp": "%s:%s/%s" % (ERP_HOST, ERP_PORT, ERP_DB), "cached_contracts": cached, "runs": rows}


if __name__ == "__main__":
    if "--status" in sys.argv:
        print(json.dumps(status(), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(sync(), ensure_ascii=False, indent=1))
