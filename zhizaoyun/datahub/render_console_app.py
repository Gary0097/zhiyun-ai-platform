#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 8000 控制台内嵌的数据中枢页面（自包含侧边栏交互版）。

与 18790 交互页同一套界面，但数据在生成时嵌入（控制台 iframe 内无法访问
127.0.0.1:18790 的 API），订单节点查询/筛选/下钻/导出全部在浏览器本地完成。
数据随部署批次刷新：bash deploy.sh 会重新生成本页。
"""
import datetime as dt
import html
import json
import sqlite3

DB = "/data/actions/zhizaoyun-datahub/agent_data.sqlite"
OUT = ("/root/zhiyun-ai-platform/apps/zhizaoyunAIOS/runtime/qwenpaw-hub/venv/lib/"
       "python3.12/site-packages/qwenpaw/console/datahub-dashboard.html")

PHASE_MAP = {
    "待图纸": "备料/图纸/确认", "待确认": "备料/图纸/确认", "待业务确认": "备料/图纸/确认",
    "待回料": "备料/图纸/确认", "待物料验收": "备料/图纸/确认",
    "待组装": "加工/调试", "组装中": "加工/调试", "待调试": "加工/调试", "调试中": "加工/调试",
    "待验收": "验收", "待出货": "待出货", "已签收": "已完成",
}
PHASE_ORDER = ["备料/图纸/确认", "加工/调试", "待出货", "验收", "已完成", "其他/待确认"]

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
q = lambda s, *a: con.execute(s, a).fetchall()

snap = q("SELECT config_value FROM configuration WHERE config_key='snapshot_at'")[0][0]
snap_day = dt.date.fromisoformat(snap[:10])
red_line = (snap_day + dt.timedelta(days=7)).isoformat()
yellow_line = (snap_day + dt.timedelta(days=30)).isoformat()

SHIP_BASE = """
WITH s AS (SELECT sales_order_id, COUNT(*) b,
  SUM(CASE WHEN status='已签收' AND received_at IS NOT NULL AND received_at<>'' THEN 1 ELSE 0 END) g
  FROM shipments GROUP BY sales_order_id)
"""
effective = q("SELECT COUNT(*) FROM v_current_orders")[0][0]
completed = q(SHIP_BASE + "SELECT COUNT(*) FROM v_current_orders o JOIN s USING(sales_order_id) WHERE s.g=s.b")[0][0]
risk_rows = q(SHIP_BASE + """SELECT o.sales_order_id, o.promised_delivery_at,
  CASE WHEN s.sales_order_id IS NULL THEN '未发货' ELSE '在途未签' END kind
  FROM v_current_orders o LEFT JOIN s USING(sales_order_id)
  WHERE (s.g IS NULL OR s.g < s.b)""")
risk = {"red": [], "yellow": [], "green": []}
overdue = 0
# 与 18790 实时版同口径: 快照当月之前的旧交期订单不计入风险预警
month_start = snap[:8] + "01"
excluded_historical = 0
for r in risk_rows:
    p = r["promised_delivery_at"]
    if p and p < month_start:
        excluded_historical += 1
        continue
    item = {"so": r["sales_order_id"], "due": (p or "")[:10], "kind": r["kind"]}
    if p and p < snap:
        risk["red"].append(item); overdue += 1
    elif p and p < red_line:
        risk["red"].append(item)
    elif p and p < yellow_line:
        risk["yellow"].append(item)
    else:
        risk["green"].append(item)
for k in risk:
    risk[k] = sorted(risk[k], key=lambda x: x["due"])

stages = [dict(r) for r in q("""
    SELECT stage_code, MAX(stage_name) stage_name, COUNT(*) total,
           SUM(CASE WHEN stage_status='已完成' THEN 1 ELSE 0 END) completed,
           SUM(CASE WHEN stage_status='进行中' THEN 1 ELSE 0 END) running,
           SUM(CASE WHEN stage_status='未开始' THEN 1 ELSE 0 END) pending,
           SUM(CASE WHEN planned_end_at IS NOT NULL AND planned_end_at < ?
                     AND stage_status <> '已完成' THEN 1 ELSE 0 END) overdue
    FROM stage_nodes GROUP BY stage_code ORDER BY MIN(sequence)""", snap)]
for s in stages:
    s["completion_rate"] = round(s["completed"] / s["total"] * 100, 1) if s["total"] else 0

raw = [dict(r) for r in q("""SELECT source_status, COUNT(DISTINCT sales_order_id) n
    FROM stage_nodes WHERE stage_code='PLAN' AND source_status IS NOT NULL
    GROUP BY source_status ORDER BY n DESC""")]
dist = {p: 0 for p in PHASE_ORDER}
for r in raw:
    dist[PHASE_MAP.get(r["source_status"], "其他/待确认")] += r["n"]

ingestion = [dict(r) for r in q("""SELECT source_system, run_at, input_record_count,
    loaded_record_count, quarantined_record_count,
    CASE WHEN run_status LIKE '%成功%' OR run_status LIKE '%完成%' THEN '已完成'
         WHEN run_status LIKE '%待OCR%' THEN '待OCR'
         WHEN run_status LIKE '%部分%' OR run_status LIKE '%OCR%' THEN '处理中'
         WHEN run_status LIKE '%待%' THEN '接入中' ELSE '需关注' END status, note
    FROM ingestion_runs ORDER BY run_id""")]

workcenters = [dict(r) for r in q("""
    SELECT w.workcenter_id, w.workcenter_name,
           COUNT(DISTINCT CASE WHEN n.stage_code='PROCESS' THEN n.sales_order_id END) active_orders
    FROM workcenters w LEFT JOIN stage_nodes n USING(workcenter_id)
    GROUP BY w.workcenter_id ORDER BY w.workcenter_id""")]
labor_rows = q("SELECT COUNT(*) FROM labor_logs")[0][0]

# 订单节点全量（含 deadline_state），浏览器本地筛选
month_start = snap[:8] + "01"

def dl(state, pe):
    """与18790实时版/交付风险预警同口径: 当月前旧交期=历史结转, 无计划=待排程"""
    if state == "已完成":
        return "已完成"
    if not pe:
        return "待排程"
    if pe < month_start:
        return "历史结转"
    if pe < snap:
        return "超时"
    if pe[:10] < red_line:
        return "即将到期"
    return "按期"

_SNAP_DATE = snap_day


def _overdue_days(status, planned_end):
    """未完成且计划结束日 < 快照日 → 超时天数; 否则 0。"""
    if status == "已完成" or not planned_end:
        return 0
    pe = str(planned_end)[:10]
    try:
        from datetime import date as _d
        return max(0, (_SNAP_DATE - _d.fromisoformat(pe)).days)
    except (ValueError, TypeError):
        return 0


_om = {r["sales_order_id"]: dict(r) for r in q(
    """SELECT o.sales_order_id, o.contract_name, o.unique_id, o.contract_no,
              COALESCE(c.customer_name, '') customer_name
       FROM orders o LEFT JOIN customers c ON c.customer_id=o.customer_id""")}
_slim = ("sales_order_id", "contract_name", "unique_id", "contract_no", "customer_name")
orders = [{"sales_order_id": r["sales_order_id"],
           **{k: (_om.get(r["sales_order_id"]) or {}).get(k) or "" for k in
              ("contract_name", "unique_id", "contract_no", "customer_name")},
           "stage_code": r["stage_code"], "stage_name": r["stage_name"],
           "stage_status": r["stage_status"], "workcenter_id": r["workcenter_id"],
           "work_order_id": r["work_order_id"] or "",
           "planned_start_at": (r["planned_start_at"] or "")[:10],
           "planned_end_at": (r["planned_end_at"] or "")[:10],
           "actual_start_at": (r["actual_start_at"] or "")[:10],
           "actual_end_at": (r["actual_end_at"] or "")[:10],
           "source_status": r["source_status"] or "",
           "deadline_state": dl(r["stage_status"], r["planned_end_at"]),
           "overdue_days": _overdue_days(r["stage_status"], r["planned_end_at"])}
          for r in q("SELECT * FROM stage_nodes ORDER BY sales_order_id, sequence")]

report_day = (snap_day - dt.timedelta(days=1)).isoformat()
brief_row = q("""
    SELECT
      (SELECT COUNT(DISTINCT sh.sales_order_id) FROM shipments sh
       WHERE sh.received_at LIKE ? || '%'
         AND NOT EXISTS (SELECT 1 FROM shipments sh2
                         WHERE sh2.sales_order_id=sh.sales_order_id
                           AND (sh2.received_at IS NULL OR sh2.received_at=''))) AS completed_order_count,
      (SELECT COUNT(DISTINCT work_order_id) FROM exceptions WHERE opened_at LIKE ? || '%') AS exception_count,
      (SELECT COUNT(*) FROM expenses WHERE submitted_at LIKE ? || '%') AS reimbursement_count,
      (SELECT ROUND(COALESCE(SUM(amount),0),2) FROM expenses WHERE submitted_at LIKE ? || '%') AS reimbursement_amount
""", report_day, report_day, report_day, report_day)[0]
import datahub_api as _api
brief_history = _api.daily_brief_history(30)
del _api
import daily_brief as _db
brief_today_text = _db.run(DB, (snap_day - dt.timedelta(days=1)).isoformat())["brief"]
del _db
brief = {"report_date": report_day,
         "completed_order_count": brief_row[0], "exception_count": brief_row[1],
         "reimbursement_count": brief_row[2], "reimbursement_amount": brief_row[3]}

# ---------- 生产执行分析(2026 1-9月): 多维数据 + 移动平均/线性回归/下滑判定 ----------
MONTHS = ["2026-%02d" % m for m in range(1, 10)]


def _ma(xs, w):
    out = []
    for i in range(len(xs)):
        seg = [v for v in xs[max(0, i - w + 1):i + 1] if v is not None]
        out.append(round(sum(seg) / len(seg), 4) if seg else None)
    return out


def _slope(ys):
    pts = [(i, v) for i, v in enumerate(ys) if v is not None]
    n = len(pts)
    if n < 2:
        return 0.0
    mx = sum(i for i, _ in pts) / n
    my = sum(v for _, v in pts) / n
    den = sum((i - mx) ** 2 for i, _ in pts)
    return (sum((i - mx) * (v - my) for i, v in pts) / den) if den else 0.0


def _regline(ys):
    sl = _slope(ys)
    pts = [(i, v) for i, v in enumerate(ys) if v is not None]
    if not pts:
        return [None] * len(ys)
    b = sum(v for _, v in pts) / len(pts) - sl * (sum(i for i, _ in pts) / len(pts))
    return [round(sl * i + b, 4) for i in range(len(ys))]


def _verdict(ys, unit=""):
    """移动平均+线性回归综合判定: 下行提醒 / 平稳 / 上行。"""
    if not [v for v in ys if v is not None]:
        return {"level": "none", "text": "无数据"}
    ma3, ma7 = _ma(ys, 3), _ma(ys, 7)
    sl = _slope(ys)
    tail = [v for v in ys if v is not None]
    short, long_ = ma3[-1], ma7[-1]
    if short is not None and long_ not in (None, 0) and short < long_ and sl < 0:
        pct = (short / long_ - 1) * 100
        return {"level": "down", "slope": round(sl, 4), "ma3": short, "ma7": long_,
                "text": "⚠️ 下行：近3月均值 %.2f%s 较近7月均值 %.2f%s 下降 %.1f%%，回归斜率 %.4f/月" %
                        (short, unit, long_, unit, abs(pct), sl)}
    if sl > 0.02 * (abs(tail[-1]) or 1):
        return {"level": "up", "slope": round(sl, 4), "ma3": short, "ma7": long_,
                "text": "📈 上行：回归斜率 %.4f/月，近3月均值 %.2f%s" % (sl, short or 0, unit)}
    return {"level": "flat", "slope": round(sl, 4), "ma3": short, "ma7": long_,
            "text": "✅ 平稳：回归斜率 %.4f/月，波动正常" % sl}


_mset = lambda rows, key="n": {r[0]: r[1] for r in rows}
created_m = _mset(q("SELECT substr(created_at,1,7), COUNT(*) FROM orders WHERE created_at>='2026-01-01' GROUP BY 1"))
ship_m = q("""SELECT substr(received_at,1,7) ym, COUNT(*) n, ROUND(COALESCE(SUM(quantity),0),0) qty
              FROM shipments WHERE received_at IS NOT NULL AND received_at<>'' AND received_at>='2026-01-01' GROUP BY 1""")
done_m = {r[0]: r[1] for r in ship_m}
qty_m = {r[0]: r[2] for r in ship_m}
comp = q("""WITH s AS (SELECT sales_order_id, MAX(received_at) last_at FROM shipments
              WHERE received_at IS NOT NULL AND received_at<>'' GROUP BY 1)
  SELECT substr(s.last_at,1,7) ym, COUNT(*) n,
    SUM(CASE WHEN substr(s.last_at,1,10) <= substr(o.promised_delivery_at,1,10) THEN 1 ELSE 0 END) ontime,
    ROUND(AVG(CAST(julianday(substr(s.last_at,1,10)) - julianday(substr(o.created_at,1,10)) AS REAL)),1) cycle
  FROM v_current_orders o JOIN s USING(sales_order_id)
  WHERE s.last_at>='2026-01-01' GROUP BY 1""")
ontime_m = {r[0]: (r[2], r[1]) for r in comp}   # (准时数, 完成数)
cycle_m = {r[0]: r[3] for r in comp}
stage_m = {}
for r in q("""SELECT stage_code, substr(actual_end_at,1,7) ym, COUNT(*) n FROM stage_nodes
              WHERE actual_end_at IS NOT NULL AND actual_end_at>='' AND actual_end_at>='2026-01-01'
              GROUP BY 1,2"""):
    stage_m.setdefault(r[0], {})[r[1]] = r[2]
eff = {}
for r in q("""SELECT workcenter_id, substr(work_date,1,7) ym,
              ROUND(SUM(earned_standard_hours)/SUM(actual_hours),4) p
              FROM labor_logs GROUP BY 1,2"""):
    eff.setdefault(r[0], {})[r[1]] = r[2]

series = {
    "created": [created_m.get(m, 0) for m in MONTHS],
    "done": [done_m.get(m, 0) for m in MONTHS],
    "qty": [qty_m.get(m, 0) for m in MONTHS],
    "ontime_rate": [round(ontime_m[m][0] / ontime_m[m][1] * 100, 1) if m in ontime_m and ontime_m[m][1] else None for m in MONTHS],
    "cycle": [cycle_m.get(m) for m in MONTHS],
}
verdicts = {k: _verdict(v, "%" if k == "ontime_rate" else ("天" if k == "cycle" else "")) for k, v in series.items()}
wc_eff = {}
for wc in sorted(eff):
    ys = [eff[wc].get(m) for m in MONTHS]
    wc_eff[wc] = {"values": ys, "ma3": _ma(ys, 3), "reg": _regline(ys), "verdict": _verdict(ys)}

def _ai(name, v, unit, src, advice):
    ys = [y for y in series.get(name, []) if y is not None] if name in series else []
    vals = ys or [y for y in (wc_eff.get(name.replace("wc_", ""), {}) or {}).get("values", []) if y is not None]
    last = vals[-1] if vals else None
    label = "该指标" if not name.startswith("wc_") else ("小组 " + name.replace("wc_", "") + " 人效")
    return ("基于 %s：%s当前值 %s%s，%s。%s" % (src, label,
            last if last is not None else "—", unit, v["text"], advice))

ai_notes = {
    "done": _ai("done", verdicts["done"], " 单/月", "shipments 签收记录(2026-01~09)",
                "建议核对近3月排产负荷与发货能力匹配度, 关注延期订单占比。"),
    "qty": _ai("qty", verdicts["done"], " 台/月", "shipments 签收数量",
               "产量与完成量同向, 可结合缺料/缺件记录核查波动原因。"),
    "ontime_rate": _ai("ontime_rate", verdicts["ontime_rate"], "%",
                       "v_current_orders × 签收日期 vs 承诺交期",
                       "准时率下滑时优先排查长周期订单的承诺交期设定是否过紧。"),
    "cycle": _ai("cycle", verdicts["cycle"], " 天",
                 "订单创建日→全量签收日间隔",
                 "周期上升通常意味着加工/物流瓶颈, 建议查看五节点超时分布。"),
}
for wc in wc_eff:
    ai_notes["wc_" + wc] = _ai("wc_" + wc, wc_eff[wc]["verdict"], " 人效比",
                               "labor_logs 工时日志(标准工时/实际人时)",
                               "人效下滑需结合设备停机日志与人员出勤核查。")


_d_total = sum(series["done"]); _q_total = sum(series["qty"])
_ot = [v for v in series["ontime_rate"] if v is not None]
_cy = [v for v in series["cycle"] if v is not None]
prod = {
    "months": MONTHS, "series": series,
    "ma": {k: _ma(v, 3) for k, v in series.items()},
    "reg": {k: _regline(v) for k, v in series.items()},
    "verdicts": verdicts, "stage_m": stage_m, "wc_eff": wc_eff, "ai_notes": ai_notes,
    "sources": {"done": "shipments 签收记录 · %d 单" % _d_total, "qty": "shipments · %d 台" % _q_total,
                 "ontime_rate": "订单×签收 vs 承诺交期", "cycle": "创建→签收间隔",
                 "eff": "labor_logs 工时日志 · %d 条" % q("SELECT COUNT(*) FROM labor_logs")[0][0]},
    "totals": {"done": _d_total, "qty": _q_total, "created": sum(series["created"]),
               "ontime": round(sum(_ot) / len(_ot), 1) if _ot else None,
               "cycle": round(sum(_cy) / len(_cy), 1) if _cy else None},
    "agent": (
        "【趋势预测智能体 · 综合诊断】基于 2026 年 1-9 月 %d 张订单、%d 单交付（%d 台）与 %d 条工时记录："
        "① 交付量：%s；② 准时率：%s；③ 平均交付周期 %s 天：%s；④ 人效方面，%s。"
        "建议关注带 ⚠️ 标记的指标，结合设备停机与排产负荷核查下滑根因。") % (
        sum(series["created"]), _d_total, _q_total, q("SELECT COUNT(*) FROM labor_logs")[0][0],
        verdicts["done"]["text"], verdicts["ontime_rate"]["text"],
        (round(sum(_cy) / len(_cy), 1) if _cy else "—"), verdicts["cycle"]["text"],
        "；".join("%s %s" % (wc, v["verdict"]["text"]) for wc, v in wc_eff.items()) or "暂无工时数据"),
}

# ---------- 数据源可视化(点击即看: 行数/最新记录/逐月记录量/前15行预览) ----------
DS_TABLES = [
    ("订单表(机器下单)", "orders", "created_at"),
    ("发货签收", "shipments", "received_at"),
    ("订单流转节点", "stage_nodes", "planned_start_at"),
    ("售后工单", "exceptions", "opened_at"),
    ("报销流水", "expenses", "submitted_at"),
    ("工时日志", "labor_logs", "work_date"),
    ("ERP销售合同", "erp_contracts", "signed_at"),
    ("合同台账", "contracts", "signed_at"),
    ("采购明细", "procurement_lines", "ordered_at"),
    ("库存流水", "wms_transactions", "occurred_at"),
    ("客户主数据", "customers", None),
    ("产品主数据", "products", None),
]
datasources = []
for _label, _tbl, _dcol in DS_TABLES:
    try:
        _cols = [r[1] for r in q("PRAGMA table_info(%s)" % _tbl)]
        if not _cols:
            continue
        _n = q("SELECT COUNT(*) FROM %s" % _tbl)[0][0]
        _monthly, _latest = [], ""
        if _dcol and _dcol in _cols:
            _monthly = [{"m": r[0], "n": r[1]} for r in q(
                "SELECT substr(%s,1,7), COUNT(*) FROM %s WHERE %s IS NOT NULL AND %s<>'' "
                "GROUP BY 1 ORDER BY 1 DESC LIMIT 12" % (_dcol, _tbl, _dcol, _dcol))][::-1]
            _latest = (q("SELECT MAX(%s) FROM %s WHERE %s IS NOT NULL AND %s<>''"
                         % (_dcol, _tbl, _dcol, _dcol))[0][0] or "")[:19]
        _pc = _cols[:8]
        _prev = []
        for _r in q("SELECT %s FROM %s LIMIT 15" % (",".join('"%s"' % c for c in _pc), _tbl)):
            _prev.append({c: (str(v)[:26] if v is not None else "") for c, v in zip(_pc, _r)})
        datasources.append({"key": _tbl, "label": _label, "rows": _n, "fields": len(_cols),
                            "latest": _latest, "monthly": _monthly, "preview_cols": _pc,
                            "preview": _prev, "date_col": _dcol or ""})
    except Exception:
        continue

# ---------- 数据中台融合分析(订单×工时×人员×成本 → 人效-产值-损耗三维指标) ----------
try:
    import crm_sync as _crm
    _crm_stats = _crm.fetch_stats()
except Exception:
    _crm_stats = {}

_months9 = ["2026-%02d" % m for m in range(1, 10)]
_emp_n = q("SELECT COUNT(*) FROM employees")[0][0]
_ord_m = {r[0]: r[1] for r in q(
    "SELECT substr(created_at,1,7), COUNT(*) FROM orders WHERE created_at>='2026-01-01' GROUP BY 1")}
_qty_m = {r[0]: r[2] for r in q(
    """SELECT substr(received_at,1,7), COUNT(*), ROUND(COALESCE(SUM(quantity),0),0)
       FROM shipments WHERE received_at IS NOT NULL AND received_at<>'' AND received_at>='2026-01-01' GROUP BY 1""")}
_lab_m = {r[0]: r[1] for r in q(
    "SELECT substr(work_date,1,7), ROUND(SUM(actual_hours),0) FROM labor_logs GROUP BY 1")}
_cost_m = {r[0]: r[1] for r in q(
    "SELECT substr(work_date,1,7), ROUND(SUM(actual_hours*hourly_rate),0) FROM labor_logs GROUP BY 1")}
# 产值: 当月全量签收订单的合同金额
_rev_m = {r[0]: r[1] for r in q(
    """WITH s2 AS (SELECT sales_order_id, MAX(received_at) last_at FROM shipments
        WHERE received_at IS NOT NULL AND received_at<>'' GROUP BY 1)
    SELECT substr(s2.last_at,1,7), ROUND(COALESCE(SUM(o.contract_amount),0),0)
    FROM v_current_orders o JOIN s2 USING(sales_order_id)
    WHERE s2.last_at>='2026-01-01' GROUP BY 1""")}

fusion_rows = []
for m in _months9:
    orders_n = _ord_m.get(m, 0)
    qty = _qty_m.get(m, 0)
    hours = _lab_m.get(m, 0)
    cost = _cost_m.get(m, 0)
    revenue = _rev_m.get(m, 0)
    eff = round(qty / _emp_n, 2) if _emp_n else 0            # 反推综合人效: 台/人/月
    loss = round(cost / revenue * 100, 1) if revenue else None  # 损耗率: 人工成本/产值
    fusion_rows.append({"month": m, "orders": orders_n, "qty": qty, "hours": hours,
                        "headcount": _emp_n, "cost": cost, "revenue": revenue,
                        "eff": eff, "loss": loss})

_ftot = {"orders": sum(r["orders"] for r in fusion_rows), "qty": sum(r["qty"] for r in fusion_rows),
         "revenue": sum(r["revenue"] for r in fusion_rows), "cost": sum(r["cost"] for r in fusion_rows)}
_fusion = {
    "months": _months9, "rows": fusion_rows, "headcount": _emp_n, "totals": _ftot,
    "crm": _crm_stats,
    "erp": {"contracts": q("SELECT COUNT(*) FROM erp_contracts")[0][0]},
    "excel": {"sources": q("SELECT COUNT(*) FROM ingestion_runs WHERE source_system NOT LIKE 'CRM:%' AND source_system NOT LIKE 'ERP:%'")[0][0]},
    "agent": ("【跨域数据融合智能体】已联通三域数据：ERP(zbintel117_erp, %d 条销售合同) + CRM伙伴云(%s) + Excel业务表(%d 类)。"
              "按月聚合 订单量×工时×人员数(%d人)×成本：1-9月累计新增订单 %d 单、出库 %d 台、产值 %.0f 元、人工成本 %.0f 元。"
              "综合人效(按出库数量反推) = 出库台数÷人数，当前人效按出库口径核算，labor_logs 工时实绩持续接入中；"
              "损耗率 = 人工成本÷产值。接入真实报工/MES 后人效口径将自动切换。") % (
        q("SELECT COUNT(*) FROM erp_contracts")[0][0],
        "; ".join("%s %d条" % (n, d_["total"]) for n, d_ in _crm_stats.items()) or "未连接",
        q("SELECT COUNT(*) FROM ingestion_runs WHERE source_system NOT LIKE 'CRM:%' AND source_system NOT LIKE 'ERP:%'")[0][0],
        _emp_n, _ftot["orders"], _ftot["qty"], _ftot["revenue"], _ftot["cost"]),
}

src_parts = " + ".join(f"{r[0]} {r[1]}" for r in q(
    "SELECT order_source, COUNT(*) FROM orders WHERE is_effective=1 GROUP BY 1 ORDER BY 2 DESC"))

DATA = {
    "snapshot_at": snap, "risk_lines": {"red": red_line, "yellow": yellow_line},
    "brief": brief, "brief_history": brief_history,
    "brief_today_text": brief_today_text,
    "kpis": {"effective_orders": effective, "completed_orders": completed,
             "unfinished_orders": effective - completed, "overdue_orders": overdue},
    "risk_counts": {k: len(v) for k, v in risk.items()},
    "consistency": {
        "stage_overdue": sum(1 for r in orders if r["deadline_state"] == "超时"),
        "risk_red": len(risk["red"]), "risk_yellow": len(risk["yellow"]),
        "historical_nodes": sum(1 for r in orders if r["deadline_state"] == "历史结转"),
        "pending_sched": sum(1 for r in orders if r["deadline_state"] == "待排程"),
    },
    "risk_rule": ("高=本月内已逾期或7天内到期；中=8–30天；低=超过30天或暂无承诺交期；"
        f"{month_start[:7]} 之前的旧交期订单（{excluded_historical} 单）不计入"),
    "stages": stages,
    "status_distribution": {"phases": [{"phase": p, "orders": dist[p]} for p in PHASE_ORDER],
                            "raw_status": raw,
                            "loaded": sum(r["n"] for r in raw), "source_total": 1228},
    "ingestion": ingestion, "workcenters": workcenters,
    "productivity_status": "接入中" if labor_rows == 0 else "可用",
    "prod": prod, "datasources": datasources, "fusion": _fusion,
    "trend": [dict(r) for r in q("""SELECT workcenter_id, substr(work_date,1,7) ym,
           ROUND(SUM(earned_standard_hours)/SUM(actual_hours),4) productivity,
           ROUND(SUM(earned_standard_hours*standard_value_rate),0) work_value
           FROM labor_logs GROUP BY 1,2 ORDER BY 1,2""")],
    "orders": orders, "drill": risk,
    "n_contract": q("SELECT COUNT(*) FROM contracts")[0][0],
    "n_wms": q("SELECT COUNT(*) FROM wms_transactions")[0][0],
    "n_ship": q("SELECT COUNT(*) FROM shipments")[0][0],
    "n_exc": q("SELECT COUNT(*) FROM exceptions")[0][0],
}
con.close()
DATA_JS = json.dumps(DATA, ensure_ascii=False, separators=(",", ":"))

# 页面模板（与 18790 侧边栏版同款样式；数据内嵌，无任何 fetch）
page = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>数据中枢 · 订单交付与生产协同</title>
<style>
  :root { --ink:#1F2329; --sub:#646A73; --bg:#F5F6F7; --red:#C7000B; --side:#FFFFFF; --line:#EDEFF2; }
  * { box-sizing:border-box; }
  html,body { height:100%; }
  body { margin:0; font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif; background:var(--bg); color:var(--ink); }
  .layout { display:flex; min-height:100vh; }
  aside { width:200px; background:var(--side); border-right:1px solid var(--line);
          position:fixed; top:0; bottom:0; left:0; overflow-y:auto; z-index:20; }
  .brand { background:linear-gradient(90deg,#B00A0A,#C7000B 55%,#E23A22); color:#fff; padding:14px 16px 12px; }
  .brand h1 { margin:0; font-size:15px; letter-spacing:.5px; }
  .brand .sub { font-size:11px; opacity:.88; margin-top:4px; }
  .nav-group { font-size:11px; color:var(--sub); padding:12px 16px 4px; letter-spacing:.5px; }
  .nav-item { display:flex; align-items:center; gap:8px; padding:8px 16px; font-size:13px;
              color:var(--ink); cursor:pointer; border-left:3px solid transparent; user-select:none; }
  .nav-item:hover { background:#FAFBFC; }
  .nav-item.active { background:#FFF1F0; color:var(--red); border-left-color:var(--red); font-weight:600; }
  .nav-item .ic { width:16px; text-align:center; opacity:.85; }
  .nav-item .pill { margin-left:auto; background:#F0F0F0; color:var(--sub); border-radius:9px; font-size:10.5px; padding:1px 7px; }
  .nav-item.active .pill { background:#FFE1E0; color:var(--red); }
  main { flex:1; margin-left:200px; }
  header { background:#fff; border-bottom:1px solid var(--line); padding:11px 20px;
           display:flex; align-items:center; gap:12px; position:sticky; top:0; z-index:10; }
  header h2 { margin:0; font-size:15.5px; }
  header .snap { font-size:12px; color:var(--sub); }
  .content { padding:16px 20px 42px; max-width:none; }
  .page { display:none; }
  .page.active { display:block; }
  .kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
  .kpi { background:#fff; border-radius:10px; padding:13px 16px; box-shadow:0 1px 4px rgba(0,0,0,.06); }
  .kpi-label { font-size:12px; color:var(--sub); }
  .kpi-value { font-size:23px; font-weight:700; margin-top:4px; }
  .kpi-note { font-size:11px; color:var(--sub); margin-top:3px; }
  .card { background:#fff; border-radius:10px; padding:15px 17px; box-shadow:0 1px 4px rgba(0,0,0,.06); margin-top:13px; }
  .card h3 { margin:0 0 9px; font-size:14.5px; }
  .card h3 .tag { font-size:11px; color:var(--sub); font-weight:400; margin-left:8px; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  .grid2 > .card { margin-top:12px; }
  @media (max-width:1000px){ .grid2{grid-template-columns:1fr} .kpis{grid-template-columns:1fr 1fr} }
  table { border-collapse:collapse; width:100%; font-size:12.5px; margin-top:8px; }
  th,td { border-bottom:1px solid #F0F0F0; padding:6px 8px; text-align:left; white-space:nowrap; }
  th { color:var(--sub); font-weight:500; position:sticky; top:0; background:#fff; }
  .scroll { max-height:56vh; overflow:auto; border-radius:8px; }
  #page-query .card { display:flex; flex-direction:column; height:calc(100vh - 118px); }
  #page-query .scroll { flex:1; min-height:300px; max-height:none; }
  #qOut { font-size:13px; }
  #qOut td:nth-child(2) { white-space:normal; min-width:300px; line-height:1.5; }
  #briefTable tbody tr.b-row { cursor:pointer; }
  #briefTable tbody tr.b-row:hover { background:#FBF3F4; }
  #briefTable .mini { display:inline-block; height:8px; background:#A6192E; border-radius:2px;
                      vertical-align:middle; margin-right:6px; min-width:2px; }
  #briefTable .hol { font-size:10px; color:#fff; background:#D48806; border-radius:3px;
                     padding:1px 5px; margin-left:5px; vertical-align:1px; }
  #briefTable .wkend { color:var(--sub); }
  #briefTable tr.b-detail td { background:#FAFBFC; font-size:12px; color:var(--ink);
                               border-top:none; padding:8px 12px; }
  .lgk { display:inline-block; width:10px; height:10px; border-radius:2px;
         margin:0 4px 0 0; vertical-align:-1px; }
  .hrow { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
  .btn-gen { background:#A6192E; color:#fff; border:none; border-radius:6px; padding:8px 15px;
             font-size:13px; cursor:pointer; white-space:nowrap; }
  .btn-gen:hover { background:#8C1526; }
  .btn-gen:disabled { opacity:.55; cursor:wait; }
  .grid-brief { display:grid; grid-template-columns:minmax(0,2fr) minmax(0,1fr); gap:0 12px; }
  .grid-brief > .card, .grid-brief > div > .card { margin-top:12px; }
  @media (max-width:1000px){ .grid-brief{grid-template-columns:1fr} }
  .sc-row { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:6px; }
  .sc { background:#FAFBFC; border:1px solid #EDEFF2; border-radius:6px; padding:4px 8px;
        font-size:11.5px; color:var(--sub); }
  .sc b { color:var(--ink); }
  .pl-sec { font-size:12px; color:var(--sub); margin:9px 0 2px; font-weight:600; }
  .pl-row { display:flex; justify-content:space-between; gap:8px; padding:5px 0;
            border-bottom:1px dashed #F0F0F0; font-size:12.5px; }
  .pl-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .pl-meta { color:var(--sub); font-size:11px; }
  .pl-amt { font-weight:600; white-space:nowrap; }
  .empty-mini { color:var(--sub); font-size:12px; padding:6px 0; }
  .bmask { position:fixed; inset:0; background:rgba(15,18,22,.48); display:none;
           align-items:center; justify-content:center; z-index:120; }
  .bmask.on { display:flex; }
  .bmodal { background:#fff; border-radius:12px; width:min(680px,94vw); max-height:82vh;
            display:flex; flex-direction:column; box-shadow:0 12px 40px rgba(0,0,0,.22); }
  .bm-head { display:flex; justify-content:space-between; align-items:center;
             padding:13px 18px; border-bottom:1px solid #F0F0F0; }
  .bm-close { border:none; background:none; font-size:14px; cursor:pointer; color:var(--sub); }
  .bm-meta { padding:10px 18px 0; font-size:12px; color:var(--sub); line-height:1.8; }
  .bm-body { padding:12px 18px 18px; overflow:auto; }
  .brief-pre { white-space:pre-wrap; word-break:break-word; font-family:inherit; font-size:13px;
               line-height:1.95; background:#FAFBFC; border:1px solid #F0F0F0; border-radius:8px;
               padding:12px 14px; margin:0; }
  .empty { color:var(--sub); font-size:13px; padding:16px 4px; }
  .chips { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
  .chip { border:1px solid #E0E2E6; background:#FAFBFC; color:var(--ink); border-radius:16px;
          padding:5px 12px; font-size:12.5px; cursor:pointer; }
  .chip:hover { border-color:#FFCCC7; background:#FFF8F7; }
  #askSql details { margin-top:8px; }
  #askSql summary { cursor:pointer; font-size:12px; color:#1F6FEB; }
  #askSql pre { background:#FAFBFC; border:1px solid #F0F0F0; border-radius:8px; padding:10px 12px;
                font-size:12px; overflow:auto; white-space:pre-wrap; }
  .note { margin-top:8px; font-size:12px; color:var(--sub); }
  .meta { font-size:12px; color:var(--sub); margin-top:8px; }
  .badge { border-radius:10px; padding:2px 8px; font-size:11px; cursor:default; }
  .badge.alert { color:#C7000B; background:#FFF1F0; }
  .badge.ok { color:#2E8B57; background:#F0FFF4; }
  .badge.gray { color:#646A73; background:#F0F0F0; }
  .badge.amber { color:#D48806; background:#FFFBE6; }
  .clickable { cursor:pointer; }
  .stage-row { padding:9px 0; border-top:1px solid #F0F0F0; }
  .stage-row:first-of-type { border-top:0; }
  .stage-head { display:flex; align-items:center; gap:12px; font-size:13px; flex-wrap:wrap; }
  .stage-name { min-width:84px; display:flex; align-items:center; font-weight:600; }
  .dot { width:10px; height:10px; border-radius:50%; display:inline-block; margin-right:8px; }
  .stage-bar { height:8px; background:#F0F0F0; border-radius:8px; overflow:hidden; margin:7px 0 4px 16px; }
  .stage-bar span { display:block; height:100%; border-radius:8px; }
  .stage-meta { margin-left:16px; color:var(--sub); font-size:11px; display:flex; gap:14px; flex-wrap:wrap; }
  .filters { display:flex; gap:9px; flex-wrap:wrap; align-items:center; }
  .filters label { font-size:12px; color:var(--sub); }
  input[type=text] { border:1px solid #E0E2E6; border-radius:8px; padding:7px 10px; font-size:13px; width:170px; }
  select { border:1px solid #E0E2E6; border-radius:8px; padding:7px 8px; font-size:13px; background:#fff; }
  button.primary { background:var(--red); color:#fff; border:0; border-radius:8px; padding:8px 15px; font-size:13px; cursor:pointer; }
  button.ghost { background:#fff; color:var(--red); border:1px solid var(--red); border-radius:8px; padding:7px 12px; font-size:13px; cursor:pointer; }
  button.ghost.blue { color:#1F6FEB; border-color:#1F6FEB; }
  .risk-cards { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
  .risk-card { border-radius:10px; padding:12px 14px; cursor:pointer; border:1px solid transparent; }
  .risk-card:hover { box-shadow:0 2px 10px rgba(0,0,0,.10); }
  .risk-card.red { background:#FFF1F0; border-color:#FFCCC7; }
  .risk-card.yellow { background:#FFFBE6; border-color:#FFE58F; }
  .risk-card.green { background:#F0FFF4; border-color:#B7EB8F; }
  .risk-num { font-size:22px; font-weight:700; }
  .risk-card.red .risk-num { color:#C7000B; }
  .risk-card.yellow .risk-num { color:#D48806; }
  .risk-card.green .risk-num { color:#2E8B57; }
  .risk-label { font-size:12px; margin-top:2px; }
  .risk-hint { font-size:11px; color:var(--sub); margin-top:3px; }
  .ph-row { display:flex; align-items:center; gap:10px; margin:8px 0; font-size:13px; }
  .ph-name { min-width:112px; }
  .ph-bar { flex:1; height:14px; background:#F0F0F0; border-radius:7px; overflow:hidden; }
  .ph-bar span { display:block; height:100%; background:linear-gradient(90deg,#1677FF,#722ED1); }
  .ph-row b { min-width:44px; text-align:right; }
  details summary { cursor:pointer; font-size:12px; color:#1F6FEB; margin-top:8px; }
  .st { border-radius:10px; padding:2px 8px; font-size:11px; white-space:nowrap; }
  .st.done { color:#2E8B57; background:#F0FFF4; }
  .st.part { color:#D48806; background:#FFFBE6; }
  .st.wait { color:#646A73; background:#F0F0F0; }
  .st.ocr  { color:#722ED1; background:#F9F0FF; }
  .st.warn { color:#C7000B; background:#FFF1F0; }
  .tabs { display:flex; gap:8px; flex-wrap:wrap; }
  .tab { border:1px solid #E0E2E6; background:#fff; border-radius:8px; padding:6px 13px; font-size:13px; cursor:pointer; }
  .tab.active { background:var(--red); color:#fff; border-color:var(--red); font-weight:600; }
  .pending-box { border:1px dashed #D9DCE0; border-radius:10px; padding:22px 16px; text-align:center;
                 color:var(--sub); font-size:13px; background:#FAFBFC; margin-top:12px; }
  .sys-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; }
  .sys-card { background:#fff; border:1px solid var(--line); border-radius:10px; padding:17px 15px;
              text-decoration:none; color:var(--ink); transition:box-shadow .15s; }
  .sys-card:hover { box-shadow:0 2px 10px rgba(0,0,0,.10); border-color:#FFCCC7; }
  .sys-ic { font-size:25px; }
  .sys-name { font-size:16px; font-weight:700; margin-top:6px; }
  .sys-url { font-size:12px; color:var(--sub); margin-top:3px; word-break:break-all; }
  .sys-open { display:inline-block; margin-top:9px; color:var(--red); border:1px solid var(--red);
              border-radius:8px; padding:4px 12px; font-size:12.5px; }
  .sys-row { display:flex; align-items:center; gap:10px; padding:9px 0; border-top:1px solid #F0F0F0;
             text-decoration:none; color:var(--ink); font-size:13.5px; font-weight:600; }
  .sys-row:first-of-type { border-top:0; }
  .sys-row .sys-url { font-weight:400; }
  .sys-row .sys-open { margin-left:auto; }
  @media (max-width:760px){ .sys-grid{grid-template-columns:1fr} }
  .quick { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:12px; }
  .q-item { background:#fff; border-radius:10px; padding:12px 14px; box-shadow:0 1px 4px rgba(0,0,0,.06);
            cursor:pointer; border:1px solid transparent; }
  .q-item:hover { border-color:#FFCCC7; }
  .q-item .q-t { font-size:13.5px; font-weight:600; margin-top:4px; }
  .q-item .q-d { font-size:11.5px; color:var(--sub); margin-top:3px; }
  @media (max-width:760px){
    aside { position:static; width:100%; border-right:0; border-bottom:1px solid var(--line); }
    main { margin-left:0; }
    .kpis,.quick,.risk-cards { grid-template-columns:1fr 1fr; }
  }
</style>
</head>
<body>
<div class="layout">
  <aside>
    <div class="brand">
      <h1>数据中枢</h1>
      <div class="sub">订单交付与生产协同</div>
    </div>
    <nav id="nav">
      <div class="nav-group">总览</div>
      <div class="nav-item active" data-page="home"><span class="ic">📊</span>经营总览</div>
      <div class="nav-item" data-page="ask"><span class="ic">🤖</span>智能问数</div>
      <div class="nav-group">订单协同</div>
      <div class="nav-item" data-page="progress"><span class="ic">⚙️</span>订单进度看板<span class="pill" id="pillProg">—</span></div>
      <div class="nav-item" data-page="query"><span class="ic">🔍</span>订单节点查询</div>
      <div class="nav-item" data-page="risk"><span class="ic">⚠️</span>交付风险预警<span class="pill" id="pillRisk">—</span></div>
      <div class="nav-group">数据治理</div>
      <div class="nav-item" data-page="ingest"><span class="ic">🔌</span>系统接入</div>
      <div class="nav-item" data-page="statusdist"><span class="ic">🏭</span>生产状态分布</div>
      <div class="nav-group">分析与简报</div>
      <div class="nav-item" data-page="fusion"><span class="ic">🧩</span>数据融合与人效</div>
      <div class="nav-item" data-page="brief"><span class="ic">📰</span>经营简报</div>
      <div class="nav-item" data-page="trend"><span class="ic">📈</span>指标趋势分析</div>
    </nav>
  </aside>

  <main>
    <header>
      <h2 id="pageTitle">经营总览</h2>
      <span class="snap" id="snapText"></span>
    </header>
    <div class="content">

      <section class="page" id="page-ask">
        <div class="card">
          <h3>智能问数 <span class="tag">用一句话提问，AI 自动生成并执行 SQL</span></h3>
          <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
            <input type="text" id="askQ" placeholder="例如：订单 KL251128-602-A 现在卡在哪个节点？" style="flex:1;min-width:260px;padding:10px 12px;font-size:14px">
            <button class="primary" id="askBtn" style="padding:10px 22px;font-size:14px">提问</button>
          </div>
          <div class="chips" id="askChips">
            <button class="chip">订单 KL251128-602-A 现在卡在哪个节点？</button>
            <button class="chip">超时时间最久的10个订单</button>
            <button class="chip">每个业务员签了多少合同、总金额多少？</button>
            <button class="chip">未收款最多的前10个客户</button>
            <button class="chip">现在有哪些生产订单在待回料？</button>
            <button class="chip">近三个月每个月下多少单？</button>
          </div>
          <div class="meta" id="askMeta"></div>
          <div id="askSql"></div>
          <div id="askOut"><div class="empty">输入问题或点击示例开始提问（AI 生成约需 20–40 秒）。</div></div>
          <div id="askErr"></div>
        </div>
      </section>

      <section class="page active" id="page-home">
        <div class="kpis">
          <div class="kpi"><div class="kpi-label">已生效订单</div><div class="kpi-value" style="color:#1F2329" id="kEff">—</div><div class="kpi-note">来源：__ORDER_SOURCES__</div></div>
          <div class="kpi"><div class="kpi-label">已全量签收</div><div class="kpi-value" style="color:#2E8B57" id="kDone">—</div><div class="kpi-note">口径=实际交付或验收回填</div></div>
          <div class="kpi"><div class="kpi-label">未全量交付</div><div class="kpi-value" style="color:#D48806" id="kUndo">—</div><div class="kpi-note">含"已出货未回签"</div></div>
          <div class="kpi"><div class="kpi-label">其中已逾期</div><div class="kpi-value" style="color:#C7000B" id="kOver">—</div><div class="kpi-note">承诺交期 &lt; 快照且未签收</div></div>
        </div>
        <div class="card">
          <h3>订单全流程进度 <span class="tag">计划→加工→质检→发货→签收 · 点击进入进度看板</span></h3>
          <div id="homeStages"></div>
        </div>
        <div class="grid2">
          <div class="card clickable" data-goto="risk">
            <h3>交付风险 <span class="tag">点击进入预警页</span></h3>
            <div class="risk-cards">
              <div class="risk-card red"><div class="risk-num" id="rRed">—</div><div class="risk-label">高风险</div></div>
              <div class="risk-card yellow"><div class="risk-num" id="rYellow">—</div><div class="risk-label">中风险</div></div>
              <div class="risk-card green"><div class="risk-num" id="rGreen">—</div><div class="risk-label">低风险</div></div>
            </div>
          </div>
          <div class="card">
            <h3>系统接入 <span class="tag">点击打开对应系统</span></h3>
            <a class="sys-row" href="https://app.huoban.com/" target="_blank" rel="noopener">🧩 CRM <span class="sys-url">app.huoban.com</span><span class="sys-open">打开 ↗</span></a>
            <a class="sys-row" href="http://192.167.30.7:6088/SYSN/view/init/home.ashx?dvn=1789859550966" target="_blank" rel="noopener">📦 ERP <span class="sys-url">192.167.30.7:6088/SYSN</span><span class="sys-open">打开 ↗</span></a>
          </div>
        </div>
        <div class="quick">
          <div class="q-item" data-goto="query"><div class="q-t">🔍 查订单卡在哪</div><div class="q-d">订单号/节点/小组查询</div></div>
          <div class="q-item" data-goto="risk"><div class="q-t">⚠️ 看超时订单</div><div class="q-d">红黄绿预警下钻</div></div>
          <div class="q-item" data-goto="trend"><div class="q-t">📈 小组趋势</div><div class="q-d">4 小组 × 9 个月人效</div></div>
        </div>
      </section>

      <section class="page" id="page-progress">
        <div class="card">
          <h3>订单全流程进度 <span class="tag">点击行查看订单明细 · 超时徽章可下钻</span></h3>
          <div id="stages"></div>
          <div class="note">超时规则（与交付风险预警同口径）：当月内 <code>planned_end_at &lt; snapshot_at</code> 且未完成 → 超时；快照当月前旧交期节点 → <b>历史结转</b>（两模块一致排除）；无计划日期 → <b>待排程</b>。</div>
          <div class="note" id="consistencyNote"></div>
        </div>
      </section>

      <section class="page" id="page-query">
        <div class="card">
          <h3>订单节点查询 <span class="tag">默认 200 条 · 加载更多 · 可导出CSV</span></h3>
          <div class="filters">
            <label>编号检索</label><input type="text" id="fOrder" placeholder="订单号/合同名称/合同编号/数据唯一编号">
            <label>节点</label>
            <select id="fStage">
              <option value="">全部</option><option value="PLAN">计划</option><option value="PROCESS">加工</option>
              <option value="QC">质检</option><option value="SHIP">发货</option><option value="SIGN">签收</option>
            </select>
            <label>状态</label>
            <select id="fStatus"><option value="">全部</option><option>已完成</option><option>进行中</option><option>未开始</option></select>
            <label>时限</label>
            <select id="fDl"><option value="">全部</option><option>超时</option><option>即将到期</option><option>按期</option><option>历史结转</option><option>待排程</option><option>已完成</option></select>
            <button class="primary" id="queryBtn">查询</button>
            <button class="ghost" id="resetBtn">重置</button>
            <button class="ghost blue" id="csvBtn">导出CSV</button>
          </div>
          <div class="meta" id="qMeta"></div>
          <div class="scroll" id="qOut"><div class="empty">输入条件后点击"查询"。</div></div>
          <div style="margin-top:10px"><button class="ghost blue" id="moreBtn" style="display:none">加载更多</button></div>
        </div>
      </section>

      <section class="page" id="page-risk">
        <div class="card">
          <h3>交付风险预警 <span class="tag">点击卡片下钻订单明细</span></h3>
          <div class="risk-cards" id="riskCards">
            <div class="risk-card red" data-bucket="red"><div class="risk-num" id="rRed2">—</div><div class="risk-label">高风险</div><div class="risk-hint">已逾期或 7 天内到期</div></div>
            <div class="risk-card yellow" data-bucket="yellow"><div class="risk-num" id="rYellow2">—</div><div class="risk-label">中风险</div><div class="risk-hint">8–30 天内到期</div></div>
            <div class="risk-card green" data-bucket="green"><div class="risk-num" id="rGreen2">—</div><div class="risk-label">低风险</div><div class="risk-hint">超过 30 天或暂无承诺交期</div></div>
          </div>
          <div class="meta" id="riskMeta"></div>
          <div id="riskDrill"></div>
        </div>
      </section>

      <section class="page" id="page-ingest">
        <div class="card">
          <h3>系统接入 <span class="tag">点击卡片打开对应系统</span></h3>
          <div class="sys-grid">
            <a class="sys-card" href="https://app.huoban.com/" target="_blank" rel="noopener">
              <div class="sys-ic">🧩</div>
              <div class="sys-name">CRM</div>
              <div class="sys-url">app.huoban.com</div>
              <div class="sys-open">打开 ↗</div>
            </a>
            <a class="sys-card" href="http://192.167.30.7:6088/SYSN/view/init/home.ashx?dvn=1789859550966" target="_blank" rel="noopener">
              <div class="sys-ic">📦</div>
              <div class="sys-name">ERP</div>
              <div class="sys-url">192.167.30.7:6088/SYSN</div>
              <div class="sys-open">打开 ↗</div>
            </a>
          </div>
          <div class="note">更多系统（MES / WMS / OA）接入待配置。</div>
        </div>
      </section>

      <section class="page" id="page-statusdist">
        <div class="card">
          <h3>生产订单状态分布 <span class="tag">原始状态映射 · 原文保留</span></h3>
          <div id="phases"></div>
          <details><summary>查看原始状态明细（生产总表"当天状态"原文）</summary><div id="rawStatus"></div></details>
          <div class="note" id="phaseNote"></div>
        </div>
      </section>

      <section class="page" id="page-fusion">
        <div class="card">
          <h3>数据中台 · 跨域数据融合 <span class="tag">跨域数据融合智能体 · ERP + CRM伙伴云 + Excel</span></h3>
          <div class="kpis" id="fusionCards" style="grid-template-columns:repeat(4,1fr)"></div>
          <div class="agentcard" id="fusionAgent"></div>
        </div>
        <div class="grid2">
          <div class="card">
            <h3>数据源联通状态 <span class="tag">三域直连</span></h3>
            <div id="domainBox"></div>
          </div>
          <div class="card">
            <h3>人效-产值-损耗 三维聚合 <span class="tag">月度 · 人效按出库数量反推</span></h3>
            <div id="fusionChart"></div>
          </div>
        </div>
        <div class="card">
          <h3>融合明细(订单量×工时×人员数×成本) <span class="tag">1-9月 · 综合人效=出库台数÷人数 · 损耗率=人工成本÷产值</span></h3>
          <div class="scroll" id="fusionTable"></div>
        </div>
        <div class="card">
          <h3>生产小组 <span class="tag">人效 = 标准工时产出 / 实际人时(工时实绩)</span></h3>
          <div class="scroll"><table>
            <thead><tr><th>小组</th><th>名称</th><th>在制订单（加工节点）</th><th>人效数据</th></tr></thead>
            <tbody id="wcBody"></tbody>
          </table></div>
        </div>
      </section>

      <section class="page" id="page-brief">
        <div class="card">
          <div class="hrow">
            <h3 style="margin:0">经营简报 <span class="tag">报告日 = 快照前一日 · 近30天逐日明细</span></h3>
            <button class="btn-gen" id="genBriefBtn" title="生成报告日简报：存档 md + 台账 + 推送消息通道（幂等）">⚡ 一键生成本日简报</button>
          </div>
          <div class="kpis" id="briefCards" style="margin-top:10px"></div>
          <div class="note" id="briefNote"></div>
        </div>
        <div class="grid2">
          <div class="card">
            <h3>签收完成 / 新增异常工单 <span class="tag">近30天 · 单</span></h3>
            <div id="briefChart1"></div>
          </div>
          <div class="card">
            <h3>报销金额 <span class="tag">近30天 · 元</span></h3>
            <div id="briefChart2"></div>
          </div>
        </div>
        <div class="grid-brief">
          <div class="card">
            <h3>逐日明细 <span class="tag">点击行展开当日完成订单 · 由新到旧</span></h3>
            <div class="scroll" style="max-height:60vh"><table id="briefTable"></table></div>
          </div>
          <div>
            <div class="card">
              <h3>今日客户动态 <span class="tag" id="briefCustTag">报告日</span></h3>
              <div id="briefCustBox"></div>
            </div>
            <div class="card">
              <h3>今日交付信息 <span class="tag">完成=全部批次签收</span></h3>
              <div id="briefDlvBox"></div>
            </div>
          </div>
        </div>
      </section>
      <div class="bmask" id="dsModal">
        <div class="bmodal" style="width:min(960px,96vw)">
          <div class="bm-head"><b id="dsTitle">数据源</b><button class="bm-close" onclick="document.getElementById('dsModal').classList.remove('on')">✕ 关闭</button></div>
          <div class="bm-body" id="dsBody"></div>
        </div>
      </div>
      <div class="bmask" id="briefModal">
        <div class="bmodal">
          <div class="bm-head"><b id="bmTitle">本日经营简报</b><button class="bm-close" id="bmClose">✕ 关闭</button></div>
          <div class="bm-meta" id="bmMeta"></div>
          <div class="bm-body"><pre class="brief-pre" id="bmText"></pre></div>
        </div>
      </div>

      <section class="page" id="page-trend">
        <div class="card">
          <h3>关键指标趋势分析 <span class="tag">趋势预测智能体 · 移动平均 + 线性回归 · 2026 年 1-9 月</span></h3>
          <div class="kpis" id="prodKpis"></div>
          <div class="agentcard" id="prodAgent"></div>
        </div>
        <div class="grid2">
          <div class="card"><h3>月度订单：新增 vs 完成 <span class="tag">单</span></h3><div id="chOrder"></div></div>
          <div class="card"><h3>交付产量 <span class="tag">台 · 含3月移动平均</span></h3><div id="chQty"></div></div>
        </div>
        <div class="grid2">
          <div class="card"><h3>交付准时率 <span class="tag">% · 回归趋势线</span></h3><div id="chOntime"></div></div>
          <div class="card"><h3>平均交付周期 <span class="tag">天 · 回归趋势线</span></h3><div id="chCycle"></div></div>
        </div>
        <div class="card">
          <h3>生产小组人效趋势 <span class="tag">标准工时/实际人时 · MA3 + 回归 · 下滑自动提醒</span></h3>
          <div id="wcEffBox"></div>
        </div>
        <div class="card">
          <h3>生产执行明细（1-9 月） <span class="tag">多维度 · 数据越全越好</span></h3>
          <div class="scroll" id="prodTable"></div>
        </div>
      </section>

    </div>
  </main>
</div>
<script>
'use strict';
const DATA = __DATA__;
const esc = s => String(s === null || s === undefined ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const fmtDT = s => s ? String(s).replace('T',' ').slice(0,19) : '—';
const $ = id => document.getElementById(id);
const STAGE_COLOR = {PLAN:'#722ED1', PROCESS:'#1677FF', QC:'#D48806', SHIP:'#2E8B57', SIGN:'#8C8C8C'};
const PAGE_TITLES = {home:'经营总览', ask:'智能问数', progress:'订单进度看板', query:'订单节点查询', risk:'交付风险预警',
                     ingest:'系统接入', statusdist:'生产状态分布', fusion:'数据融合与人效',
                     brief:'经营简报', trend:'指标趋势分析'};

/* ---- 路由 ---- */
function goto(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === 'page-' + page));
  document.querySelectorAll('#nav .nav-item').forEach(n => n.classList.toggle('active', n.dataset.page === page));
  $('pageTitle').textContent = PAGE_TITLES[page] || page;
}
document.querySelectorAll('#nav .nav-item[data-page]').forEach(n =>
  n.addEventListener('click', () => goto(n.dataset.page)));
document.querySelectorAll('[data-goto]').forEach(el =>
  el.addEventListener('click', () => goto(el.dataset.goto)));

/* ---- 渲染 ---- */
function kv(label, value, note) {
  return '<div class="kpi"><div class="kpi-label">' + label + '</div><div class="kpi-value" style="font-size:19px;color:#1F2329">' +
    value + '</div><div class="kpi-note">' + note + '</div></div>';
}
function stageRowHTML(s, compact) {
  const c = STAGE_COLOR[s.stage_code] || '#1677FF';
  const badge = s.overdue > 0
    ? '<span class="badge alert clickable" onclick="drillStage(\\'' + s.stage_code + '\\',\\'超时\\')">超时 ' + s.overdue + ' 单</span>'
    : '<span class="badge ok">按期</span>';
  const meta = compact ? '<span>进行 ' + s.running + ' · 未开 ' + s.pending + '</span>'
    : '<span>进行中 ' + s.running + '</span><span>未开始 ' + s.pending + '</span>';
  return '<div class="stage-row clickable" onclick="drillStage(\\'' + s.stage_code + '\\',\\'\\')">' +
    '<div class="stage-head"><span class="stage-name"><span class="dot" style="background:' + c + '"></span>' + esc(s.stage_name) + '</span>' +
    '<b>' + s.completed + '/' + s.total + '（' + s.completion_rate + '%）</b>' + badge + '</div>' +
    '<div class="stage-bar"><span style="width:' + s.completion_rate + '%;background:' + c + '"></span></div>' +
    '<div class="stage-meta">' + meta + '</div></div>';
}
function renderAll() {
  const d = DATA;
  $('snapText').textContent = '快照 ' + fmtDT(d.snapshot_at) + ' · 批次 ' + d.snapshot_at.slice(0,10).replace(/-/g,'');
  $('kEff').textContent = d.kpis.effective_orders.toLocaleString() + ' 单';
  $('kDone').textContent = d.kpis.completed_orders.toLocaleString() + ' 单';
  $('kUndo').textContent = d.kpis.unfinished_orders.toLocaleString() + ' 单';
  $('kOver').textContent = d.kpis.overdue_orders.toLocaleString() + ' 单';
  ['rRed','rRed2'].forEach(i => $(i).textContent = d.risk_counts.red.toLocaleString());
  ['rYellow','rYellow2'].forEach(i => $(i).textContent = d.risk_counts.yellow.toLocaleString());
  ['rGreen','rGreen2'].forEach(i => $(i).textContent = d.risk_counts.green.toLocaleString());
  $('riskMeta').textContent = '口径：高=已逾期或7天内到期；中=8–30天；低=超过30天或暂无承诺交期 · 数据时间 ' + fmtDT(d.snapshot_at);
  $('pillProg').textContent = d.stages.reduce((a, s) => a + s.overdue, 0) + ' 超时';
  const csc = DATA.consistency;
  if (csc) { const cn2 = $('consistencyNote'); if (cn2) {
    cn2.innerHTML = '🔗 交叉校验：进度看板超时节点 <b>' + csc.stage_overdue + '</b> ↔ 交付风险预警 红 <b>' + csc.risk_red + '</b> / 黄 <b>' + csc.risk_yellow + '</b>（同为当月窗口口径）· 历史结转节点 ' + csc.historical_nodes + ' · 待排程 ' + csc.pending_sched; } }
  $('pillRisk').textContent = d.risk_counts.red.toLocaleString() + ' 红';
  $('homeStages').innerHTML = d.stages.map(s => stageRowHTML(s, true)).join('');
  $('stages').innerHTML = d.stages.map(s => stageRowHTML(s, false)).join('');

  const ph = d.status_distribution.phases, mx = Math.max.apply(null, ph.map(x => x.orders).concat([1]));
  $('phases').innerHTML = ph.map(p =>
    '<div class="ph-row"><span class="ph-name">' + esc(p.phase) + '</span>' +
    '<div class="ph-bar"><span style="width:' + Math.round(p.orders / mx * 100) + '%"></span></div>' +
    '<b>' + p.orders + ' 单</b></div>').join('');
  $('rawStatus').innerHTML = '<table><thead><tr><th>原始状态（当天状态原文）</th><th>订单数</th></tr></thead><tbody>' +
    d.status_distribution.raw_status.map(r => '<tr><td>' + esc(r.source_status) + '</td><td>' + r.n + '</td></tr>').join('') + '</tbody></table>';
  const ex = d.status_distribution;
  $('phaseNote').textContent = '提取比例：' + ex.loaded + '/' + ex.source_total + '（' + (ex.loaded / ex.source_total * 100).toFixed(1) + '%）· 其余排产表已并入节点数据';

  const F = d.fusion || {};
  $('fusionCards').innerHTML =
    kv('ERP 销售合同', (F.erp ? F.erp.contracts : 0).toLocaleString() + ' 条', 'zbintel117_erp 直连') +
    kv('CRM 伙伴云', F.crm && Object.keys(F.crm).length ? Object.values(F.crm).reduce((a, b) => a + b.total, 0).toLocaleString() + ' 条' : '未连接', Object.keys(F.crm || {}).length + ' 张表直连') +
    kv('Excel 业务表', (F.excel ? F.excel.sources : 0) + ' 类', '14个业务表导出') +
    kv('融合指标', F.totals ? (F.totals.qty + ' 台/' + F.totals.orders + ' 单') : '—', '1-9月出库/新增');
  if ($('fusionAgent') && F.agent)
    $('fusionAgent').innerHTML = '<div class="name">🤖 跨域数据融合智能体</div><p>' + esc(F.agent) + '</p>';

  if ($('domainBox') && F.crm) {
    const dm = (name, icon, color, items, note) =>
      '<div style="display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px dashed var(--line)">' +
      '<span style="font-size:22px">' + icon + '</span><div><b style="color:' + color + '">' + name + '</b>' +
      '<div class="note" style="margin:2px 0 4px">' + note + '</div><div style="font-size:12px">' +
      items.map(i2 => '<span class="tag ' + (i2[2] ? 'green' : 'red') + '" style="margin:1px 3px">' + i2[0] + ' ' + i2[1] + '</span>').join('') +
      '</div></div></div>';
    const crmItems = Object.entries(F.crm).map(([n, v]) => [n, v.total + '条', v.ok]);
    $('domainBox').innerHTML =
      dm('ERP 系统', '🏢', '#1F6FEB', [['销售合同', (F.erp || {}).contracts || 0, true]], 'SQL Server 192.167.30.7 · zbintel117_erp · TDS 7.0') +
      dm('CRM 伙伴云', '☁️', '#D48806', crmItems, 'api.huoban.com 直连 · OpenAPI v1') +
      dm('Excel 业务表', '📊', '#2E7D32', [['订单/合同/售后/库存/采购', '已入库', true]], '14 个业务表导出 · BiTable');
  }

  if ($('fusionChart') && F.rows) {
    const W = 880, H = 220, pl = 50, pr = 12, pt = 22, pb = 26;
    const mx = Math.max.apply(null, F.rows.map(r => r.qty));
    const mxc = Math.max.apply(null, F.rows.map(r => r.revenue));
    const X = i => pl + i * (W - pl - pr) / Math.max(F.rows.length - 1, 1);
    const Yq = v => pt + (1 - v / mx) * (H - pt - pb);
    const Yr = v => pt + (1 - v / mxc) * (H - pt - pb);
    let g = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block">';
    g += '<text x="' + pl + '" y="12" font-size="11" fill="#646A73">左Y轴: 出库量(台) · 右Y轴参考: 产值(元)</text>';
    const bw = Math.min(26, (W - pl - pr) / F.rows.length * 0.5);
    F.rows.forEach((r, i) => {
      const x = X(i) - bw / 2;
      g += '<rect x="' + x.toFixed(1) + '" y="' + Yq(r.qty).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + (H - pb - Yq(r.qty)).toFixed(1) + '" rx="2" fill="#A6192E" opacity="0.75"><title>' + r.month + '：出库' + r.qty + '台</title></rect>';
      g += '<circle cx="' + X(i).toFixed(1) + '" cy="' + Yr(r.revenue).toFixed(1) + '" r="3" fill="#2E7D32"><title>' + r.month + '：产值' + r.revenue + '元</title></circle>';
      g += '<text x="' + X(i).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle" font-size="9" fill="#9AA0A6">' + r.month.slice(5) + '月</text>';
    });
    const rp = F.rows.map((r, i) => X(i).toFixed(1) + ',' + Yr(r.revenue).toFixed(1)).join(' ');
    g += '<polyline points="' + rp + '" fill="none" stroke="#2E7D32" stroke-width="1.5" stroke-dasharray="4 3"/>';
    g += '</svg>';
    $('fusionChart').innerHTML = g + '<div class="note">图例：<span style="color:#A6192E">▮</span> 出库量(台)　<span style="color:#2E7D32">●╌</span> 产值(元)</div>';
  }

  if ($('fusionTable') && F.rows) {
    $('fusionTable').innerHTML = '<table><thead><tr><th>月份</th><th>订单量(单)</th><th>出库量(台)</th><th>工时(h)</th><th>人员数(人)</th><th>人工成本(元)</th><th>产值(元)</th><th>综合人效(台/人)</th><th>损耗率(%)</th></tr></thead><tbody>' +
      F.rows.map(r => '<tr><td><b>' + r.month + '</b></td><td>' + r.orders + '</td><td>' + r.qty + '</td><td>' + r.hours + '</td><td>' + r.headcount + '</td><td>' + r.cost.toLocaleString() + '</td><td>' + r.revenue.toLocaleString() + '</td><td><b>' + r.eff + '</b></td><td>' + (r.loss != null ? r.loss : '—') + '</td></tr>').join('') +
      '</tbody></table>';
  }
  $('wcBody').innerHTML = d.workcenters.map(w =>
    '<tr><td>' + esc(w.workcenter_id) + '</td><td>' + esc(w.workcenter_name) + '</td><td>' + (w.active_orders || 0) + '</td>' +
    '<td><span class="st ' + (d.productivity_status === '接入中' ? 'wait' : 'done') + '">' + esc(d.productivity_status) + '</span></td></tr>').join('');


  renderBrief(d.brief_history);

  /* ---- 近30天经营简报渲染(卡片+双图+明细表, 与 18790 实时版同款) ---- */
  function briefAmt(v) { return '¥' + Number(v).toLocaleString(undefined, {maximumFractionDigits: 0}); }
  function briefChartSVG(rows, amountMode) {
    const W = 760, H = 190, padL = 40, padR = 8, padT = 12, padB = 24;
    const n = rows.length, slot = (W - padL - padR) / n;
    const vals = rows.map(r => amountMode ? r.reimb_amount : r.completed);
    const ev = amountMode ? null : rows.map(r => r.new_exceptions);
    const mx = amountMode ? Math.max.apply(null, vals.concat([1]))
                          : Math.max.apply(null, vals.concat(ev || [], [1]));
    const y = v => padT + (1 - v / mx) * (H - padT - padB);
    let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block">';
    for (let i = 0; i <= 4; i++) {
      const v = mx * i / 4, yy = y(v).toFixed(1);
      svg += '<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + yy + '" y2="' + yy + '" stroke="#EEE"/>' +
             '<text x="' + (padL - 6) + '" y="' + (+yy + 4) + '" text-anchor="end" font-size="10" fill="#9AA0A6">' +
             (amountMode ? (v >= 10000 ? (v / 10000).toFixed(1) + '万' : Math.round(v)) : Math.round(v)) + '</text>';
    }
    const bw = Math.min(16, slot * 0.55);
    rows.forEach((r, i) => {
      const v = vals[i];
      if (v <= 0) return;
      const x = (padL + i * slot + (slot - bw) / 2).toFixed(1);
      svg += '<rect x="' + x + '" y="' + y(v).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' +
             (H - padB - y(v)).toFixed(1) + '" rx="1.5" fill="' + (amountMode ? '#2E7D32' : '#A6192E') +
             '" opacity="' + (r.holiday ? 0.3 : 0.85) + '"><title>' + r.date + ' ' + r.weekday + '：' +
             (amountMode ? '报销 ¥' + r.reimb_amount.toLocaleString() : '签收完成 ' + r.completed + ' 单 / 新增工单 ' + r.new_exceptions + ' 单') +
             '</title></rect>';
    });
    if (ev) {
      const pts = ev.map((v, i) => (padL + i * slot + slot / 2).toFixed(1) + ',' + y(v).toFixed(1));
      svg += '<polyline fill="none" stroke="#D48806" stroke-width="2" points="' + pts.join(' ') + '"/>';
    }
    rows.forEach((r, i) => {
      if (i % 5 === 0 || i === n - 1)
        svg += '<text x="' + (padL + i * slot + slot / 2).toFixed(1) + '" y="' + (H - 7) +
               '" text-anchor="middle" font-size="10" fill="#9AA0A6">' + r.date.slice(5) + '</text>';
    });
    svg += '</svg>';
    const lg = amountMode
      ? '<span class="lgk" style="background:#2E7D32"></span>当日报销金额(元) · 透明=法定假日'
      : '<span class="lgk" style="background:#A6192E"></span>签收完成(单)　<span class="lgk" style="background:#D48806;height:3px;border-radius:1px"></span>新增异常工单(单)';
    return svg + '<div class="note" style="margin-top:2px">' + lg + '</div>';
  }

  function renderBrief(h) {
    const rows = h.rows, last = rows[rows.length - 1], t = h.totals;
    const amt = briefAmt;
    $('briefCards').innerHTML =
      kv('当日签收完成', last.completed + ' 单', '完成=全部批次签收 · ' + last.date + ' ' + last.weekday) +
      kv('当日售后工单', last.new_exceptions + ' 单', '新增售后申请 · 日末未关闭 ' + last.open_eod + ' 单') +
      kv('当日报销', last.reimb_count + ' 笔 / ' + amt(last.reimb_amount), 'OA 报销') +
      kv('近30天累计', t.completed + ' 单交付', '新增工单 ' + t.new_exceptions + ' 单 · 报销 ' +
        t.reimb_count + ' 笔 / ' + amt(t.reimb_amount));
    $('briefNote').textContent = '报告日 ' + h.report_date + '（快照前一日）· ' + h.rule +
      '；近 9 个月归档见 output/daily_brief_*.md，实时版在数据中枢服务（18790）。';
    $('briefChart1').innerHTML = briefChartSVG(rows, false);
    $('briefChart2').innerHTML = briefChartSVG(rows, true);
    const mxComp = Math.max.apply(null, rows.map(r => r.completed).concat([1]));
    const byDate = {}; rows.forEach(r => byDate[r.date] = r);
    window._briefByDate = byDate;
    const tb = rows.slice().reverse();
    $('briefTable').innerHTML =
      '<thead><tr><th>日期</th><th>签收完成</th><th>新增工单</th><th>日末未关闭</th><th>报销笔数</th><th>报销金额</th></tr></thead><tbody>' +
      tb.map(r => {
        const wk = r.weekday === '周六' || r.weekday === '周日';
        return '<tr class="b-row" data-date="' + r.date + '">' +
          '<td><b>' + r.date + '</b> <span class="' + (wk ? 'wkend' : '') + '">' + r.weekday + '</span>' +
          (r.holiday ? '<span class="hol">假日</span>' : '') + '</td>' +
          '<td><span class="mini" style="width:' + Math.max(2, r.completed / mxComp * 46).toFixed(0) + 'px"></span>' + r.completed + ' 单</td>' +
          '<td>' + r.new_exceptions + ' 单</td><td>' + r.open_eod + ' 单</td>' +
          '<td>' + r.reimb_count + ' 笔</td><td>' + amt(r.reimb_amount) + '</td></tr>';
      }).join('') + '</tbody>';
    window._briefDate = h.report_date;
    renderBriefToday(h.today);
  }

  function plRow(name, sub, amount) {
    return '<div class="pl-row"><div class="pl-name" title="' + esc(name) + '">' + esc(name) +
      '</div><div style="white-space:nowrap"><span class="pl-meta">' + sub + '</span>' +
      (amount ? ' <span class="pl-amt">' + briefAmt(amount) + '</span>' : '') + '</div></div>';
  }

  function renderBriefToday(t) {
    if (!t) return;
    const dc = t.delivered_customers || [], nc = t.new_order_customers || [], dv = t.deliveries || [];
    $('briefCustTag').textContent = t.date + '（报告日）';
    $('briefCustBox').innerHTML =
      '<div class="sc-row"><span class="sc">交付客户 <b>' + dc.length + '</b> 家</span>' +
      '<span class="sc">新增订单客户 <b>' + nc.length + '</b> 家</span></div>' +
      '<div class="pl-sec">交付客户（按金额排序）</div>' +
      (dc.length ? dc.slice(0, 8).map(c => plRow(c.name, c.orders + ' 单', c.amount)).join('')
                 : '<div class="empty-mini">当日无交付客户</div>') +
      '<div class="pl-sec">新增订单客户</div>' +
      (nc.length ? nc.map(c => plRow(c.name, c.orders + ' 单', c.amount)).join('')
                 : '<div class="empty-mini">当日无新增订单</div>');
    $('briefDlvBox').innerHTML =
      '<div class="sc-row"><span class="sc">全量交付 <b>' + dv.length + '</b> 单</span>' +
      '<span class="sc">今日发货 <b>' + t.dispatched_today + '</b> 批</span>' +
      '<span class="sc">在途 <b>' + t.in_transit_total + '</b> 批</span></div>' +
      '<div class="sc-row"><span class="sc">未全量交付 <b>' + t.unfinished + '</b> 单（逾期 <b>' + t.overdue + '</b>）</span></div>' +
      '<div class="pl-sec">当日全量交付订单</div>' +
      (dv.length ? dv.slice(0, 12).map(d => plRow(d.order_id + ' · ' + d.customer, d.qty + ' ' + (d.unit || '台'), d.amount)).join('') +
        (dv.length > 12 ? '<div class="empty-mini">…等 ' + dv.length + ' 单</div>' : '')
                 : '<div class="empty-mini">当日无全量交付订单</div>');
  }

  /* ---- 一键生成本日简报: 优先实时调用 18790(跨域 CORS 已开), 失败回退页面内预计算全文 ---- */
  async function genBrief(date) {
    const btn = $('genBriefBtn');
    btn.disabled = true; btn.textContent = '⏳ 生成中…';
    try {
      const ctl = new AbortController();
      const t = setTimeout(() => ctl.abort(), 5000);
      const r = await fetch('http://127.0.0.1:18790/api/daily-brief/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date }), signal: ctl.signal
      });
      clearTimeout(t);
      showBriefModal(await r.json());
    } catch (e) {
      showBriefModal({ ok: true, fallback: '控制台环境未能连接数据中枢服务(18790)，以下为页面生成时预计算的本日简报；推送与台账请在数据中枢页操作。',
                      brief: d.brief_today_text, report_date: d.brief_history.report_date });
    }
    btn.disabled = false; btn.textContent = '⚡ 一键生成本日简报';
  }

  function showBriefModal(j) {
    const ledger = j.ledger_pushes && j.ledger_pushes.length ? j.ledger_pushes[j.ledger_pushes.length - 1] : null;
    const pushed = (j.push && j.push.status) || (ledger && ledger.push_status);
    let status;
    if (j.fallback) status = '📴 ' + esc(j.fallback);
    else if (!j.ok) status = '❌ 生成失败';
    else if (j.skipped) status = 'ℹ️ 当日简报已生成过（幂等跳过，未重复推送）';
    else status = '✅ 已生成' + (pushed ? '，推送状态：' + esc(pushed) : '');
    $('bmTitle').textContent = '本日经营简报' + (j.report_date ? ' · ' + j.report_date : '');
    $('bmMeta').innerHTML = status +
      ((j.saved_to || j.md_path) ? '　·　存档：<code>' + esc(j.saved_to || j.md_path) + '</code>' : '') +
      (j.idempotency_key ? '　·　幂等键：<code>' + esc(j.idempotency_key) + '</code>' : '') +
      (j.error ? '　·　错误：<code>' + esc(j.error) + '</code>' : '');
    $('bmText').textContent = j.brief || '';
    $('briefModal').classList.add('on');
  }

  $('genBriefBtn').addEventListener('click', () => genBrief(window._briefDate));
  $('bmClose').addEventListener('click', () => $('briefModal').classList.remove('on'));
  $('briefModal').addEventListener('click', e => { if (e.target === $('briefModal')) $('briefModal').classList.remove('on'); });

  $('briefTable').addEventListener('click', e => {
    const tr = e.target.closest('tr.b-row');
    if (!tr) return;
    const open = tr.nextElementSibling;
    if (open && open.classList.contains('b-detail')) { open.remove(); return; }
    const r = window._briefByDate && window._briefByDate[tr.dataset.date];
    if (!r) return;
    const orders = r.completed_orders.length
      ? r.completed_orders.slice(0, 12).join('、') + (r.completed_orders.length > 12 ? ' …等 ' + r.completed_orders.length + ' 单' : '')
      : '当日无全量交付订单';
    const dtr = document.createElement('tr');
    dtr.className = 'b-detail';
    dtr.innerHTML = '<td colspan="6"><b>当日完成订单：</b>' + esc(orders) +
      '　|　日末未关闭异常工单 ' + r.open_eod + ' 单　|　报销 ' + r.reimb_count + ' 笔 ' + briefAmt(r.reimb_amount) + '</td>';
    tr.after(dtr);
  });

  window.showDS = function (key) {
    const ds = (DATA.datasources || []).find(x => x.key === key);
    const mask = $('dsModal'), body = $('dsBody');
    if (!ds) { mask.classList.add('on'); body.innerHTML = '<div class="empty">未找到数据源：' + esc(key) + '</div>'; return; }
    let chart = '';
    if (ds.monthly && ds.monthly.length) {
      const W = 880, H = 170, pl = 40, pr = 8, pt = 10, pb = 22;
      const mx = Math.max.apply(null, ds.monthly.map(m => m.n));
      const bw = Math.min(30, (W - pl - pr) / ds.monthly.length * 0.6);
      let g = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block">';
      g += '<text x="' + pl + '" y="9" font-size="11" fill="#646A73">逐月记录量(条) · 时间列 ' + esc(ds.date_col) + '</text>';
      ds.monthly.forEach((m, i) => {
        const x = pl + (i + 0.5) * (W - pl - pr) / ds.monthly.length - bw / 2;
        const y = pt + (1 - m.n / mx) * (H - pt - pb);
        g += '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + (H - pb - y).toFixed(1) + '" rx="2" fill="#A6192E" opacity="0.85"><title>' + m.m + '：' + m.n + ' 条</title></rect>' +
             '<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (y - 3).toFixed(1) + '" text-anchor="middle" font-size="9" fill="#A6192E">' + m.n + '</text>' +
             '<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle" font-size="9" fill="#9AA0A6">' + m.m.slice(2) + '</text>';
      });
      chart = g + '</svg>';
    }
    body.innerHTML =
      '<div class="note" style="margin:0 0 8px">表 <b>' + esc(ds.key) + '</b> · ' + esc(ds.label) +
      ' · 共 <b>' + ds.rows.toLocaleString() + '</b> 行 / ' + ds.fields + ' 字段' +
      (ds.latest ? ' · 最新记录 ' + esc(ds.latest) : '') + '</div>' +
      (chart || '<div class="empty">该表无时间列, 不展示趋势</div>') +
      '<div style="font-weight:600;font-size:12.5px;margin:10px 0 4px">数据预览(前 ' + ds.preview.length + ' 行 × 前 ' + ds.preview_cols.length + ' 列)</div>' +
      '<div class="scroll" style="max-height:38vh"><table><thead><tr>' +
      ds.preview_cols.map(c => '<th>' + esc(c) + '</th>').join('') + '</tr></thead><tbody>' +
      ds.preview.map(r => '<tr>' + ds.preview_cols.map(c => '<td>' + esc(r[c]) + '</td>').join('') + '</tr>').join('') +
      '</tbody></table></div>';
    $('dsTitle').textContent = '数据源可视化 · ' + ds.label;
    mask.classList.add('on');
  };

  renderProdTrend();

  /* ---- 趋势预测智能体: 移动平均 + 线性回归 图表渲染 ---- */
  function tLine(P, cfgs, W0, H0) {
    const W = W0 || 860, H = H0 || 210, pl = 52, pr = 14, pt = 26, pb = 26;
    const unit = P.unit || '';
    const all = [];
    cfgs.forEach(c => P[c.key].forEach(v => { if (v != null) all.push(v); }));
    let mx = Math.max.apply(null, all.concat([1])), mn = Math.min.apply(null, all.concat([0]));
    if (cfgs.some(c => c.bars)) mn = 0;
    const X = i => pl + i * (W - pl - pr) / Math.max(P.x.length - 1, 1);
    const Y = v => pt + (1 - (v - mn) / ((mx - mn) || 1)) * (H - pt - pb);
    let g = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block">';
    g += '<text x="' + pl + '" y="13" font-size="11" fill="#646A73">Y轴单位: ' + esc(unit) + '</text>' +
         '<text x="' + (W - pr) + '" y="13" font-size="11" fill="#646A73" text-anchor="end">X轴: 月份(2026年)</text>';
    for (let k = 0; k <= 4; k++) {
      const v = mn + (mx - mn) * k / 4, yy = Y(v).toFixed(1);
      g += '<line x1="' + pl + '" x2="' + (W - pr) + '" y1="' + yy + '" y2="' + yy + '" stroke="#EEE"/>' +
           '<text x="' + (pl - 6) + '" y="' + (+yy + 4) + '" text-anchor="end" font-size="10" fill="#9AA0A6">' + (Math.round(v * 10) / 10) + '</text>';
    }
    const bw = Math.min(22, (W - pl - pr) / P.x.length * 0.32);
    cfgs.forEach(c => {
      if (c.bars) {
        P[c.key].forEach((v, i) => {
          if (v == null) return;
          const x = (X(i) - bw / 2 - (c.off || 0)).toFixed(1);
          g += '<rect x="' + x + '" y="' + Y(v).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + (H - pb - Y(v)).toFixed(1) + '" rx="1.5" fill="' + c.color + '" opacity="0.8"><title>' + P.x[i] + '：' + v + '</title></rect>';
        });
      } else {
        const pts = P[c.key].map((v, i) => v == null ? null : X(i).toFixed(1) + ',' + Y(v).toFixed(1)).filter(Boolean);
        if (pts.length) g += '<polyline fill="none" stroke="' + c.color + '" stroke-width="' + (c.w || 2) + '"' + (c.dash ? ' stroke-dasharray="5 4"' : '') + ' points="' + pts.join(' ') + '"/>';
        if (c.dots !== false) {
          const vs = P[c.key].filter(v => v != null);
          const mxV = Math.max.apply(null, vs), mnV = Math.min.apply(null, vs);
          P[c.key].forEach((v, i) => {
            if (v == null) return;
            g += '<circle cx="' + X(i).toFixed(1) + '" cy="' + Y(v).toFixed(1) + '" r="2.6" fill="' + c.color + '"><title>' + P.x[i] + '：' + v + unit + '</title></circle>';
            if (v === mxV || v === mnV || i === P.x.length - 1)
              g += '<text x="' + (X(i) + 4).toFixed(1) + '" y="' + (Y(v) - 5).toFixed(1) + '" font-size="9.5" fill="' + c.color + '">' + v + '</text>';
          });
        }
      }
    });
    P.x.forEach((m, i) => { g += '<text x="' + X(i).toFixed(1) + '" y="' + (H - 7) + '" text-anchor="middle" font-size="10" fill="#9AA0A6">' + m.slice(5) + '月</text>'; });
    return g + '</svg>';
  }

  function legend(items) {
    return '<div class="note" style="margin-top:2px">' + items.map(i =>
      '<span style="display:inline-block;width:14px;height:3px;background:' + i[1] + ';margin:0 4px 2px 0;vertical-align:middle' +
      (i[2] ? ';background-image:linear-gradient(90deg,' + i[1] + ' 60%,#fff 60%)' : '') + '"></span>' + i[0]).join('　') + '</div>';
  }

  function badge(v) {
    const cls = v.level === 'down' ? 'alert' : (v.level === 'up' ? 'ok' : 'gray');
    return '<span class="badge ' + cls + '">' + esc(v.text) + '</span>';
  }

  function renderProdTrend() {
    const t = d.prod;
    if (!t) return;
    const P = { x: t.months };
    ['created', 'done', 'qty', 'ontime_rate', 'cycle'].forEach(k => P[k] = t.series[k]);
    P.maQty = t.ma.qty; P.regOntime = t.reg.ontime_rate; P.regCycle = t.reg.cycle;
    const T = t.totals;
    $('prodKpis').innerHTML =
      kv('累计新增订单', T.created + ' 单', '2026 1-9月') +
      kv('累计完成交付', T.done + ' 单', T.qty + ' 台设备') +
      kv('平均准时率', (T.ontime != null ? T.ontime : '—') + '%', '签收≤承诺交期') +
      kv('平均交付周期', (T.cycle != null ? T.cycle : '—') + ' 天', '创建→签收');
    $('prodAgent').innerHTML = '<div class="name">🤖 趋势预测智能体 · 综合诊断</div><p>' + esc(t.agent) + '</p>';

    const DS_OF = { done: 'shipments', qty: 'shipments', ontime_rate: 'orders', cycle: 'orders', eff: 'labor_logs' };
  const aiBox = (k, extra) => '<div class="agentcard" style="margin:8px 0 0;padding:9px 12px"><div class="name" style="font-size:12.5px">🤖 AI 解读</div>' +
      '<p style="margin-top:4px">' + esc(t.ai_notes[k]) + (extra || '') + '<br><span style="color:#9AA0A6">数据源：' + esc(t.sources[k.split('_')[0] === 'wc' ? 'eff' : k] || '') + '</span> ' +
            '<a href="javascript:void(0)" onclick="showDS(&#39;' + (DS_OF[k.split('_')[0] === 'wc' ? 'eff' : k] || k) + '&#39;)" style="color:var(--blue,#1F6FEB);font-size:12px;margin-left:6px">📊 查看数据源</a></p></div>';
    P.unit = '单';
    $('chOrder').innerHTML = tLine(P, [
      { key: 'created', bars: true, color: '#B9C6D4', off: 6 },
      { key: 'done', bars: true, color: '#A6192E' },
      { key: 'done', color: '#A6192E', dots: false }
    ]) + legend([['新增订单(单)', '#B9C6D4'], ['完成交付(单)', '#A6192E']]) +
      '<div style="margin-top:6px">' + badge(t.verdicts.done) + '</div>' + aiBox('done');

    P.unit = '台';
    $('chQty').innerHTML = tLine(P, [
      { key: 'qty', color: '#2E7D32' },
      { key: 'maQty', color: '#F59E0B', dash: true, dots: false }
    ]) + legend([['月度产量(台)', '#2E7D32'], ['3月移动平均(台)', '#F59E0B', true]]) + aiBox('qty');

    P.unit = '%';
    $('chOntime').innerHTML = tLine(P, [
      { key: 'ontime_rate', color: '#1677FF' },
      { key: 'regOntime', color: '#9AA0A6', dash: true, dots: false }
    ]) + legend([['准时率(%)', '#1677FF'], ['线性回归趋势', '#9AA0A6', true]]) +
      '<div style="margin-top:6px">' + badge(t.verdicts.ontime_rate) + '</div>' + aiBox('ontime_rate');

    P.unit = '天';
    $('chCycle').innerHTML = tLine(P, [
      { key: 'cycle', color: '#8E44AD' },
      { key: 'regCycle', color: '#9AA0A6', dash: true, dots: false }
    ]) + legend([['平均交付周期(天)', '#8E44AD'], ['线性回归趋势', '#9AA0A6', true]]) +
      '<div style="margin-top:6px">' + badge(t.verdicts.cycle) + '</div>' + aiBox('cycle');


    const wcNames = {};
    (d.workcenters || []).forEach(w => wcNames[w.workcenter_id] = w.workcenter_name);
    $('wcEffBox').innerHTML = Object.keys(t.wc_eff).map(wc => {
      const e = t.wc_eff[wc], PP = { x: t.months, v: e.values, m: e.ma3, r: e.reg, unit: '人效比(标准工时/实际人时)' };
      return '<div style="margin:12px 0;padding:12px;border:1px solid var(--line);border-radius:8px">' +
        '<b style="font-size:13.5px">' + wc + ' · ' + esc(wcNames[wc] || '生产小组') + ' — 人效趋势</b>' +
        '<span class="note" style="margin-left:10px">小组编码 ' + wc + '</span>' +
        '<div class="grid2" style="grid-template-columns:minmax(0,1fr) 320px;gap:10px;align-items:start;margin-top:8px">' +
        '<div>' + tLine(PP, [
          { key: 'v', color: '#A6192E' },
          { key: 'm', color: '#F59E0B', dash: true, dots: false },
          { key: 'r', color: '#9AA0A6', dash: true, dots: false, w: 1.5 }
        ], 620, 190) + legend([['月人效(比值)', '#A6192E'], ['3月移动平均', '#F59E0B', true], ['线性回归趋势', '#9AA0A6', true]]) + '</div>' +
        '<div><div style="margin:6px 0">' + badge(e.verdict) + '</div>' +
        '<div class="note" style="margin:0">近3月均值 ' + (e.ma3[e.ma3.length - 1] != null ? e.ma3[e.ma3.length - 1].toFixed(4) : '—') +
        ' · 回归斜率 ' + e.verdict.slope + '/月</div>' +
        '<div class="agentcard" style="margin-top:8px;padding:9px 12px"><div class="name" style="font-size:12.5px">🤖 AI 解读</div>' +
        '<p style="margin-top:4px">' + esc(t.ai_notes['wc_' + wc] || '') + '<br><span style="color:#9AA0A6">数据源：' + esc(t.sources.eff) + '</span> ' +
                '<a href="javascript:void(0)" onclick="showDS(&#39;labor_logs&#39;)" style="color:var(--blue,#1F6FEB);font-size:12px;margin-left:6px">📊 查看数据源</a></p></div></div></div></div>';
    }).join('') || '<div class="empty">暂无工时数据</div>';

    const sm = t.stage_m, SN = { PLAN: '计划', PROCESS: '加工', QC: '质检', SHIP: '发货', SIGN: '签收' };
    $('prodTable').innerHTML = '<table><thead><tr><th>月份</th><th>新增</th><th>完成</th><th>产量(台)</th><th>准时率</th><th>周期(天)</th>' +
      Object.keys(SN).map(k => '<th>' + SN[k] + '完成</th>').join('') + '</tr></thead><tbody>' +
      t.months.map(m => {
        const i = t.months.indexOf(m);
        const ot = t.series.ontime_rate[i];
        return '<tr><td><b>' + m + '</b></td><td>' + t.series.created[i] + '</td><td>' + t.series.done[i] + '</td><td>' + t.series.qty[i] + '</td>' +
          '<td>' + (ot != null ? ot + '%' : '—') + '</td><td>' + (t.series.cycle[i] != null ? t.series.cycle[i] : '—') + '</td>' +
          Object.keys(SN).map(k => '<td>' + ((sm[k] || {})[m] || 0) + '</td>').join('') + '</tr>';
      }).join('') + '</tbody></table>';
  }
}

/* ---- 智能问数（跨端口调用数据中枢 API） ---- */
const API_BASE = (location.port === '8000') ? ('http://' + location.hostname + ':18790') : '';
async function askAI(q) {
  if (q) $('askQ').value = q;
  const question = $('askQ').value.trim();
  if (!question) { $('askQ').focus(); return; }
  $('askBtn').disabled = true;
  $('askMeta').textContent = '⏳ AI 正在生成 SQL 并查询…（通常 20–40 秒，请稍候）';
  $('askOut').innerHTML = '<div class="empty">⏳ AI 思考中…</div>';
  $('askSql').innerHTML = ''; $('askErr').innerHTML = '';
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 150000);
    const r = await fetch(API_BASE + '/api/ask', {method:'POST', signal: ctl.signal,
      headers:{'Content-Type':'application/json'}, body: JSON.stringify({question})});
    clearTimeout(t);
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || ('HTTP ' + r.status));
    $('askMeta').textContent = '✅ 返回 ' + d.row_count + ' 行 · 耗时 ' + (d.elapsed_ms/1000).toFixed(1) + ' 秒' +
      (d.attempts > 1 ? ' · 首次报错已自动纠正' : '');
    $('askSql').innerHTML = '<details><summary>查看 AI 生成的 SQL（只读）</summary><pre>' + esc(d.sql) + '</pre></details>';
    const cols = d.columns || [];
    $('askOut').innerHTML = d.rows.length
      ? '<div class="scroll"><table><thead><tr>' + cols.map(c => '<th>' + esc(c) + '</th>').join('') + '</tr></thead><tbody>' +
        d.rows.map(r2 => '<tr>' + cols.map(c => '<td>' + esc(r2[c] === null ? '' : r2[c]) + '</td>').join('') + '</tr>').join('') +
        '</tbody></table></div>'
      : '<div class="empty">查询成功，无匹配数据</div>';
  } catch (e) {
    $('askMeta').textContent = '';
    $('askOut').innerHTML = '';
    $('askErr').innerHTML = '<div class="err">问数失败：' + esc(e && e.message || e) +
      (String(e && e.message).indexOf('abort') >= 0 || String(e).indexOf('Failed to fetch') >= 0
        ? '（需数据中枢服务在线：服务器 18790 端口）' : '') + '</div>';
  }
  $('askBtn').disabled = false;
}
$('askBtn').addEventListener('click', () => askAI());
$('askQ').addEventListener('keydown', e => { if (e.key === 'Enter') askAI(); });
document.querySelectorAll('#askChips .chip').forEach(c => c.addEventListener('click', () => askAI(c.textContent)));

/* ---- 本地订单节点查询 ---- */
let CURSOR = 0; const PAGE = 200; let LAST = null;
function filteredRows() {
  const f = {so: $('fOrder').value.trim().toUpperCase(), stage: $('fStage').value,
             st: $('fStatus').value, dl: $('fDl').value};
  LAST = f;
  return DATA.orders.filter(r =>
    (!f.so || r.sales_order_id.toUpperCase().indexOf(f.so) >= 0 ||
      (r.contract_name || '').toUpperCase().indexOf(f.so) >= 0 ||
      (r.unique_id || '').toUpperCase().indexOf(f.so) >= 0 ||
      (r.contract_no || '').toUpperCase().indexOf(f.so) >= 0) &&
    (!f.stage || r.stage_code === f.stage) &&
    (!f.st || r.stage_status === f.st) &&
    (!f.dl || r.deadline_state === f.dl));
}
function runQuery(append) {
  if (!append) CURSOR = 0;
  const all = filteredRows().sort((a, b) => (b.overdue_days || 0) - (a.overdue_days || 0));
  const rows = all.slice(CURSOR, CURSOR + PAGE);
  const cols = ['contract_name','overdue_days','sales_order_id','contract_no','unique_id','customer_name','stage_name','stage_status',
                'planned_start_at','planned_end_at','actual_start_at','actual_end_at','deadline_state','source_status'];
  const HEAD = {contract_name:'合同名称(ERP)', overdue_days:'超时(天)', sales_order_id:'订单编号(生产编号)', contract_no:'合同编号(ERP)',
                unique_id:'数据唯一编号', customer_name:'客户', stage_name:'节点', stage_status:'节点状态',
                planned_start_at:'计划开始', planned_end_at:'计划结束',
                actual_start_at:'实际开始', actual_end_at:'实际结束', deadline_state:'时限', source_status:'当天状态原文'};
  const dlClass = v => v === '超时' ? 'alert' : (v === '即将到期' ? 'amber' : (v === '已完成' ? 'ok' : 'gray'));
  const rowsHtml = rows.map(r => {
    const od = r.overdue_days || 0;
    const rowBg = od > 0 ? ' style="background:#FFF2F0"' : '';
    return '<tr' + rowBg + '>' + cols.map(c => {
      const v = r[c];
      if (c === 'overdue_days') {
        if (od > 0) return '<td><span style="color:#C7000B;font-weight:700;font-size:14px">⚠ ' + od + '</span></td>';
        if (r.stage_status === '已完成') return '<td style="color:#52C41A">✓ 0</td>';
        return '<td style="color:#9AA0A6">0</td>';
      }
      if (c === 'deadline_state') return '<td><span class="badge ' + dlClass(v) + '">' + esc(v) + '</span></td>';
      if (c === 'contract_name' && od > 0) return '<td style="color:#C7000B;font-weight:600">' + esc(v === null ? '' : v) + '</td>';
      return '<td>' + esc(v === null ? '' : v) + '</td>';
    }).join('') + '</tr>';
  }).join('');
  if (append) {
    const tb = $('qOut').querySelector('tbody');
    if (tb) tb.insertAdjacentHTML('beforeend', rowsHtml);
  } else {
    $('qOut').innerHTML = rows.length
      ? '<table><thead><tr>' + cols.map(c => '<th>' + (HEAD[c] || c) + '</th>').join('') + '</tr></thead><tbody>' + rowsHtml + '</tbody></table>'
      : '<div class="empty">无匹配数据（可调整筛选条件）</div>';
  }
  const odTotal = all.filter(r => (r.overdue_days || 0) > 0).length;
  const odMax = all.reduce((a, r) => Math.max(a, r.overdue_days || 0), 0);
  $('qMeta').innerHTML = '匹配 ' + all.length + ' 条(本页 ' + rows.length + ') · <b style="color:#C7000B">⚠ 超时 ' + odTotal + ' 条</b>(最长 ' + odMax + ' 天)' +
    ' · 快照 ' + fmtDT(DATA.snapshot_at) + ' · 超时 = 计划结束日 < 快照日且未完成';
  const hasMore = CURSOR + PAGE < all.length;
  $('moreBtn').style.display = hasMore ? '' : 'none';
  if (hasMore) { $('moreBtn').textContent = '加载更多（已载 ' + (CURSOR + rows.length) + '/' + all.length + '）'; CURSOR += PAGE; }
}
function drillStage(stageCode, dl) {
  goto('query');
  $('fStage').value = stageCode;
  $('fDl').value = dl || '';
  runQuery(false);
}

/* ---- 风险下钻（本地） ---- */
function riskDrill(bucket) {
  const box = $('riskDrill');
  const rows = DATA.drill[bucket].slice(0, 100);
  box.innerHTML = '<div class="meta">风险明细（最多 100 条）：</div>' +
    '<div class="scroll"><table><thead><tr><th>订单号</th><th>承诺交期</th><th>状态</th></tr></thead><tbody>' +
    rows.map(x => '<tr><td>' + esc(x.so) + '</td><td>' + esc(x.due || '—') + '</td><td>' + esc(x.kind) + '</td></tr>').join('') +
    '</tbody></table></div>' + (rows.length === 0 ? '<div class="empty">该风险档暂无订单</div>' : '');
}
document.querySelectorAll('#riskCards .risk-card').forEach(c => c.addEventListener('click', () => riskDrill(c.dataset.bucket)));

/* ---- CSV ---- */
function exportCSV() {
  const all = filteredRows();
  const cols = ['sales_order_id','work_order_id','stage_code','stage_name','stage_status',
                'planned_start_at','planned_end_at','actual_start_at','actual_end_at','deadline_state','source_status'];
  const q = v => '"' + String(v === null || v === undefined ? '' : v).replace(/"/g, '""') + '"';
  const csv = '\\ufeff' + cols.map(c => HEAD[c] || c).join(',') + '\\n' + all.map(r => cols.map(c => q(r[c])).join(',')).join('\\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
  a.download = 'order_progress.csv';
  a.click();
}
$('queryBtn').addEventListener('click', () => runQuery(false));
$('resetBtn').addEventListener('click', () => {
  $('fOrder').value = ''; $('fStage').value = '';
  $('fStatus').value = ''; $('fDl').value = '';
  runQuery(false);
});
$('moreBtn').addEventListener('click', () => runQuery(true));
$('csvBtn').addEventListener('click', exportCSV);
$('fOrder').addEventListener('keydown', e => { if (e.key === 'Enter') runQuery(false); });

renderAll();
runQuery(false);
</script>
</body>
</html>
"""

page = page.replace("__DATA__", DATA_JS)
page = page.replace("\\\\'", "'")   # stageRowHTML 内联 onclick 转义还原
import os as _os, tempfile as _tf
page = page.replace("__ORDER_SOURCES__", src_parts)
_tmp = OUT + ".tmp"
with open(_tmp, "w", encoding="utf-8") as f:
    f.write(page)
_os.replace(_tmp, OUT)  # 原子替换, 避免并发读取到半写文件导致白屏
print("written", OUT, len(page), "bytes",
      "| orders", len(orders), "| drill", {k: len(v) for k, v in risk.items()})
