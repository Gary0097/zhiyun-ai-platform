#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智能采购·功能15 只读查询 API + 看板托管（127.0.0.1:18110）
- GET  /health        健康检查
- GET  /api/dashboard 看板数据（库存预警/供应商评分/补货建议）
- POST /api/sql       {"sql": "SELECT ..."} 只读查询（禁多语句/禁写）
- GET  /               dashboard/ 静态页面
"""
import json
import os
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "agent_data.sqlite")
DASH = os.path.join(ROOT, "dashboard")
PORT = int(os.environ.get("PURCHASE_PORT", "18110"))
BIND = os.environ.get("PURCHASE_BIND", "127.0.0.1")
MAX_ROWS = 2000
SQL_RE = re.compile(r"(?is)^\s*(select|with|pragma\s+(table_info|foreign_key_list|table_list))\b")

# ---- 多企业演示：按访问 IP(Host 头) 切换企业库；未配置时行为不变 ----
import sys as _sys
_kit = os.environ.get("ENTERPRISE_KIT")
if _kit and os.path.isdir(_kit) and _kit not in _sys.path:
    _sys.path.insert(0, _kit)
try:
    import enterprise_selector as _ent
except Exception:
    _ent = None


def ent_db():
    if _ent is not None:
        p = _ent.db_path("purchase_agent_data.sqlite")
        if p:
            return p
    return DB


def db():
    con = sqlite3.connect(f"file:{ent_db()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def q(sql, args=()):
    con = db()
    try:
        cur = con.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def dashboard_payload():
    snap = q("SELECT 参数值 FROM calc_params WHERE 参数名='snapshot_at'")
    snapshot_at = snap[0]["参数值"] if snap else None
    alerts = q("SELECT * FROM v_inventory_alert ORDER BY 缺口数量 DESC")
    advice = q("SELECT * FROM v_replenishment_advice ORDER BY 建议补货量 DESC, 缺口数量 DESC")
    recs = q("SELECT * FROM v_supplier_recommendation ORDER BY 物料名称, 排名")
    by_sku = {}
    for r in recs:
        by_sku.setdefault(r["物料名称"], []).append(r)
    for a in advice:
        rs = by_sku.get(a["物料名称"], [])
        a["供应商推荐"] = rs
        a["主荐"] = rs[0] if rs else None
        a["需比价"] = bool(rs and rs[0].get("价格校验不通过") == "是")
        a["无合格候选"] = not rs
        a["是否需下单"] = a["建议补货量"] > 0
    need_order = sum(1 for a in advice if a["是否需下单"])
    pending_manual = sum(1 for a in advice if a["无合格候选"])
    transit_cov = sum(1 for a in advice if not a["是否需下单"])
    summary = {
        "预警SKU数": len(alerts),
        "需下单SKU数": need_order,
        "在途覆盖免下单": transit_cov,
        "转人工SKU数": pending_manual,
        "比价提示数": sum(1 for a in advice if a["需比价"]),
        "供应商总数": q("SELECT COUNT(*) c FROM supplier_master")[0]["c"],
        "启用SKU数": q("SELECT COUNT(*) c FROM material_master")[0]["c"],
        "近180天到货批次": q("SELECT COUNT(*) c FROM arrival_records WHERE 状态='已到货' AND date(到货日期)>=date((SELECT 参数值 FROM calc_params WHERE 参数名='snapshot_at'),'-180 day')")[0]["c"],
    }
    scores = q("""SELECT 供应商编码, 供应商名称, 所在地, 供应类别, 近180天到货批次, 准时率, 合格率, 价格竞争力,
                  ROUND(综合评分,4) AS 综合评分 FROM v_supplier_score
                  WHERE 近180天到货批次 > 0 ORDER BY 综合评分 DESC, 准时率 DESC""")
    return {"snapshot_at": snapshot_at, "summary": summary, "alerts": alerts,
            "advice": advice, "scores": scores, "note": "演示评分，未校准；只读数据，发送仅限 Mock"}


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, payload, ctype="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/health":
            try:
                c = q("SELECT COUNT(*) c FROM v_inventory_alert")[0]["c"]
                snap = q("SELECT 参数值 FROM calc_params WHERE 参数名='snapshot_at'")[0]["参数值"]
                return self._send(200, {"ok": True, "mode": "READ_ONLY", "snapshot_at": snap, "alert_count": c})
            except Exception as exc:
                return self._send(500, {"ok": False, "error": str(exc)})
        if p == "/api/params":
            try:
                return self._send(200, {"params": q("SELECT 参数名, 参数值, 说明 FROM calc_params")})
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        if p == "/api/dashboard":
            try:
                return self._send(200, dashboard_payload())
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        rel = (p.lstrip("/") or "index.html")
        fp = os.path.normpath(os.path.join(DASH, rel))
        if fp.startswith(DASH) and os.path.isfile(fp):
            with open(fp, "rb") as f:
                data = f.read()
            ct = ("text/html; charset=utf-8" if fp.endswith(".html")
                  else "application/javascript; charset=utf-8" if fp.endswith(".js")
                  else "text/css; charset=utf-8" if fp.endswith(".css")
                  else "image/svg+xml" if fp.endswith(".svg")
                  else "application/octet-stream")
            return self._send(200, data, ct)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/sql":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) or b"{}"
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("gbk", "replace")
            body = json.loads(text)
            sql = (body.get("sql") or "").strip()
        except Exception as exc:
            return self._send(400, {"error": f"bad request: {exc}"})
        if not SQL_RE.match(sql):
            return self._send(400, {"error": "only read-only SELECT/PRAGMA allowed"})
        if ";" in sql.rstrip().rstrip(";"):
            return self._send(400, {"error": "multiple statements not allowed"})
        try:
            con = db()
            cur = con.execute(sql)
            rows = [dict(r) for r in cur.fetchmany(MAX_ROWS)]
            cols = [d[0] for d in cur.description] if cur.description else []
            con.close()
            return self._send(200, {"columns": cols, "rows": rows, "row_count": len(rows),
                                    "truncated": len(rows) >= MAX_ROWS})
        except Exception as exc:
            return self._send(400, {"error": str(exc)})


if __name__ == "__main__":
    # 多企业：每个请求先按 Host 头记录企业上下文，再走原逻辑
    if _ent is not None:
        def _wrap_enterprise(orig):
            def inner(self, *a, **k):
                _ent.set_host(self.headers.get("Host"))
                return orig(self, *a, **k)
            return inner
        for _m in ("do_GET", "do_POST", "do_OPTIONS"):
            _orig = getattr(H, _m, None)
            if _orig is not None:
                setattr(H, _m, _wrap_enterprise(_orig))
    srv = ThreadingHTTPServer((BIND, PORT), H)
    print(f"Purchase API on {BIND}:{PORT}, db={DB}"
          + (" [enterprise-mode]" if _ent is not None else ""), flush=True)
    srv.serve_forever()
