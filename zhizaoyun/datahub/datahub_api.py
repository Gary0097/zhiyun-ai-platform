#!/usr/bin/env python3
"""DataHub 只读查询 API + 看板静态托管（0.0.0.0:18790，局域网可达）— 按 PRD v1.0 契约实现

- GET  /health            健康检查 {ok, mode, snapshot_at}
- POST /api/ask           {"question": "一句话问题"} AI 生成只读 SQL 并执行（智能问数）
- POST /api/sql           {"sql": "SELECT ..."} 只读查询（禁多语句/禁写），支持 CORS 与 OPTIONS 预检
- GET  /api/dashboard     KPI + 五节点汇总(含超时/最近更新) + 风险分布 + 生产状态分布 + 接入状态 + 小组汇总
- GET  /api/order-progress 订单节点查询：sales_order_id / stage_code / workcenter_id /
                           stage_status / deadline_state / limit(默认200) / cursor
- GET  /api/trends?workcenter_id=WCxx  生产小组人效趋势；无工时数据返回 待接入
- GET  /api/ingestion/status 数据接入状态
- GET  /api/daily-brief/latest 早报三项指标
- GET  /api/daily-brief/history?days=30 近N天逐日简报(完成/新增异常/日末未关闭/报销+完成订单清单)
- GET  /api/erp/contracts?q=    ERP 销售合同缓存列表(按合同名称/编号/客户过滤)
- POST /api/erp/contracts-sync  直连 ERP 同步销售合同并按合同名称匹配订单
- POST /api/daily-brief/generate {"date":"YYYY-MM-DD","force":bool} 一键生成当日简报(md+台账+消息通道推送)
- GET  /                  dashboard/ 静态文件（index.html 交互看板 / snapshot.html 静态存档 / sql.html 查询台）
"""
import json
import os
import re
import sqlite3
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
import erp_sync
DB = os.environ.get("DATAHUB_DB", os.path.join(ROOT, "agent_data.sqlite"))

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
    """当前请求企业的 agent_data.sqlite；无企业上下文时回退默认库。"""
    if _ent is not None:
        p = _ent.db_path("agent_data.sqlite")
        if p:
            return p
    return DB
DASH = (os.path.join(ROOT, "dashboard")
       if os.path.isdir(os.path.join(ROOT, "dashboard"))
       else os.path.join(ROOT, "dashboard_local"))
PORT = int(os.environ.get("DATAHUB_PORT", "18790"))
ENT_NAME = os.environ.get("ENT_NAME", "")
ENT_COLOR = os.environ.get("ENT_COLOR", "")
FEATURES_FILE = os.environ.get("ENT_FEATURES_FILE", os.path.join(ROOT, "ent_features.json"))
# 数据中枢标准功能项(用于"未开通"对比展示)
HUB_STD_ITEMS = ["实时客户订单进度看板", "客户交付风险智能预警", "多源数据自动采集",
                 "跨部门数据融合加工", "企业关键数据日看板", "关键指标趋势分析"]


def ent_features_block():
    """企业实例: 按合同功能清单生成版本/模块/导航裁剪信息"""
    if not ENT_NAME:
        return None
    try:
        with open(FEATURES_FILE, encoding="utf-8") as f:
            cfg = json.load(f).get(ENT_NAME)
    except Exception:
        return None
    if not cfg:
        return None
    feats = cfg.get("features", [])
    modules = []
    for r in feats:
        if not modules or modules[-1]["name"] != r["module"]:
            modules.append({"name": r["module"], "groups": []})
        if not modules[-1]["groups"] or modules[-1]["groups"][-1]["name"] != r["group"]:
            modules[-1]["groups"].append({"name": r["group"], "items": []})
        modules[-1]["groups"][-1]["items"].append(r["item"])
    total = len(feats)
    version = "旗舰版" if total >= 30 else ("专业版" if total >= 24 else "标准版")
    hub_items = {r["item"] for r in feats if r["group"] == "数据整合与分析引擎"}
    pages = {
        "progress": True, "query": True,
        "risk": "客户交付风险智能预警" in hub_items,
        "collect": "多源数据自动采集" in hub_items,
        "fusion": "跨部门数据融合加工" in hub_items,
        "brief": "企业关键数据日看板" in hub_items,
        "trend": "关键指标趋势分析" in hub_items,
    }
    locked = [i for i in HUB_STD_ITEMS if i not in hub_items]
    return {"version": version, "total": total, "modules": modules,
            "pages": pages, "locked": locked}
BIND = os.environ.get("DATAHUB_BIND", "0.0.0.0")
MAX_ROWS = 2000
DEFAULT_PAGE = 200          # PRD 4.2：查询结果默认 200 条

# ---- 智能问数 LLM 配置（OpenAI 兼容网关）----
LLM_BASE = os.environ.get("DATAHUB_LLM_BASE", "http://api.computing.lzwcai.com:3110/v1")
LLM_KEY = os.environ.get("DATAHUB_LLM_KEY", "")
LLM_MODEL = os.environ.get("DATAHUB_LLM_MODEL", "deepseek-v4-flash")
LLM_FALLBACK_MODEL = os.environ.get("DATAHUB_LLM_FALLBACK_MODEL", "qwen3.8-flash")
ASK_MAX_ROWS = 200

SCHEMA_PROMPT = """为只读 SQLite 写查询：金汉隆包装机械厂订单数据（快照时点在 configuration 表 snapshot_at，约2026-09-20）。
表：
- v_current_orders(已生效订单): sales_order_id 订单号, contract_no 合同号, customer_id, packaged_goods 包装产品, quantity 数量, contract_amount 金额, created_at 下单时间, promised_delivery_at 承诺交期, sales_owner 业务员
- contracts: contract_no, customer_name 客户, sales_owner 业务员, signed_at 成交日期, contract_amount 合同金额, received_amount 已收款, unpaid_amount 未收款, final_payment 尾款
- stage_nodes(订单节点): sales_order_id, stage_code(PLAN计划/PROCESS加工/QC质检/SHIP发货/SIGN签收), stage_status(已完成/进行中/未开始), workcenter_id(WC01多列装配/WC02电工/WC03调试/WC04装盒部), planned_end_at, source_status 生产"当天状态"原文(待回料/待出货/待调试/待图纸/待验收等)
- shipments(发货): sales_order_id, dispatched_at 出货, received_at 签收, status(已签收/已发货)
- customers: customer_name, province, city, industry, sales_owner
- procurement_lines(采购): sales_order_id, material_id, required_quantity, ordered_at, promised_receipt_at
- inventory_snapshot(库存快照2026-09-18,一物料一行): material_id, 库位, 物料名称, 规格型号, 机型, 上月库存, 当月入库, 当月出库, 当月返工入仓, 当月返工出仓, 当天库存, 备货数, 库存预警(充足/库存不足/库存归零)
- wms_transactions(库存流水,长表): material_id, movement_type(期初结转/入库/出库/返工入仓/返工出仓), signed_quantity(出库/返工出仓为负数), occurred_at, reference_id(含 库位/序号/几号)
- v_inventory_balance(当前结存): material_id, quantity_balance=SUM(signed_quantity), 应等于 inventory_snapshot.当天库存
- exceptions(售后): opened_at, status, reason
- configuration: config_key, config_value
规则：
1. 超时=planned_end_at<(SELECT config_value FROM configuration WHERE config_key='snapshot_at')且stage_status<>'已完成'
2. 未交付=shipments里无status='已签收'运单
3. 时间是ISO文本，用字符串比较或date()
4. 只输出一条SELECT/WITH语句，无分号无解释
5. 明细加LIMIT 50，统计不用
6. 列名用中文别名"""


def call_llm(messages, timeout=90, max_tokens=600):
    """主模型 deepseek-v4-flash；鉴权/模型不可用时自动回退到备用模型。"""
    msgs = list(messages)
    msgs[0] = {"role": "system", "content": msgs[0]["content"] + "\n/no_think"}
    last_err = None
    for model in (LLM_MODEL, LLM_FALLBACK_MODEL):
        if not model:
            continue
        body = json.dumps({"model": model, "messages": msgs,
                           "temperature": 0, "max_tokens": max_tokens}).encode()
        req = urllib.request.Request(
            LLM_BASE + "/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + LLM_KEY})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode())
            if "choices" not in d:
                raise RuntimeError(str(d.get("error") or d)[:120])
            content = d["choices"][0]["message"]["content"] or ""
            call_llm.used_model = model
            return content
        except Exception as exc:
            last_err = f"{model}: {str(exc)[:100]}"
    raise RuntimeError(last_err or "no LLM configured")


def extract_sql(text):
    text = (text or "").strip()
    m = re.search(r"```(?:sql)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    text = text.strip().strip("`").strip()
    text = re.sub(r";\s*$", "", text)
    return text


def run_ask(question):
    """自然语言 → LLM 生成只读 SQL → 校验执行（失败带错误重试一次）。"""
    started = datetime.now()
    messages = [
        {"role": "system", "content": SCHEMA_PROMPT},
        {"role": "user", "content": question},
    ]
    last_err = None
    for attempt in (1, 2):
        try:
            raw = call_llm(messages)
        except Exception as exc:
            return {"error": f"大模型调用失败：{exc}"}
        sql = extract_sql(raw)
        if not SQL_RE.match(sql) or ";" in sql:
            last_err = "生成语句未通过只读校验"
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content":
                             "该语句不是合法的只读 SELECT（或含多语句/分号）。请重新输出一条符合规则的 SQLite SELECT 语句，只输出 SQL 本身。"})
            continue
        try:
            con = db()
            cur = con.execute(sql)
            rows = [dict(r) for r in cur.fetchmany(ASK_MAX_ROWS)]
            cols = [d[0] for d in cur.description] if cur.description else []
            con.close()
            return {"question": question, "sql": sql, "model": getattr(call_llm, "used_model", LLM_MODEL),
                    "columns": cols, "rows": rows, "row_count": len(rows),
                    "truncated": len(rows) >= ASK_MAX_ROWS, "attempts": attempt,
                    "elapsed_ms": int((datetime.now() - started).total_seconds() * 1000)}
        except Exception as exc:
            last_err = str(exc)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content":
                             f"执行报错：{last_err}。请修正后重新输出一条 SQLite SELECT 语句，只输出 SQL 本身。"})
    return {"error": f"AI 生成的 SQL 执行失败：{last_err}", "question": question}

SQL_RE = re.compile(r"(?is)^\s*(select|with|pragma\s+(table_info|foreign_key_list|table_list))\b")

# PRD 4.4：生产总表原始状态 → 展示位相（映射仅用于展示，原文保留在 stage_nodes.source_status）
PHASE_MAP = {
    "待图纸": "备料/图纸/确认", "待确认": "备料/图纸/确认", "待业务确认": "备料/图纸/确认",
    "待回料": "备料/图纸/确认", "待物料验收": "备料/图纸/确认",
    "待组装": "加工/调试", "组装中": "加工/调试", "待调试": "加工/调试", "调试中": "加工/调试",
    "待验收": "验收", "待出货": "待出货", "已签收": "已完成",
}
PHASE_ORDER = ["备料/图纸/确认", "加工/调试", "待出货", "验收", "已完成", "其他/待确认"]


def db():
    con = sqlite3.connect(f"file:{ent_db()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def snapshot_value(con):
    r = con.execute("select config_value from configuration where config_key='snapshot_at'").fetchone()
    return r[0] if r else None


def risk_lines(snap_iso):
    day = datetime.fromisoformat(snap_iso).date()
    return ((day + timedelta(days=7)).isoformat(),
            (day + timedelta(days=30)).isoformat())


def deadline_state(stage_status, planned_end, snap_iso, red_line_iso, month_start=None):
    """PRD 超时规则（与交付风险预警同口径）：
    快照当月之前的历史结转节点不计超时；无计划日期判「待排程」。"""
    if stage_status == "已完成":
        return "已完成"
    if not planned_end:
        return "待排程"
    ms = month_start or (snap_iso[:8] + "01")
    if planned_end < ms:
        return "历史结转"
    if planned_end < snap_iso:
        return "超时"
    if planned_end[:10] < red_line_iso:
        return "即将到期"
    return "按期"


SHIP_BASE = """
WITH s AS (
  SELECT sales_order_id, COUNT(*) AS batches,
         SUM(CASE WHEN status='已签收' AND received_at IS NOT NULL AND received_at<>'' THEN 1 ELSE 0 END) AS signed
  FROM shipments GROUP BY sales_order_id)
"""

# 2026 法定假日(用于简报明细展示标记, 与 simulate_9m_usage.py 口径一致)
_BRIEF_HOLIDAYS = {"2026-01-01", "2026-01-02", "2026-01-03",
                   "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19",
                   "2026-02-20", "2026-02-21", "2026-02-22",
                   "2026-04-04", "2026-04-05", "2026-04-06",
                   "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05",
                   "2026-06-19", "2026-06-20", "2026-06-21",
                   "2026-09-25", "2026-09-26", "2026-09-27"}
_WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def daily_brief_history(days=30):
    """近 N 天(默认30, 上限92)逐日经营简报: 与 daily_brief.py 同口径。
    完成=全量签收; 新增异常=当日 opened 去重; 日末未关闭=时点开放; 报销按 submitted_at。"""
    try:
        days = min(max(int(days), 1), 92)
    except (TypeError, ValueError):
        days = 30
    con = db()
    try:
        snap = snapshot_value(con)
        end = datetime.fromisoformat(snap[:10]).date() - timedelta(days=1)
        start = end - timedelta(days=days - 1)
        out = []
        d = start
        while d <= end:
            D = d.isoformat()
            EOD = D + "T23:59:59+08:00"
            completed = [r[0] for r in con.execute("""
WITH lr AS (SELECT sales_order_id, MAX(received_at) last_at, COUNT(*) batches,
       SUM(CASE WHEN status='已签收' AND received_at IS NOT NULL AND received_at<>'' THEN 1 ELSE 0 END) signed
       FROM shipments GROUP BY sales_order_id)
SELECT sales_order_id FROM lr WHERE signed=batches AND last_at LIKE ? || '%'""", (D,)).fetchall()]
            new_wo = con.execute("SELECT COUNT(DISTINCT work_order_id) FROM exceptions WHERE opened_at LIKE ? || '%'",
                                 (D,)).fetchone()[0]
            open_wo = con.execute("""SELECT COUNT(DISTINCT work_order_id) FROM exceptions
WHERE opened_at<=? AND (closed_at IS NULL OR closed_at='' OR closed_at>?)""",
                                  (EOD, EOD)).fetchone()[0]
            reimb = con.execute("SELECT COUNT(*), ROUND(COALESCE(SUM(amount),0),2) FROM expenses WHERE submitted_at LIKE ? || '%'",
                                (D,)).fetchone()
            out.append({"date": D, "weekday": _WEEKDAY_CN[d.weekday()],
                        "holiday": D in _BRIEF_HOLIDAYS,
                        "completed": len(completed), "completed_orders": completed,
                        "new_exceptions": new_wo, "open_eod": open_wo,
                        "reimb_count": reimb[0], "reimb_amount": reimb[1]})
            d += timedelta(days=1)
        totals = {"completed": sum(r["completed"] for r in out),
                  "new_exceptions": sum(r["new_exceptions"] for r in out),
                  "reimb_count": sum(r["reimb_count"] for r in out),
                  "reimb_amount": round(sum(r["reimb_amount"] for r in out), 2)}
        return {"snapshot_at": snap, "report_date": end.isoformat(), "days": days,
                "rows": out, "totals": totals, "today": _brief_today_detail(con, end.isoformat(), snap),
                "rule": "完成=全部批次签收；新增异常=当日 opened 去重；日末未关闭=日末时点仍开放；报销按 submitted_at"}
    finally:
        con.close()


def _brief_today_detail(con, D, snap):
    """报告日客户动态与交付信息(简报页右栏)。"""
    delivered = [dict(r) for r in con.execute("""
        SELECT sh.sales_order_id AS order_id,
               COALESCE(c.customer_name, o.packaged_goods, '（未关联客户）') AS customer,
               COALESCE(o.quantity, sh.quantity, 1) AS qty,
               ROUND(COALESCE(o.contract_amount, 0), 0) AS amount
        FROM shipments sh
        LEFT JOIN orders o ON o.sales_order_id = sh.sales_order_id
        LEFT JOIN customers c ON o.customer_id = c.customer_id
        WHERE sh.received_at LIKE ? || '%'
        ORDER BY amount DESC""", (D,)).fetchall()]
    dmap = {}
    for r in delivered:
        a = dmap.setdefault(r["customer"], {"name": r["customer"], "orders": 0, "amount": 0.0})
        a["orders"] += 1
        a["amount"] += r["amount"]
    new_orders = [dict(r) for r in con.execute("""
        SELECT COALESCE(c.customer_name, o.packaged_goods, '（未关联客户）') AS name,
               COUNT(*) AS orders, ROUND(SUM(COALESCE(o.contract_amount, 0)), 0) AS amount
        FROM orders o LEFT JOIN customers c ON o.customer_id = c.customer_id
        WHERE o.created_at LIKE ? || '%'
        GROUP BY 1 ORDER BY amount DESC LIMIT 8""", (D,)).fetchall()]
    dispatched = con.execute("SELECT COUNT(*) FROM shipments WHERE dispatched_at LIKE ? || '%'",
                             (D,)).fetchone()[0]
    in_transit = con.execute("SELECT COUNT(*) FROM shipments WHERE status='已发货'").fetchone()[0]
    unfinished = con.execute(SHIP_BASE + """
        SELECT COUNT(*), SUM(CASE WHEN o.promised_delivery_at < ? THEN 1 ELSE 0 END)
        FROM v_current_orders o LEFT JOIN s USING(sales_order_id)
        WHERE s.sales_order_id IS NULL OR s.signed < s.batches""", (snap,)).fetchone()
    return {"date": D,
            "delivered_customers": sorted(dmap.values(), key=lambda x: -x["amount"]),
            "deliveries": delivered,
            "new_order_customers": new_orders,
            "dispatched_today": dispatched, "in_transit_total": in_transit,
            "unfinished": unfinished[0], "overdue": unfinished[1] or 0}


def generate_daily_brief(date_str=None, force=False):
    """一键生成: 复用 daily_brief.py(幂等 claim + 台账 + 统一消息通道推送)。"""
    import subprocess
    import sys
    cmd = [sys.executable, os.path.join(ROOT, "daily_brief.py")]
    if date_str:
        cmd += ["--date", date_str]
    if force:
        cmd += ["--force"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=ROOT)
    try:
        payload = json.loads(proc.stdout.strip())
    except (ValueError, json.JSONDecodeError):
        return {"ok": False, "returncode": proc.returncode,
                "error": (proc.stderr.strip() or proc.stdout.strip())[-800:]}
    if "brief" not in payload and payload.get("md_path"):
        try:
            with open(payload["md_path"], encoding="utf-8") as f:
                payload["brief"] = f.read().strip()
        except OSError:
            pass
    payload["ok"] = proc.returncode == 0
    return payload


def render_snapshot():
    """企业实例静态快照页: 按当前企业库实时渲染(替代旧全局金汉隆存档)"""
    d = dashboard_data()
    k = d.get("kpis") or {}
    risk = d.get("risk") or {}
    stages = d.get("stages") or []
    brief = d.get("brief") or {}
    brand = ENT_COLOR or "#C7000B"
    name = ENT_NAME or "智造云平台"
    snap = (d.get("snapshot_at") or "")[:19].replace("T", " ")
    total_risk = max(1, (risk.get("red") or 0) + (risk.get("yellow") or 0) + (risk.get("green") or 0))

    def rbar(label, val, color):
        w = (val or 0) / total_risk * 500
        return (f'<text x="0" y="18" font-size="13" fill="#1F2329">{label}</text>'
                f'<rect x="150" y="0" width="{w:.1f}" height="26" rx="4" fill="{color}"/>'
                f'<text x="{658 if w >= 8 else 158 + w:.0f}" y="18" font-size="13" fill="#646A73">{val or 0}</text>')

    rows = ""
    for s in stages:
        rows += (f'<tr><td>{s.get("stage_name") or s.get("stage_code")}</td>'
                 f'<td>{s.get("total", 0)}</td><td>{s.get("completed", 0)}</td>'
                 f'<td>{s.get("running", 0)}</td>'
                 f'<td style="color:#C7000B">{s.get("overdue", 0)}</td></tr>')
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} AI数据中枢 · 经营快照</title>
<style>:root{{--brand:{brand}}}
*{{box-sizing:border-box}} body{{margin:0;font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif;background:#F5F6F7;color:#1F2329}}
.top{{background:linear-gradient(90deg,{brand},{brand}cc);color:#fff;padding:20px 28px}} .top h1{{margin:0;font-size:18px}}
.wrap{{max-width:1080px;margin:18px auto;padding:0 16px 40px}}
.card{{background:#fff;border-radius:10px;padding:16px 18px;margin-bottom:12px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap}} .kpi{{flex:1;min-width:150px;background:#fff;border-radius:10px;padding:14px 18px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.kpi-label{{font-size:12px;color:#646A73}} .kpi-value{{font-size:26px;font-weight:600;margin-top:4px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{border-bottom:1px solid #F0F0F0;padding:7px 9px;text-align:left}}
th{{color:#646A73;font-weight:500}} .sub{{margin-top:5px;font-size:12px;opacity:.9}} .hint{{color:#646A73;font-size:12px}}
h2{{font-size:15px;margin:0 0 10px}}</style></head>
<body><div class="top"><h1>{name} AI数据中枢 · 经营快照</h1>
<div class="sub">数据时点 {snap}（北京时间） · {name}经营数据 · 只读存档</div></div>
<div class="wrap"><div class="kpis">
<div class="kpi"><div class="kpi-label">已生效订单</div><div class="kpi-value" style="color:#1F2329">{k.get("effective_orders",0)} 单</div></div>
<div class="kpi"><div class="kpi-label">已全量签收</div><div class="kpi-value" style="color:#2E8B57">{k.get("completed_orders",0)} 单</div></div>
<div class="kpi"><div class="kpi-label">未全量交付</div><div class="kpi-value" style="color:#D48806">{k.get("unfinished_orders",0)} 单</div></div>
<div class="kpi"><div class="kpi-label">其中已逾期</div><div class="kpi-value" style="color:#C7000B">{k.get("overdue_orders",0)} 单</div></div></div>
<div class="card"><h2>交付风险分布</h2><div class="hint" style="margin-bottom:8px">{risk.get("rule","")}</div>
<svg width="100%" viewBox="0 0 760 108" preserveAspectRatio="xMidYMid meet">
<g>{rbar("高风险（红）", risk.get("red"), "#C7000B")}</g>
<g transform="translate(0,36)">{rbar("中风险（黄）", risk.get("yellow"), "#D48806")}</g>
<g transform="translate(0,72)">{rbar("低风险（绿）", risk.get("green"), "#2E8B57")}</g></svg></div>
<div class="card"><h2>五节点汇总</h2><table><thead><tr><th>节点</th><th>总数</th><th>已完成</th><th>进行中</th><th>逾期</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<div class="card"><h2>今日经营简报</h2><div class="hint">{brief.get("text") or brief.get("summary") or "暂无简报，可在协同看板生成。"}</div></div>
<div class="card"><div class="hint">静态快照由 {name} 专属实例实时渲染 · 交互看板：<a href="./" style="color:var(--brand)">协同看板</a> · <a href="sql.html" style="color:var(--brand)">SQL 查询台</a></div></div>
</div></body></html>"""
    return html


def dashboard_data():
    con = db()
    try:
        q = lambda sql, args=(): [dict(r) for r in con.execute(sql, args).fetchall()]
        snap = snapshot_value(con)
        red_line, yellow_line = risk_lines(snap)

        # KPI（与静态快照页同一口径）
        effective = con.execute("SELECT COUNT(*) FROM v_current_orders").fetchone()[0]
        completed = con.execute(SHIP_BASE + """
            SELECT COUNT(*) FROM v_current_orders o JOIN s USING(sales_order_id)
            WHERE s.signed = s.batches""").fetchone()[0]
        rows = con.execute(SHIP_BASE + """
            SELECT o.sales_order_id, o.promised_delivery_at FROM v_current_orders o
            LEFT JOIN s USING(sales_order_id)
            WHERE (s.signed IS NULL OR s.signed < s.batches)""").fetchall()
        risk = {"red": 0, "yellow": 0, "green": 0}
        overdue = 0
        # 风险窗口口径：仅统计快照当月及以后的交期；当月之前的旧订单多为已交付/
        # 历史结转，不再计入风险预警（旧逾期单据可在 SQL 查询台按交期自查）
        month_start = snap[:8] + "01"
        excluded_historical = 0
        for r in rows:
            p = r["promised_delivery_at"]
            if p and p < month_start:
                excluded_historical += 1
                continue
            if p and p < snap:
                risk["red"] += 1
                overdue += 1
            elif p and p < red_line:
                risk["red"] += 1
            elif p and p < yellow_line:
                risk["yellow"] += 1
            else:
                risk["green"] += 1
        risk["rule"] = ("高=本月内已逾期或7天内到期；中=8–30天；低=超过30天或暂无承诺交期；"
                        f"{month_start[:7]} 之前的旧交期订单（{excluded_historical} 单）不计入")
        risk["as_of"] = snap

        # 五节点汇总（PRD 4.1：名称/总数/完成与完成率/进行中/未开始/超时/最近更新）
        stages = q("""
            SELECT stage_code, MAX(stage_name) stage_name,
                   COUNT(*) total,
                   SUM(CASE WHEN stage_status='已完成' THEN 1 ELSE 0 END) completed,
                   SUM(CASE WHEN stage_status='进行中' THEN 1 ELSE 0 END) running,
                   SUM(CASE WHEN stage_status='未开始' THEN 1 ELSE 0 END) pending,
                   SUM(CASE WHEN planned_end_at IS NOT NULL AND planned_end_at < ?
                             AND planned_end_at >= ? AND stage_status <> '已完成' THEN 1 ELSE 0 END) overdue,
                   SUM(CASE WHEN planned_end_at IS NOT NULL AND planned_end_at < ?
                             AND stage_status <> '已完成' THEN 1 ELSE 0 END) historical_carryover,
                   MAX(updated_at) last_updated_at
            FROM stage_nodes GROUP BY stage_code ORDER BY MIN(sequence)""", (snap, snap[:8] + "01", snap[:8] + "01"))
        for s in stages:
            s["completion_rate"] = round(s["completed"] / s["total"] * 100, 1) if s["total"] else 0

        # 生产订单状态分布（PRD 4.4：位相映射 + 原文保留）
        raw = q("""
            SELECT source_status, COUNT(DISTINCT sales_order_id) n
            FROM stage_nodes WHERE stage_code='PLAN' AND source_status IS NOT NULL
            GROUP BY source_status ORDER BY n DESC""")
        dist = {p: 0 for p in PHASE_ORDER}
        for r in raw:
            dist[PHASE_MAP.get(r["source_status"], "其他/待确认")] += r["n"]
        status_distribution = {
            "phases": [{"phase": p, "orders": dist[p]} for p in PHASE_ORDER],
            "raw_status": raw,
            "rule": "映射自生产总表当天状态原文（stage_nodes.source_status），仅用于展示不覆盖原始事实",
            "extraction": {"loaded": sum(r["n"] for r in raw), "source_total": 1228,
                           "note": "生产进度总表 1228 行中已结构化 87 单（去重后），其余排产表已并入节点数据"},
        }

        # 数据接入与血缘（PRD 4.5）
        ingestion = q("""
            SELECT run_id, source_system, run_at, input_record_count, loaded_record_count,
                   quarantined_record_count,
                   CASE WHEN run_status LIKE '%成功%' OR run_status LIKE '%完成%' THEN '已完成'
                        WHEN run_status LIKE '%部分%' OR run_status LIKE '%OCR%' THEN '处理中'
                        WHEN run_status LIKE '%待OCR%' THEN '待OCR'
                        WHEN run_status LIKE '%待%' THEN '待接入'
                        ELSE '需关注' END AS status,
                   run_status AS raw_status, note
            FROM ingestion_runs ORDER BY run_id""")

        # 生产小组汇总（PRD 4.6：无工时数据 → 待接入）
        wcs = q("""
            SELECT w.workcenter_id, w.workcenter_name,
                   COUNT(DISTINCT CASE WHEN n.stage_code='PROCESS' THEN n.sales_order_id END) active_orders
            FROM workcenters w LEFT JOIN stage_nodes n USING(workcenter_id)
            GROUP BY w.workcenter_id ORDER BY w.workcenter_id""")
        labor_rows = con.execute("SELECT COUNT(*) FROM labor_logs").fetchone()[0]
        for w in wcs:
            w["productivity_status"] = "待接入" if labor_rows == 0 else "可用"

        fusion = q("""
            SELECT workcenter_id,
                   ROUND(SUM(earned_standard_hours),2) standard_hours,
                   ROUND(SUM(actual_hours),2) actual_hours,
                   ROUND(SUM(earned_standard_hours)/NULLIF(SUM(actual_hours),0),4) productivity,
                   ROUND(SUM(earned_standard_hours*standard_value_rate),2) work_value
            FROM labor_logs GROUP BY workcenter_id ORDER BY workcenter_id""")
        fusion_status = "待接入" if labor_rows == 0 else "可用"

        report_day = q("SELECT date(?, '-1 day') value", (snap[:10],))[0]["value"]

        def _brief_for(day):
            return q("""
                SELECT
                  (SELECT COUNT(DISTINCT sh.sales_order_id) FROM shipments sh
                   WHERE sh.received_at LIKE ? || '%'
                     AND NOT EXISTS (SELECT 1 FROM shipments sh2
                                     WHERE sh2.sales_order_id=sh.sales_order_id
                                       AND (sh2.received_at IS NULL OR sh2.received_at=''))
                  ) AS completed_order_count,
                  (SELECT COUNT(*) FROM exceptions WHERE opened_at LIKE ? || '%') AS exception_count,
                  (SELECT COUNT(*) FROM expenses WHERE submitted_at LIKE ? || '%') AS reimbursement_count,
                  (SELECT ROUND(COALESCE(SUM(amount),0),2) FROM expenses WHERE submitted_at LIKE ? || '%') AS reimbursement_amount
                """, (day, day, day, day))[0]

        brief = _brief_for(report_day)
        brief_note = ""
        # 快照重建后当日可能无流水: 回退到最近有活动的交易日
        if not (brief["completed_order_count"] or brief["exception_count"] or brief["reimbursement_count"]):
            last_active = q("""SELECT MAX(substr(received_at,1,10)) d FROM shipments
                               WHERE received_at IS NOT NULL AND received_at < ?""", (snap,))[0]["d"]
            if last_active:
                brief = _brief_for(last_active)
                brief_note = f"（{report_day} 无交付流水，回退至最近交付日 {last_active}）"
                report_day = last_active
        brief["note"] = brief_note

        # 口径统计: 订单来源分布 + 各底表行数(与SQL查询台可互验)
        order_sources = {r[0] or '未标注': r[1] for r in con.execute(
            "SELECT order_source, COUNT(*) FROM orders WHERE is_effective=1 GROUP BY 1 ORDER BY 2 DESC")}
        t_contracts = con.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
        t_erp = con.execute("SELECT COUNT(*) FROM erp_contracts").fetchone()[0] if [r for r in con.execute(
            "SELECT name FROM sqlite_master WHERE name='erp_contracts'")] else 0
        t_cust = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        t_ship = con.execute("SELECT COUNT(*) FROM shipments").fetchone()[0]
        t_ex_open = con.execute("SELECT COUNT(*) FROM exceptions WHERE status='处理中'").fetchone()[0]
        t_ex_closed = con.execute("SELECT COUNT(*) FROM exceptions WHERE status='已关闭'").fetchone()[0]
        t_inv = con.execute("SELECT COUNT(*) FROM inventory_snapshot").fetchone()[0]

        return {"snapshot_at": snap, "risk_lines": {"red": red_line, "yellow": yellow_line},
                "kpis": {"effective_orders": effective, "completed_orders": completed,
                         "unfinished_orders": effective - completed, "overdue_orders": overdue},
                "risk": risk, "stages": stages, "status_distribution": status_distribution,
                "ingestion": ingestion, "workcenters": wcs,
                "fusion": {"rows": fusion, "status": fusion_status,
                           "note": "工时数据校准中，暂不展示估算值" if fusion_status == "待接入" else ""},
                "brief": {"report_date": report_day, **brief},
                "features": ent_features_block(),
                "consistency": {
                    "stage_overdue": sum(st_["overdue"] for st_ in stages),
                    "risk_red": risk["red"], "risk_yellow": risk["yellow"],
                    "historical_nodes": sum(st_["historical_carryover"] for st_ in stages),
                    "pending_sched": q("SELECT COUNT(*) c FROM stage_nodes WHERE stage_status<>'已完成' "
                                       "AND (planned_end_at IS NULL OR planned_end_at='')")[0]["c"],
                    "note": ("交叉校验：进度看板超时节点与交付风险预警红/黄单同为当月窗口口径；"
                             "当月前旧交期节点计为历史结转（两模块一致排除），无计划日期节点计为待排程"),
                },
                "order_sources": order_sources,
                "table_stats": {
                    "contracts": t_contracts, "erp_contracts": t_erp, "customers": t_cust,
                    "shipments": t_ship, "exceptions_open": t_ex_open, "exceptions_closed": t_ex_closed,
                    "inventory_rows": t_inv,
                }}
    finally:
        con.close()


def _month_seq(start_ym, end_ym, n):
    """Return list of last n 'YYYY-MM' strings ending at end_ym."""
    from datetime import date
    try:
        ey, em = int(end_ym[:4]), int(end_ym[5:7])
    except Exception:
        ey, em = 2026, 9
    out = []
    for k in range(n - 1, -1, -1):
        y, m = ey, em - k
        while m <= 0:
            m += 12
            y -= 1
        out.append(f"{y:04d}-{m:02d}")
    _ = start_ym
    return out


# 快速模拟参数：各工作中心标准人力配置与工艺完工节奏（相对发货月的提前量）
SIM_WC_CONF = {
    "WC01": {"name": "多列装配", "crew": 12, "offset": 2},
    "WC02": {"name": "电工", "crew": 6, "offset": 3},
    "WC03": {"name": "调试", "crew": 8, "offset": 1},
    "WC04": {"name": "装盒部", "crew": 5, "offset": 0},
}


def trend_data(workcenter_id=None):
    con = db()
    try:
        labor_rows = con.execute("SELECT COUNT(*) FROM labor_logs").fetchone()[0]
        if labor_rows:
            args = () if not workcenter_id else (workcenter_id,)
            where = "" if not workcenter_id else "WHERE workcenter_id=?"
            rows = [dict(r) for r in con.execute(f"""
                SELECT workcenter_id, work_date,
                       ROUND(SUM(earned_standard_hours),4) standard_hours,
                       ROUND(SUM(actual_hours),4) actual_hours,
                       ROUND(SUM(earned_standard_hours)/NULLIF(SUM(actual_hours),0),6) productivity
                FROM labor_logs {where}
                GROUP BY workcenter_id, work_date ORDER BY workcenter_id, work_date
            """, args).fetchall()]
            return {"workcenter_id": workcenter_id, "status": "可用", "mode": "labor",
                    "rows": rows,
                    "rule": "近7个有作业日均值较前7个下降超过10%且14日斜率为负时需要关注"}

        # ---- 快速模拟：工时日志未接入时，用生产订单/发货记录推算小组趋势 ----
        snap = snapshot_value(con) or "2026-09-20T08:00:00"
        months = _month_seq(None, snap[:7], 12)
        mset = set(months)
        disp = {r[0]: r[1] for r in con.execute("""
            SELECT strftime('%Y-%m', dispatched_at) ym, COUNT(DISTINCT sales_order_id) n
            FROM shipments WHERE dispatched_at IS NOT NULL AND dispatched_at <> ''
            GROUP BY ym""").fetchall()}
        created = {r[0]: r[1] for r in con.execute("""
            SELECT strftime('%Y-%m', created_at) ym, COUNT(*) n
            FROM v_current_orders WHERE created_at IS NOT NULL AND created_at <> ''
            GROUP BY ym""").fetchall()}
        # 模拟口径：工作中心在“发货月-offset”完成其工序；人效=该月完工单数/标准人力
        def shift(ym, k):
            y, m = int(ym[:4]), int(ym[5:7]) + k
            while m > 12:
                m -= 12
                y += 1
            while m <= 0:
                m += 12
                y -= 1
            return f"{y:04d}-{m:02d}"

        series = []
        for wc, cfg in SIM_WC_CONF.items():
            # 有提前量的组，最后 offset 个月对应的发货月尚未到来，不可评估 → 截尾
            usable = months[: len(months) - cfg["offset"]]
            pts, prod_hist = [], []
            for i, m in enumerate(usable):
                finished = disp.get(shift(m, cfg["offset"]), 0)
                prod = round(finished / cfg["crew"], 3)
                prod_hist.append(prod)
                ma3 = round(sum(prod_hist[max(0, i - 2):i + 1]) / len(prod_hist[max(0, i - 2):i + 1]), 3)
                pts.append({"month": m, "finished": finished, "productivity": prod, "ma3": ma3})
            warn = (len(pts) >= 6 and pts[-1]["ma3"] < pts[-4]["ma3"] * 0.9 and pts[-4]["ma3"] > 0)
            series.append({"workcenter_id": wc, "workcenter_name": cfg["name"],
                           "crew": cfg["crew"], "offset_months": cfg["offset"],
                           "months": usable, "points": pts, "decline_warn": bool(warn)})
        if workcenter_id:
            series = [s for s in series if s["workcenter_id"] == workcenter_id]
        return {
            "workcenter_id": workcenter_id, "status": "推算", "mode": "estimated",
            "months": months,
            "overview": {"months": months,
                         "created": [created.get(m, 0) for m in months],
                         "dispatched": [disp.get(m, 0) for m in months]},
            "series": series,
            "assumptions": "各小组标准人力 WC01装配12人/WC02电工6人/WC03调试8人/WC04装盒5人；"
                           "工序完工节奏按 电工提前3月、装配提前2月、调试提前1月、装盒当月 相对发货月推算",
            "rule": "近3月移动平均较3个月前下降超10%标记关注（估算口径）",
            "note": "人效按生产订单与发货记录推算，工时实绩持续校准中；"
                    "接入真实工时后本页自动切换为按作业日聚合的真实人效。",
        }
    finally:
        con.close()


def order_progress(filters):
    con = db()
    try:
        snap = snapshot_value(con)
        red_line, _ = risk_lines(snap)
        month_start = snap[:8] + "01"
        where, args = ["1=1"], []
        if filters.get("sales_order_id"):
            where.append("n.sales_order_id=?")
            args.append(filters["sales_order_id"].strip())
        if filters.get("stage_code"):
            where.append("n.stage_code=?")
            args.append(filters["stage_code"].strip())
        if filters.get("workcenter_id"):
            where.append("n.workcenter_id=?")
            args.append(filters["workcenter_id"].strip())
        if filters.get("stage_status"):
            where.append("n.stage_status=?")
            args.append(filters["stage_status"].strip())
        w = "WHERE " + " AND ".join(where)
        try:
            limit = max(1, min(int(filters.get("limit", DEFAULT_PAGE)), MAX_ROWS))
        except (TypeError, ValueError):
            limit = DEFAULT_PAGE
        try:
            cursor = max(0, int(filters.get("cursor", 0)))
        except (TypeError, ValueError):
            cursor = 0
        all_rows = [dict(r) for r in con.execute(f"""
            SELECT n.sales_order_id, n.work_order_id, n.stage_code, n.stage_name,
                   n.stage_status, n.workcenter_id, n.planned_start_at, n.planned_end_at,
                   n.actual_start_at, n.actual_end_at, n.source_status, n.updated_at,
                   o.contract_name, o.unique_id, o.contract_no, c.customer_name
            FROM stage_nodes n
            LEFT JOIN orders o ON o.sales_order_id = n.sales_order_id
            LEFT JOIN customers c ON c.customer_id = o.customer_id {w}
            ORDER BY (o.created_at IS NULL) ASC, o.created_at DESC, n.sales_order_id ASC, n.sequence ASC
        """, args).fetchall()]
        for r in all_rows:
            r["deadline_state"] = deadline_state(r["stage_status"], r["planned_end_at"], snap, red_line, month_start)
        if filters.get("deadline_state"):
            all_rows = [r for r in all_rows if r["deadline_state"] == filters["deadline_state"].strip()]
        total = len(all_rows)
        rows = all_rows[cursor:cursor + limit]
        end = cursor + limit
        return {"snapshot_at": snap, "rows": rows, "count": len(rows), "total": total,
                "limit": limit, "cursor": cursor,
                "next_cursor": end if end < total else None,
                "deadline_rule": "当月内 planned_end_at < snapshot_at 且未完成 → 超时；快照当月之前的旧交期节点 → 历史结转（不计超时，与交付风险预警口径一致）；无计划日期 → 待排程"}
    finally:
        con.close()


# ================= 多源数据自动采集（智能体采集入口 + API 聚合引擎 + 数据湖） =================
import io

COLLECT_SOURCES = [
    {"id": "excel", "name": "Excel 台账", "icon": "📗", "type": "文件上传",
     "target": "contracts / orders / procurement_lines / inventory_snapshot",
     "ingest_keys": ["合同表", "下单表", "采购总表", "库存表", "生产进度表",
                     "价格表", "供应商", "产品名称", "机型"]},
    {"id": "wms", "name": "WMS 出入库记录", "icon": "📦", "type": "API 聚合",
     "target": "wms_transactions / inventory_snapshot", "ingest_keys": ["WMS"]},
    {"id": "erp", "name": "ERP 工单", "icon": "🏭", "type": "API 聚合",
     "target": "orders / work_orders", "ingest_keys": ["ERP"], "prefill": "http://192.167.30.7:6088/SYSN"},
    {"id": "mes", "name": "MES 设备日志", "icon": "⚙️", "type": "API 聚合",
     "target": "mes_events", "ingest_keys": ["MES"]},
    {"id": "wechat", "name": "微信订单截图", "icon": "🖼️", "type": "图片 OCR",
     "target": "orders 补录", "ingest_keys": ["WeChat"]},
    {"id": "oa", "name": "OA 表单", "icon": "📝", "type": "API 聚合",
     "target": "oa_forms / expenses", "ingest_keys": ["OA"]},
]
LAKE_TARGETS = ["contracts", "orders", "work_orders", "stage_nodes", "shipments",
                "procurement_lines", "inventory_snapshot", "wms_transactions",
                "mes_events", "oa_forms", "expenses", "suppliers", "products"]


def rw_db():
    con = sqlite3.connect(ent_db())
    con.row_factory = sqlite3.Row
    return con


def _ensure_collect_tables(con):
    con.execute("""CREATE TABLE IF NOT EXISTS collect_config(
        source_id TEXT PRIMARY KEY, endpoint TEXT DEFAULT '', interval_min INTEGER DEFAULT 30,
        enabled INTEGER DEFAULT 0, last_test_at TEXT DEFAULT '', last_test_ok INTEGER DEFAULT 0,
        updated_at TEXT DEFAULT '')""")
    con.execute("""CREATE TABLE IF NOT EXISTS lake_records(
        batch_id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT, filename TEXT,
        row_count INTEGER DEFAULT 0, columns_json TEXT DEFAULT '[]',
        sample_json TEXT DEFAULT '[]', status TEXT DEFAULT '已入湖',
        created_at TEXT DEFAULT '')""")


def _xlsx_rows(data):
    """stdlib 解析 xlsx（无 openpyxl 依赖）：返回二维数组。"""
    import zipfile
    from xml.etree import ElementTree as ET
    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relmap = {r.get("Id"): r.get("Target") for r in rels}
        sh = wb.find(NS + "sheets").find(NS + "sheet")
        target = relmap.get(sh.get(RNS + "id"), "worksheets/sheet1.xml")
        if target.startswith("/"):
            target = target.lstrip("/")
        elif not target.startswith("xl/"):
            target = "xl/" + target
        root = ET.fromstring(z.read(target))
        grid = []
        for row in root.iter(NS + "row"):
            cells = {}
            for c in row.findall(NS + "c"):
                ref = c.get("r") or ""
                col = re.match(r"([A-Z]+)", ref)
                idx = 0
                if col:
                    for ch in col.group(1):
                        idx = idx * 26 + ord(ch) - 64
                    idx -= 1
                v = c.find(NS + "v")
                if v is None:
                    isel = c.find(NS + "is")
                    val = "".join(t.text or "" for t in isel.iter(NS + "t")) if isel is not None else ""
                else:
                    val = shared[int(v.text)] if c.get("t") == "s" else v.text
                cells[idx] = val or ""
            if cells:
                width = max(cells) + 1
                grid.append([cells.get(i, "") for i in range(width)])
        return grid


def _csv_rows(data):
    import csv as _csv
    text = data.decode("utf-8-sig", errors="replace")
    return [row for row in _csv.reader(io.StringIO(text))]


def _parse_multipart(ct, body):
    """极简 multipart/form-data 解析：返回 [(filename, bytes)]。"""
    m = re.search(r'boundary="?([^";]+)"?', ct or "")
    if not m:
        return []
    boundary = ("--" + m.group(1)).encode()
    out = []
    for part in body.split(boundary):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if b"\r\n\r\n" not in part:
            continue
        head, _, payload = part.partition(b"\r\n\r\n")
        fm = re.search(rb'filename="([^"]*)"', head)
        if fm and fm.group(1):
            out.append((fm.group(1).decode("utf-8", "replace"), payload))
    return out


def collect_overview():
    con = db()
    rw = rw_db()
    try:
        _ensure_collect_tables(rw)
        cfg = {r["source_id"]: dict(r) for r in rw.execute("SELECT * FROM collect_config")}
        staging = [dict(r) for r in rw.execute(
            "SELECT * FROM lake_records ORDER BY batch_id DESC LIMIT 50")]
        runs = [dict(r) for r in con.execute("SELECT * FROM ingestion_runs ORDER BY run_id")]
        sources = []
        for s in COLLECT_SOURCES:
            related = [r for r in runs if any(k in (r.get("source_system") or "")
                                             for k in s["ingest_keys"])]
            done = [r for r in related if r.get("loaded_record_count")]
            last = max(related, key=lambda r: (r.get("run_at") or "")) if related else None
            if s["type"] == "文件上传":
                status = "可用" if done else "待上传"
            elif s["type"] == "图片 OCR":
                status = "待OCR"
            else:
                status = "已接入" if (cfg.get(s["id"], {}).get("enabled")
                                     and cfg[s["id"]].get("last_test_ok")) else "待接入"
            sources.append({**s, "status": status,
                            "last_run_at": (last or {}).get("run_at"),
                            "last_file": (last or {}).get("source_system"),
                            "loaded_total": sum(r.get("loaded_record_count") or 0 for r in related),
                            "batches": len(related),
                            "config": cfg.get(s["id"])})
        lake = []
        for t in LAKE_TARGETS:
            try:
                n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.Error:
                n = None
            lake.append({"table": t, "rows": n})
        rw.commit()
        return {"snapshot_at": snapshot_value(con), "sources": sources,
                "staging": staging, "lake": lake,
                "engine_note": "API 聚合引擎：为各系统配置接口地址并启用后，按设定间隔自动拉取；"
                               "未连通前如实显示待接入，不伪造采集成功",
                "lake_note": "结构化数据湖：文件/接口采集先入湖（lake_records 暂存），"
                             "完成字段映射后推送至业务表"}
    finally:
        con.close()
        rw.close()


def collect_upload(source_id, filename, data):
    rows = []
    try:
        if filename.lower().endswith(".xlsx"):
            rows = _xlsx_rows(data)
        elif filename.lower().endswith(".csv"):
            rows = _csv_rows(data)
        else:
            return {"error": "仅支持 .xlsx / .csv 台账文件"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"文件解析失败：{exc}"}
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if len(rows) < 2:
        return {"error": "文件没有数据行"}
    headers = [str(h).strip() for h in rows[0]]
    body_rows = [[("" if c is None else str(c).strip()) for c in r] for r in rows[1:]]
    rw = rw_db()
    try:
        _ensure_collect_tables(rw)
        cur = rw.execute(
            "INSERT INTO lake_records(source_id, filename, row_count, columns_json, sample_json,"
            " status, created_at) VALUES(?,?,?,?,?,?,?)",
            (source_id, filename, len(body_rows), json.dumps(headers, ensure_ascii=False),
             json.dumps(body_rows[:100], ensure_ascii=False), "已入湖待映射",
             datetime.now().isoformat(timespec="seconds")))
        rw.commit()
        return {"ok": True, "batch_id": cur.lastrowid, "filename": filename,
                "columns": headers, "row_count": len(body_rows),
                "status": "已入湖待映射"}
    finally:
        rw.close()


def collect_image(filename, data):
    upload_dir = os.path.join(ROOT, "agent_upload")
    os.makedirs(upload_dir, exist_ok=True)
    safe = re.sub(r"[^\w.\-\u4e00-\u9fff]", "_", filename) or "wechat.png"
    path = os.path.join(upload_dir, f"{datetime.now():%Y%m%d%H%M%S}_{safe}")
    with open(path, "wb") as f:
        f.write(data)
    rw = rw_db()
    try:
        _ensure_collect_tables(rw)
        cur = rw.execute(
            "INSERT INTO lake_records(source_id, filename, row_count, status, created_at)"
            " VALUES('wechat', ?, 0, '待OCR', ?)",
            (filename, datetime.now().isoformat(timespec="seconds")))
        rw.commit()
        return {"ok": True, "batch_id": cur.lastrowid, "saved": os.path.basename(path),
                "status": "待OCR"}
    finally:
        rw.close()


def collect_save_config(source_id, endpoint, interval_min, enabled):
    if source_id not in {s["id"] for s in COLLECT_SOURCES}:
        return {"error": "未知采集源"}
    rw = rw_db()
    try:
        _ensure_collect_tables(rw)
        rw.execute("""INSERT INTO collect_config(source_id, endpoint, interval_min, enabled, updated_at)
                      VALUES(?,?,?,?,?)
                      ON CONFLICT(source_id) DO UPDATE SET endpoint=excluded.endpoint,
                        interval_min=excluded.interval_min, enabled=excluded.enabled,
                        updated_at=excluded.updated_at""",
                   (source_id, (endpoint or "").strip(), max(5, int(interval_min or 30)),
                    1 if enabled else 0, datetime.now().isoformat(timespec="seconds")))
        rw.commit()
        return {"ok": True}
    finally:
        rw.close()


def collect_test(source_id):
    cfg = None
    rw = rw_db()
    try:
        _ensure_collect_tables(rw)
        row = rw.execute("SELECT * FROM collect_config WHERE source_id=?", (source_id,)).fetchone()
        cfg = dict(row) if row else {}
    finally:
        rw.close()
    endpoint = (cfg or {}).get("endpoint") or ""
    if not endpoint:
        return {"error": "请先配置接口地址"}
    ok, detail = False, ""
    try:
        req = urllib.request.Request(endpoint, headers={"User-Agent": "datahub-collect/1.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            ok = 200 <= r.status < 400
            detail = f"HTTP {r.status}"
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)[:120]
    rw = rw_db()
    try:
        rw.execute("UPDATE collect_config SET last_test_at=?, last_test_ok=? WHERE source_id=?",
                   (datetime.now().isoformat(timespec="seconds"), 1 if ok else 0, source_id))
        rw.commit()
    finally:
        rw.close()
    return {"ok": ok, "detail": detail, "endpoint": endpoint}


# ================= 交付风险处置：AI 解决方案 + 自动联系 =================
def _ensure_risk_actions(con):
    con.execute("""CREATE TABLE IF NOT EXISTS risk_actions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, action TEXT,
        content TEXT DEFAULT '', status TEXT DEFAULT '', created_at TEXT DEFAULT '')""")


def _log_risk_action(order_id, action, content, status="已生成"):
    rw = rw_db()
    try:
        _ensure_risk_actions(rw)
        rw.execute("INSERT INTO risk_actions(order_id, action, content, status, created_at)"
                   " VALUES(?,?,?,?,?)",
                   (order_id, action, content[:4000], status,
                    datetime.now().isoformat(timespec="seconds")))
        rw.commit()
    finally:
        rw.close()


def _order_context(order_id):
    con = db()
    try:
        row = con.execute("""
            SELECT o.sales_order_id, o.contract_no, o.customer_id, c.customer_name,
                   o.packaged_goods, o.quantity, o.contract_amount,
                   o.promised_delivery_at, COALESCE(NULLIF(o.sales_owner,''), c.sales_owner) sales_owner
            FROM v_current_orders o LEFT JOIN customers c USING(customer_id)
            WHERE o.sales_order_id=? ORDER BY o.promised_delivery_at LIMIT 1""", (order_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["stages"] = [dict(r) for r in con.execute(
            "SELECT stage_code, stage_status FROM stage_nodes WHERE sales_order_id=?"
            " ORDER BY sequence", (order_id,)).fetchall()]
        snap = snapshot_value(con)
        p = d.get("promised_delivery_at")
        try:
            d["overdue_days"] = max((datetime.fromisoformat(snap[:19])
                                     - datetime.fromisoformat(p[:19])).days, 0) if p else 0
        except ValueError:
            d["overdue_days"] = 0
        d["snapshot"] = snap
        return d
    finally:
        con.close()


def risk_solution(order_id):
    ctx = _order_context(order_id)
    if not ctx:
        return {"error": "订单不存在"}
    brief = {k: ctx.get(k) for k in ("sales_order_id", "customer_name", "packaged_goods",
                                     "quantity", "contract_amount", "promised_delivery_at",
                                     "sales_owner", "overdue_days", "stages")}
    prompt = ("你是金汉隆包装机械厂的交付协同专家。以下订单已逾期或即将到期，"
              "给出3-4条具体处置措施，每条一行，从加急生产/分批发货/物流跟进/客户沟通/"
              "供应链催料等角度，并注明责任角色（生产/销售/采购/物流）。不要空话。订单信息："
              + json.dumps(brief, ensure_ascii=False, default=str))
    try:
        text = call_llm([{"role": "system", "content": "用中文简洁输出，直接给措施列表"},
                         {"role": "user", "content": prompt}])
    except Exception as exc:  # noqa: BLE001
        return {"error": f"分析模型调用失败：{exc}"}
    text = re.sub(r"(?is)<think>.*?</think>", "", text).strip()
    _log_risk_action(order_id, "solution", text)
    return {"ok": True, "order_id": order_id, "solution": text,
            "context": {"customer": ctx.get("customer_name"),
                        "promised": ctx.get("promised_delivery_at"),
                        "overdue_days": ctx.get("overdue_days"),
                        "owner": ctx.get("sales_owner")}}


def risk_contact(order_id):
    ctx = _order_context(order_id)
    if not ctx:
        return {"error": "订单不存在"}
    brief = {k: ctx.get(k) for k in ("sales_order_id", "customer_name", "packaged_goods",
                                     "contract_amount", "promised_delivery_at",
                                     "sales_owner", "overdue_days", "stages")}
    prompt = ("为以下逾期订单生成两条微信话术：1)【给业务员】督促推进：点明逾期天数、"
              "要求今天回复新交期与卡点；2)【给客户】安抚沟通：说明进展、给出新承诺交期、致歉。"
              "每条不超过80字，口语化可直接发送。订单信息："
              + json.dumps(brief, ensure_ascii=False, default=str))
    try:
        text = call_llm([{"role": "system", "content": "用中文输出两段话术，格式【给业务员】…【给客户】…"},
                         {"role": "user", "content": prompt}])
    except Exception as exc:  # noqa: BLE001
        return {"error": f"分析模型调用失败：{exc}"}
    text = re.sub(r"(?is)<think>.*?</think>", "", text).strip()
    _log_risk_action(order_id, "contact", text, status="待推送")
    return {"ok": True, "order_id": order_id, "message": text,
            "context": {"customer": ctx.get("customer_name"),
                        "owner": ctx.get("sales_owner") or "跟单业务员",
                        "overdue_days": ctx.get("overdue_days")}}


def risk_mark_contacted(order_id):
    rw = rw_db()
    try:
        _ensure_risk_actions(rw)
        cur = rw.execute(
            "UPDATE risk_actions SET status='已联系' WHERE order_id=? AND action='contact'",
            (order_id,))
        if cur.rowcount == 0:
            rw.execute("INSERT INTO risk_actions(order_id, action, content, status, created_at)"
                       " VALUES(?, 'contact', '人工标记', '已联系', ?)",
                       (order_id, datetime.now().isoformat(timespec="seconds")))
        rw.commit()
        return {"ok": True}
    finally:
        rw.close()


def risk_actions_map(order_ids):
    rw = rw_db()
    try:
        _ensure_risk_actions(rw)
        marks, contacted = {}, 0
        if order_ids:
            ph = ",".join("?" * len(order_ids))
            for r in rw.execute(
                    f"SELECT order_id, action, status, MAX(created_at) at FROM risk_actions"
                    f" WHERE order_id IN ({ph}) GROUP BY order_id, action, status", order_ids):
                m = marks.setdefault(r["order_id"], {})
                if r["action"] == "contact":
                    m["contact_status"] = r["status"]
                else:
                    m["solution_at"] = r["at"]
        contacted = rw.execute(
            "SELECT COUNT(DISTINCT order_id) c FROM risk_actions"
            " WHERE action='contact' AND status='已联系'").fetchone()["c"]
        return {"orders": marks, "contacted_total": contacted}
    finally:
        rw.close()


# ================= ERP 自动录入智能体（合同/订单 → AI 解析 → ERP 录入队列） =================
ERP_FIELDS = ["contract_no", "customer_name", "product", "quantity", "unit",
              "amount", "promised_date", "sales_owner", "remark"]
ERP_LABELS = {"contract_no": "合同/订单编号", "customer_name": "客户名称", "product": "产品/设备",
              "quantity": "数量", "unit": "单位", "amount": "金额", "promised_date": "交期",
              "sales_owner": "业务员", "remark": "备注"}


def _ensure_erp_queue(con):
    con.execute("""CREATE TABLE IF NOT EXISTS erp_entry_queue(
        id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT DEFAULT '手动',
        filename TEXT DEFAULT '', payload_json TEXT DEFAULT '{}',
        status TEXT DEFAULT '待推送', erp_ref TEXT DEFAULT '',
        created_at TEXT DEFAULT '', pushed_at TEXT DEFAULT '', result TEXT DEFAULT '')""")


def _llm_json(prompt, max_tokens=1200):
    text = call_llm(
        [{"role": "system", "content": "只输出一个 JSON 数组，不要解释，不要代码块标记"},
         {"role": "user", "content": prompt}], 120, max_tokens)
    text = re.sub(r"(?is)<think>.*?</think>", "", text).strip()
    m = re.search(r"(?s)\[.*\]", text)
    if not m:
        raise ValueError("模型未返回 JSON 数组")
    data = json.loads(m.group(0))
    if not isinstance(data, list):
        raise ValueError("JSON 结构不符")
    return data


def erp_agent_parse(content, filename=""):
    """合同/订单内容（文本或表格行）→ LLM 抽取 ERP 录入字段数组。"""
    if not content or not content.strip():
        return {"error": "内容为空"}
    prompt = ("从以下合同/订单内容中提取ERP销售订单录入字段，输出JSON数组（一条记录一个对象）。"
              "字段：contract_no 合同/订单编号, customer_name 客户名称, product 产品/设备名称, "
              "quantity 数量(数字), unit 单位, amount 金额(数字,元), promised_date 交期(YYYY-MM-DD), "
              "sales_owner 业务员, remark 备注。内容里没有的字段填空字符串，不要编造。内容：\n"
              + content[:6000])
    try:
        records = _llm_json(prompt)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"AI 解析失败：{exc}"}
    clean = []
    for r in records[:20]:
        if not isinstance(r, dict):
            continue
        item = {k: str(r.get(k, "") or "").strip() for k in ERP_FIELDS}
        item["quantity"] = _num(item["quantity"])
        item["amount"] = _num(item["amount"])
        if item["customer_name"] or item["product"] or item["contract_no"]:
            clean.append(item)
    if not clean:
        return {"error": "未能从内容中识别出订单记录"}
    return {"ok": True, "filename": filename, "records": clean,
            "fields": ERP_FIELDS, "labels": ERP_LABELS}


def _num(v):
    v = str(v or "").replace(",", "").replace("¥", "").replace("￥", "").strip()
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except ValueError:
        return ""


def erp_agent_submit(records, source="手动", filename=""):
    if not isinstance(records, list) or not records:
        return {"error": "没有可录入的记录"}
    rw = rw_db()
    ids = []
    try:
        _ensure_erp_queue(rw)
        for r in records[:50]:
            if not isinstance(r, dict):
                continue
            item = {k: str(r.get(k, "") or "").strip() for k in ERP_FIELDS}
            if not (item["customer_name"] or item["product"]):
                continue
            cur = rw.execute(
                "INSERT INTO erp_entry_queue(source, filename, payload_json, created_at)"
                " VALUES(?,?,?,?)",
                (source, filename, json.dumps(item, ensure_ascii=False),
                 datetime.now().isoformat(timespec="seconds")))
            ids.append(cur.lastrowid)
        rw.commit()
        return {"ok": True, "queued": len(ids), "ids": ids}
    finally:
        rw.close()


def erp_agent_queue():
    rw = rw_db()
    try:
        _ensure_erp_queue(rw)
        rows = []
        for r in rw.execute("SELECT * FROM erp_entry_queue ORDER BY id DESC LIMIT 100"):
            d = dict(r)
            d["payload"] = json.loads(d.pop("payload_json") or "{}")
            rows.append(d)
        cfg = rw.execute("SELECT endpoint, last_test_ok FROM collect_config"
                         " WHERE source_id='erp'").fetchone()
        erp_ready = bool(cfg and cfg["endpoint"] and cfg["last_test_ok"])
        return {"rows": rows, "erp_ready": erp_ready,
                "erp_endpoint": (cfg["endpoint"] if cfg else "") or "",
                "note": "ERP 接口未配置或未连通前，记录停留在「待推送」，可导出录入清单人工导入；"
                        "在「多源数据自动采集」页配置并测试 ERP 接口后即可自动推送"}
    finally:
        rw.close()


def erp_agent_push(entry_id=None):
    rw = rw_db()
    try:
        _ensure_erp_queue(rw)
        cfg = rw.execute("SELECT endpoint, last_test_ok FROM collect_config"
                         " WHERE source_id='erp'").fetchone()
        endpoint = (cfg["endpoint"] if cfg else "") or ""
        if not endpoint or not (cfg and cfg["last_test_ok"]):
            return {"error": "ERP 接口未配置或未连通：请先在「多源数据自动采集」页配置 ERP"
                             " 接口地址并通过测试", "erp_ready": False}
        where = "AND id=?" if entry_id else ""
        args = (entry_id,) if entry_id else ()
        rows = rw.execute(f"SELECT * FROM erp_entry_queue WHERE status='待推送' {where}"
                          " ORDER BY id LIMIT 20", args).fetchall()
        pushed = failed = 0
        last_err = ""
        for r in rows:
            payload = json.loads(r["payload_json"] or "{}")
            try:
                body = json.dumps({"source": "datahub-erp-agent",
                                   "entry": payload}, ensure_ascii=False).encode()
                req = urllib.request.Request(
                    endpoint, data=body,
                    headers={"Content-Type": "application/json",
                             "Authorization": "Bearer datahub"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    ok = 200 <= resp.status < 400
                    detail = f"HTTP {resp.status}"
                rw.execute("UPDATE erp_entry_queue SET status=?, pushed_at=?, result=? WHERE id=?",
                           ("已推送" if ok else "失败",
                            datetime.now().isoformat(timespec="seconds"),
                            detail if ok else detail, r["id"]))
                pushed += ok
                failed += (not ok)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                last_err = str(exc)[:150]
                rw.execute("UPDATE erp_entry_queue SET status='失败', result=? WHERE id=?",
                           (last_err, r["id"]))
        rw.commit()
        return {"ok": True, "pushed": pushed, "failed": failed,
                "error": last_err or None}
    finally:
        rw.close()


def erp_agent_export():
    rw = rw_db()
    try:
        _ensure_erp_queue(rw)
        rows = rw.execute("SELECT * FROM erp_entry_queue ORDER BY id DESC LIMIT 2000").fetchall()
        buf = io.StringIO()
        w = __import__("csv").writer(buf)
        w.writerow(["\ufeff录入ID"] + [ERP_LABELS[f] for f in ERP_FIELDS] + ["状态", "创建时间"])
        for r in rows:
            p = json.loads(r["payload_json"] or "{}")
            w.writerow([r["id"]] + [p.get(f, "") for f in ERP_FIELDS]
                       + [r["status"], r["created_at"]])
        return buf.getvalue().encode("utf-8")
    finally:
        rw.close()


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")

    def _send(self, code, payload, ctype="application/json; charset=utf-8"):
        if isinstance(payload, bytes):
            data = payload
        else:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _snapshot(self):
        try:
            con = db()
            v = snapshot_value(con)
            con.close()
            return v
        except Exception:
            return None

    def do_GET(self):
        p = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)
        one = lambda k: (qs.get(k) or [None])[0]
        if p == "/health":
            return self._send(200, {"ok": True, "mode": "READ_ONLY", "snapshot_at": self._snapshot()})
        if p == "/api/dashboard":
            try:
                return self._send(200, dashboard_data())
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        if p == "/api/trends":
            try:
                return self._send(200, trend_data(one("workcenter_id")))
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        if p == "/api/collect/overview":
            try:
                return self._send(200, collect_overview())
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        if p == "/api/risk/actions":
            try:
                ids = [x for x in (one("ids") or "").split(",") if x][:50]
                return self._send(200, risk_actions_map(ids))
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        if p == "/api/erp-agent/queue":
            try:
                return self._send(200, erp_agent_queue())
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        if p == "/api/erp-agent/export":
            try:
                data = erp_agent_export()
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition",
                                 "attachment; filename=ERP-entry-list.csv;"
                                 " filename*=UTF-8''%E5%BD%95%E5%85%A5%E6%B8%85%E5%8D%95.csv")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as exc:  # noqa: BLE001
                return self._send(500, {"error": str(exc)})
        if p == "/api/ingestion/status":
            try:
                con = db()
                snap = snapshot_value(con)
                rows = [dict(r) for r in con.execute("""
                    SELECT run_id, source_system, run_at, input_record_count, loaded_record_count,
                           quarantined_record_count,
                           CASE WHEN run_status LIKE '%成功%' OR run_status LIKE '%完成%' THEN '已完成'
                                WHEN run_status LIKE '%部分%' OR run_status LIKE '%OCR%' THEN '处理中'
                                WHEN run_status LIKE '%待OCR%' THEN '待OCR'
                                WHEN run_status LIKE '%待%' THEN '待接入'
                                ELSE '需关注' END AS status,
                           run_status AS raw_status, note
                    FROM ingestion_runs ORDER BY run_id""").fetchall()]
                con.close()
                return self._send(200, {"snapshot_at": snap, "rows": rows})
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        if p == "/api/daily-brief/latest":
            try:
                return self._send(200, dashboard_data()["brief"])
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        if p == "/api/erp/contracts":
            try:
                qs = parse_qs(urlparse(self.path).query)
                kw = (qs.get("q", [""])[0] or "").strip()
                con = db()
                try:
                    like = "%" + kw + "%" if kw else "%"
                    rows = [dict(r) for r in con.execute(
                        """SELECT contract_no, contract_name, customer_name, amount, signed_at, synced_at
                           FROM erp_contracts WHERE contract_name LIKE ? OR contract_no LIKE ?
                           OR customer_name LIKE ? ORDER BY synced_at DESC LIMIT 1000""",
                        (like, like, like)).fetchall()]
                finally:
                    con.close()
                return self._send(200, {"total": len(rows), "rows": rows})
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        if p == "/api/daily-brief/history":
            try:
                qs = parse_qs(urlparse(self.path).query)
                return self._send(200, daily_brief_history(qs.get("days", ["30"])[0]))
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        if p == "/api/order-progress":
            try:
                return self._send(200, order_progress(
                    {k: one(k) for k in ("sales_order_id", "stage_code", "workcenter_id",
                                         "stage_status", "deadline_state", "limit", "cursor")}))
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        rel = (p.lstrip("/") or "index.html")
        fp = os.path.normpath(os.path.join(DASH, rel))
        if fp.startswith(DASH) and os.path.isfile(fp):
            # 快照页按本库实时渲染, 不用旧静态存档(旧档为金汉隆全局旧数据)
            if os.path.basename(fp) == "snapshot.html":
                try:
                    return self._send(200, render_snapshot().encode("utf-8"), "text/html; charset=utf-8")
                except Exception:
                    pass
            with open(fp, "rb") as f:
                data = f.read()
            if fp.endswith(".html"):
                ct = "text/html; charset=utf-8"
                # 企业品牌注入: 重写HTML中的标题和颜色(所有页面)
                if ENT_NAME:
                    with open(fp, "r", encoding="utf-8") as hf:
                        html = hf.read()
                    html = html.replace("<title>AI数据中枢", f"<title>{ENT_NAME} AI数据中枢")
                    html = html.replace("<h1>AI数据中枢", f"<h1>{ENT_NAME} AI数据中枢")
                    html = html.replace('id="ent-brand-name">数据中枢', f'id="ent-brand-name">{ENT_NAME} · 数据中枢')
                    html = html.replace('金汉隆 AI数据中枢', f'{ENT_NAME} AI数据中枢')
                    html = html.replace('金汉隆经营数据', f'{ENT_NAME}经营数据')
                    if ENT_COLOR:
                        html = html.replace("</head>", f"<style>:root{{--brand:{ENT_COLOR}!important}}.nav a.active{{background:{ENT_COLOR}20;color:{ENT_COLOR}}}</style></head>", 1)
                    data = html.encode("utf-8")
            elif fp.endswith(".js"):
                ct = "application/javascript; charset=utf-8"
            elif fp.endswith(".css"):
                ct = "text/css; charset=utf-8"
            elif fp.endswith(".svg"):
                ct = "image/svg+xml"
            else:
                ct = "application/octet-stream"
            return self._send(200, data, ct)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/erp/contracts-sync":
            try:
                return self._send(200, erp_sync.sync())
            except Exception as exc:  # noqa: BLE001
                return self._send(500, {"error": str(exc)})
        if path == "/api/daily-brief/generate":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception as exc:
                return self._send(400, {"error": f"bad request: {exc}"})
            date_str = (body.get("date") or "").strip()
            if date_str and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
                return self._send(400, {"error": "date 须为 YYYY-MM-DD"})
            try:
                return self._send(200, generate_daily_brief(
                    date_str or None, bool(body.get("force"))))
            except Exception as exc:  # noqa: BLE001
                return self._send(500, {"error": str(exc)})
        if path == "/api/erp-agent/parse-file":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n)
                files = _parse_multipart(self.headers.get("Content-Type", ""), body)
                if not files:
                    return self._send(400, {"error": "缺少上传文件"})
                fname, data = files[0]
                if len(data) > 20 * 1024 * 1024:
                    return self._send(400, {"error": "文件超过 20MB 限制"})
                if fname.lower().endswith(".xlsx"):
                    grid = _xlsx_rows(data)
                elif fname.lower().endswith(".csv"):
                    grid = _csv_rows(data)
                else:
                    return self._send(400, {"error": "仅支持 .xlsx / .csv 合同或订单文件"})
                grid = [r for r in grid if any(str(c).strip() for c in r)][:60]
                if not grid:
                    return self._send(400, {"error": "文件没有数据行"})
                content = "\n".join(" | ".join(str(c).strip() for c in r) for r in grid)
                return self._send(200, erp_agent_parse(content, fname))
            except Exception as exc:  # noqa: BLE001
                return self._send(400, {"error": f"解析失败：{exc}"})
        if path == "/api/erp-agent/parse" or path == "/api/erp-agent/submit" \
                or path == "/api/erp-agent/push":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception as exc:
                return self._send(400, {"error": f"bad request: {exc}"})
            try:
                if path == "/api/erp-agent/parse":
                    return self._send(200, erp_agent_parse(body.get("text", "")))
                if path == "/api/erp-agent/submit":
                    return self._send(200, erp_agent_submit(
                        body.get("records") or [], body.get("source", "手动"),
                        body.get("filename", "")))
                return self._send(200, erp_agent_push(body.get("id")))
            except Exception as exc:  # noqa: BLE001
                return self._send(500, {"error": str(exc)})
        if path == "/api/risk/solution" or path == "/api/risk/contact" \
                or path == "/api/risk/mark-contacted":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception as exc:
                return self._send(400, {"error": f"bad request: {exc}"})
            oid = (body.get("sales_order_id") or "").strip()
            if not oid:
                return self._send(400, {"error": "sales_order_id 必填"})
            try:
                if path == "/api/risk/solution":
                    return self._send(200, risk_solution(oid))
                if path == "/api/risk/contact":
                    return self._send(200, risk_contact(oid))
                return self._send(200, risk_mark_contacted(oid))
            except Exception as exc:  # noqa: BLE001
                return self._send(500, {"error": str(exc)})
        if path == "/api/collect/upload" or path == "/api/collect/image":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n)
                files = _parse_multipart(self.headers.get("Content-Type", ""), body)
                if not files:
                    return self._send(400, {"error": "缺少上传文件"})
                fname, data = files[0]
                if len(data) > 20 * 1024 * 1024:
                    return self._send(400, {"error": "文件超过 20MB 限制"})
                if path == "/api/collect/image":
                    return self._send(200, collect_image(fname, data))
                src = "excel"
                m = re.search(r"[?&]source=([\w-]+)", self.path)
                if m:
                    src = m.group(1)
                return self._send(200, collect_upload(src, fname, data))
            except Exception as exc:  # noqa: BLE001
                return self._send(400, {"error": f"上传失败：{exc}"})
        if path == "/api/collect/config":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception as exc:
                return self._send(400, {"error": f"bad request: {exc}"})
            return self._send(200, collect_save_config(
                body.get("source_id"), body.get("endpoint"),
                body.get("interval_min", 30), bool(body.get("enabled"))))
        if path == "/api/collect/test":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception as exc:
                return self._send(400, {"error": f"bad request: {exc}"})
            try:
                return self._send(200, collect_test(body.get("source_id")))
            except Exception as exc:  # noqa: BLE001
                return self._send(500, {"error": str(exc)})
        if path == "/api/ask":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                question = (body.get("question") or "").strip()
            except Exception as exc:
                return self._send(400, {"error": f"bad request: {exc}"})
            if not question or len(question) > 500:
                return self._send(400, {"error": "question 必填且不超过500字"})
            return self._send(200, run_ask(question))
        if path != "/api/sql":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
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
            return self._send(200, {"columns": cols, "rows": rows,
                                    "row_count": len(rows), "truncated": len(rows) >= MAX_ROWS})
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
    print(f"DataHub API on {BIND}:{PORT}, db={DB}"
          + (" [enterprise-mode]" if _ent is not None else ""), flush=True)
    srv.serve_forever()
