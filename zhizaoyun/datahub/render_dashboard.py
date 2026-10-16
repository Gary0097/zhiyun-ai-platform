#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金汉隆 AI 数据中枢 · 轻量看板生成器
从 agent_data.sqlite 计算并生成自包含 index.html（内联 SVG 图表，无外部依赖）。
用法: python3 render_dashboard.py [--db PATH] [--out DIR]
默认输出到脚本所在目录的 dashboard/ 子目录（datahub_api.py 的静态托管目录）。
"""
import argparse
import html
import os
import sqlite3
import sys
from datetime import datetime, timedelta

C_RED = "#C7000B"
C_GREEN = "#2E8B57"
C_AMBER = "#D48806"
C_GRAY = "#8C8C8C"
C_BLUE = "#1F6FEB"
C_INK = "#1F2329"
C_SUB = "#646A73"
C_BG = "#F5F6F7"


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


def load(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    q = lambda s, *args: con.execute(s, args).fetchall()
    d = {}
    d["snapshot"] = q("SELECT config_value FROM configuration WHERE config_key='snapshot_at'")[0][0]
    d["effective"] = q("SELECT COUNT(*) FROM v_current_orders")[0][0]

    base = """
WITH s AS (
  SELECT sales_order_id, COUNT(*) AS batches,
         SUM(CASE WHEN status='已签收' AND received_at IS NOT NULL AND received_at<>'' THEN 1 ELSE 0 END) AS signed,
         SUM(CASE WHEN status<>'已签收' THEN 1 ELSE 0 END) AS intransit
  FROM shipments GROUP BY sales_order_id)
"""
    d["completed"] = q(base + """
SELECT COUNT(*) FROM v_current_orders o JOIN s ON s.sales_order_id=o.sales_order_id
WHERE s.signed = s.batches""")[0][0]
    d["intransit"] = q(base + """
SELECT COUNT(*) FROM v_current_orders o JOIN s ON s.sales_order_id=o.sales_order_id
WHERE s.intransit > 0 AND s.signed < s.batches""")[0][0]
    d["noship"] = q(base + """
SELECT COUNT(*) FROM v_current_orders o LEFT JOIN s ON s.sales_order_id=o.sales_order_id
WHERE s.sales_order_id IS NULL""")[0][0]
    d["unfinished"] = d["effective"] - d["completed"]

    snap = d["snapshot"]
    # 交期风险分层规则：红=已逾期或7天内到期；黄=8-30天；绿=其余
    rows = q(base + f"""
SELECT o.sales_order_id, o.promised_delivery_at,
       CASE WHEN s.sales_order_id IS NULL THEN '未发货' ELSE '在途' END AS kind
FROM v_current_orders o LEFT JOIN s ON s.sales_order_id=o.sales_order_id
WHERE (s.signed IS NULL OR s.signed < s.batches)
ORDER BY o.promised_delivery_at""")
    def bucket(p):
        due = datetime.fromisoformat(p)
        reference = datetime.fromisoformat(snap)
        if due <= reference + timedelta(days=7):
            return "red"
        if due <= reference + timedelta(days=30):
            return "yellow"
        return "green"

    risk = {"red": 0, "yellow": 0, "green": 0}
    for _, p, _k in rows:
        risk[bucket(p)] += 1
    d["risk"] = risk
    d["overdue"] = sum(1 for _, p, _ in rows if p < snap)
    d["risk_rows"] = rows[:200]

    # 合同第1条：订单节点汇总；使用现有节点事实表，不改变原始数据。
    d["stage_summary"] = q("""
SELECT stage_code, MAX(stage_name) AS stage_name,
       SUM(CASE WHEN stage_status='已完成' THEN 1 ELSE 0 END) AS completed,
       SUM(CASE WHEN stage_status='进行中' THEN 1 ELSE 0 END) AS running,
       SUM(CASE WHEN stage_status='未开始' THEN 1 ELSE 0 END) AS pending,
       SUM(CASE WHEN stage_status<>'已完成'
                     AND julianday(planned_end_at) < julianday(?)
                THEN 1 ELSE 0 END) AS overdue
FROM stage_nodes GROUP BY stage_code ORDER BY MIN(sequence)
""", snap)

    # 合同第3条：采集状态；领导页面只展示业务状态和记录数量。
    d["ingestion"] = q("""
SELECT source_system, run_at, input_record_count, loaded_record_count,
       quarantined_record_count, run_status
FROM ingestion_runs ORDER BY run_at DESC
""")

    # 合同第4条：工作中心人效、产值与质量损耗基础指标。
    d["fusion"] = q("""
SELECT workcenter_id,
       ROUND(SUM(earned_standard_hours), 2) AS standard_hours,
       ROUND(SUM(actual_hours), 2) AS actual_hours,
       ROUND(SUM(earned_standard_hours) / NULLIF(SUM(actual_hours), 0), 4) AS productivity,
       ROUND(SUM(earned_standard_hours * standard_value_rate), 2) AS work_value,
       ROUND(COALESCE((SELECT SUM(q.defective_quantity) FROM quality_inspections q
                       WHERE q.work_order_id IN
                             (SELECT DISTINCT l2.work_order_id FROM labor_logs l2
                              WHERE l2.workcenter_id=l.workcenter_id)), 0), 2) AS loss_quantity
FROM labor_logs l GROUP BY workcenter_id ORDER BY workcenter_id
""")

    # 合同第5条：日报三项指标，仍然从现有事实表计算。
    snap_day = snap[:10]
    report_day = q("SELECT date(?, '-1 day')", snap_day)[0][0]
    d["brief"] = {
        "date": report_day,
        "completed": q("""
WITH s AS (SELECT sales_order_id, COUNT(*) batches, MAX(received_at) last_received_at,
 SUM(CASE WHEN status='已签收' AND received_at IS NOT NULL AND received_at<>'' THEN 1 ELSE 0 END) signed
 FROM shipments GROUP BY sales_order_id)
SELECT COUNT(*) FROM v_current_orders o JOIN s ON s.sales_order_id=o.sales_order_id
WHERE s.signed=s.batches AND s.last_received_at LIKE ? || '%'
""", report_day)[0][0],
        "exceptions": q("SELECT COUNT(DISTINCT work_order_id) FROM exceptions WHERE opened_at LIKE ? || '%'", report_day)[0][0],
        "reimbursements": q("SELECT COUNT(*), ROUND(COALESCE(SUM(amount),0),2) FROM expenses WHERE submitted_at LIKE ? || '%'", report_day)[0],
    }

    # WC02 每日人效（有作业日）
    eff_rows = q("""
SELECT work_date, ROUND(SUM(earned_standard_hours),4), ROUND(SUM(actual_hours),4)
FROM labor_logs WHERE workcenter_id='WC02' GROUP BY work_date ORDER BY work_date""")
    series = []
    for wd, se, sa in eff_rows:
        if sa:
            series.append((wd, round(se / sa, 4)))
    d["eff_all"] = series
    d["eff30"] = series[-30:]

    def mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    def slope(ys):
        n = len(ys)
        if n < 2:
            return 0.0
        mx = (n - 1) / 2.0
        my = mean(ys)
        num = sum((i - mx) * (y - my) for i, y in enumerate(ys))
        den = sum((i - mx) ** 2 for i in range(n))
        return num / den if den else 0.0

    last14 = [v for _, v in series[-14:]]
    last7 = [v for _, v in series[-7:]]
    prev7 = [v for _, v in series[-14:-7]]
    d["wc02_recent7"] = round(mean(last7), 6)
    d["wc02_prev7"] = round(mean(prev7), 6)
    d["wc02_change_pct"] = round((d["wc02_recent7"] / d["wc02_prev7"] - 1) * 100, 2) if d["wc02_prev7"] else 0.0
    d["wc02_slope14"] = round(slope(last14), 6)
    con.close()
    return d


# ---------- SVG helpers ----------

def esc(s):
    return html.escape(str(s), quote=True)


def business_source(value):
    return {"WeChat": "微信订单", "Excel": "台账文件", "脏数据测试": "异常记录"}.get(str(value), str(value))


def business_status(value):
    value = str(value)
    if "成功" in value:
        return "已完成"
    if "OCR" in value:
        return "处理中"
    if "隔离" in value or "异常" in value:
        return "需关注"
    return value


def svg_donut(segments, size=190, thick=30):
    # segments: list of (label, value, color)
    total = sum(v for _, v, _ in segments) or 1
    cx = cy = size / 2
    r = (size - thick) / 2
    circ = 2 * 3.141592653589793 * r
    out = [f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">']
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#EEE" stroke-width="{thick}"/>')
    off = 0.0
    for label, v, color in segments:
        frac = v / total
        dash = frac * circ
        out.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{thick}" '
            f'stroke-dasharray="{dash:.2f} {circ - dash:.2f}" stroke-dashoffset="{-off:.2f}" '
            f'transform="rotate(-90 {cx} {cy})"/>')
        off += dash
    out.append(f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" font-size="26" font-weight="700" fill="{C_INK}">{total}</text>')
    out.append(f'<text x="{cx}" y="{cy + 20}" text-anchor="middle" font-size="12" fill="{C_SUB}">未交付订单</text>')
    out.append("</svg>")
    return "".join(out)


def svg_line(points, width=760, height=240, pad_l=46, pad_r=16, pad_t=18, pad_b=30,
             ma=7, color=C_BLUE, ma_color=C_RED, y_fmt="{:.2f}"):
    # points: list of (label, value)
    if not points:
        return "<div>无数据</div>"
    vals = [v for _, v in points]
    vmin, vmax = min(vals), max(vals)
    span = (vmax - vmin) or 0.1
    vmin -= span * 0.08
    vmax += span * 0.08
    n = len(points)
    W, H = width, height
    inner_w, inner_h = W - pad_l - pad_r, H - pad_t - pad_b
    X = lambda i: pad_l + (inner_w * i / (n - 1) if n > 1 else inner_w / 2)
    Y = lambda v: pad_t + inner_h * (vmax - v) / (vmax - vmin)

    out = [f'<svg width="100%" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet">']
    for g in range(4):
        y = pad_t + inner_h * g / 3
        val = vmax - (vmax - vmin) * g / 3
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{W - pad_r}" y2="{y:.1f}" stroke="#EEE"/>')
        out.append(f'<text x="{pad_l - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="10" fill="{C_SUB}">{y_fmt.format(val)}</text>')
    step = max(1, n // 8)
    for i in range(0, n, step):
        out.append(f'<text x="{X(i):.1f}" y="{H - 8}" text-anchor="middle" font-size="10" fill="{C_SUB}">{esc(points[i][0][5:])}</text>')
    pl = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(points))
    out.append(f'<polyline points="{pl}" fill="none" stroke="{color}" stroke-width="2"/>')
    for i, (_, v) in enumerate(points):
        out.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="2.4" fill="{color}"><title>{esc(points[i][0])}: {v}</title></circle>')
    if ma and n >= ma:
        ma_pts = []
        win = []
        for i, (_, v) in enumerate(points):
            win.append(v)
            if len(win) > ma:
                win.pop(0)
            if len(win) == ma:
                ma_pts.append((X(i), Y(sum(win) / ma)))
        if len(ma_pts) > 1:
            pl2 = " ".join(f"{x:.1f},{y:.1f}" for x, y in ma_pts)
            out.append(f'<polyline points="{pl2}" fill="none" stroke="{ma_color}" stroke-width="2.2" stroke-dasharray="6 3"/>')
    out.append("</svg>")
    return "".join(out)


def svg_hbar(rows, width=760, bar_h=26, gap=10, color_map=None):
    # rows: list of (label, value, color)
    W = width
    n = len(rows)
    H = n * (bar_h + gap)
    total = max(v for _, v, _ in rows) or 1
    out = [f'<svg width="100%" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet">']
    for i, (label, v, color) in enumerate(rows):
        y = i * (bar_h + gap)
        bw = (W - 260) * v / total
        out.append(f'<text x="0" y="{y + bar_h * 0.7:.0f}" font-size="13" fill="{C_INK}">{esc(label)}</text>')
        out.append(f'<rect x="150" y="{y}" width="{bw:.1f}" height="{bar_h}" rx="4" fill="{color}"/>')
        out.append(f'<text x="{150 + bw + 8:.0f}" y="{y + bar_h * 0.7:.0f}" font-size="13" fill="{C_SUB}">{v}</text>')
    out.append("</svg>")
    return "".join(out)


def render(d, out_dir):
    snap = d["snapshot"].replace("T", " ").replace("+08:00", "")[:16]
    kpi = [
        ("已生效订单", f'{d["effective"]} 单', C_INK),
        ("已全量签收", f'{d["completed"]} 单', C_GREEN),
        ("未全量交付", f'{d["unfinished"]} 单', C_AMBER),
        ("其中已逾期", f'{d["overdue"]} 单', C_RED),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="kpi-label">{esc(k)}</div>'
        f'<div class="kpi-value" style="color:{c}">{esc(v)}</div></div>'
        for k, v, c in kpi)

    prog = [("已全量签收", d["completed"], C_GREEN),
            ("在途未签收", d["intransit"], C_AMBER),
            ("未发货", d["noship"], C_GRAY)]
    prog_legend = "".join(
        f'<div class="lg"><span class="dot" style="background:{c}"></span>{esc(l)} {v} 单</div>'
        for l, v, c in prog)
    donut = svg_donut(prog)

    # 风险条
    risk_bars = [("高风险（红）", d["risk"]["red"], C_RED),
                 ("中风险（黄）", d["risk"]["yellow"], C_AMBER),
                 ("低风险（绿）", d["risk"]["green"], C_GREEN)]
    risk_svg = svg_hbar(risk_bars)

    eff = d["eff30"]
    pts = [(wd, v) for wd, v in eff]
    trend_svg = svg_line(pts, ma=7, color=C_BLUE, ma_color=C_RED)

    # 小表格：未来交期最近的未交付订单
    rows_html = "".join(
        f'<tr><td>{esc(r[0])}</td><td>{esc(r[1][:10])}</td><td>{esc(r[2])}</td></tr>'
        for r in d["risk_rows"][:10])

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>金汉隆 AI数据中枢 · 经营看板</title>
<style>
  :root {{ --ink:{C_INK}; --sub:{C_SUB}; --bg:{C_BG}; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif; background:var(--bg); color:var(--ink); }}
  .top {{ background:linear-gradient(90deg,#B00A0A,#C7000B 55%,#E23A22); color:#fff; padding:20px 28px; }}
  .top h1 {{ margin:0; font-size:20px; letter-spacing:.5px; }}
  .top .sub {{ margin-top:6px; font-size:12px; opacity:.9; }}
  .wrap {{ max-width:1080px; margin:20px auto; padding:0 16px 40px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }}
  .kpi {{ background:#fff; border-radius:10px; padding:16px 18px; box-shadow:0 1px 4px rgba(0,0,0,.06); }}
  .kpi-label {{ font-size:12px; color:var(--sub); }}
  .kpi-value {{ font-size:26px; font-weight:700; margin-top:6px; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:14px; }}
  .card {{ background:#fff; border-radius:10px; padding:18px 20px; box-shadow:0 1px 4px rgba(0,0,0,.06); }}
  .card h2 {{ margin:0 0 12px; font-size:15px; }}
  .card h2 .tag {{ font-size:11px; color:var(--sub); font-weight:400; margin-left:8px; }}
  .lg {{ display:flex; align-items:center; font-size:13px; margin:6px 0; color:var(--ink); }}
  .dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; margin-right:8px; }}
  .center {{ display:flex; align-items:center; gap:18px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th,td {{ text-align:left; padding:7px 8px; border-bottom:1px solid #F0F0F0; }}
  th {{ color:var(--sub); font-weight:500; }}
  .note {{ margin-top:8px; font-size:12px; color:var(--sub); }}
  .foot {{ max-width:1080px; margin:6px auto 0; padding:0 16px; font-size:12px; color:var(--sub); }}
</style>
</head>
<body>
<div class="top">
  <h1>金汉隆 AI数据中枢 · 经营看板</h1>
  <div class="sub">数据时点 {esc(snap)}（北京时间） · 金汉隆经营数据</div>
</div>
<div class="wrap">
  <div class="kpis">{kpi_html}</div>

  <div class="grid">
    <div class="card">
      <h2>客户订单进度<span class="tag">完成=全量签收</span></h2>
      <div class="center">{donut}
        <div>{prog_legend}
          <div class="note">分批发货按运单累计，最后一批签收后才计完成。</div>
        </div>
      </div>
    </div>
    <div class="card">
      <h2>交付风险分布<span class="tag">按交期与履约状态分析</span></h2>
      {risk_svg}
      <div class="note">红：已逾期或 7 天内到期；黄：8–30 天；绿：其余（均在 89 单未交付范围内）。</div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>订单节点进度<span class="tag">计划 / 加工 / 质检 / 发货</span></h2>
      <table>
        <thead><tr><th>节点</th><th>已完成</th><th>进行中</th><th>未开始</th><th>超时</th></tr></thead>
        <tbody>{''.join(f'<tr><td>{esc(r["stage_name"])}</td><td>{r["completed"]}</td><td>{r["running"]}</td><td>{r["pending"]}</td><td style="color:{C_RED}">{r["overdue"]}</td></tr>' for r in d["stage_summary"])}</tbody>
      </table>
    </div>
    <div class="card">
      <h2>数据采集状态<span class="tag">最近同步记录</span></h2>
      <table>
        <thead><tr><th>来源</th><th>接收</th><th>已处理</th><th>异常</th><th>状态</th></tr></thead>
        <tbody>{''.join(f'<tr><td>{esc(business_source(r["source_system"]))}</td><td>{r["input_record_count"]}</td><td>{r["loaded_record_count"]}</td><td>{r["quarantined_record_count"]}</td><td>{esc(business_status(r["run_status"]))}</td></tr>' for r in d["ingestion"][:7])}</tbody>
      </table>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>跨部门经营分析<span class="tag">人效 / 标准工时产出 / 作业产值 / 质量损耗</span></h2>
      <table>
        <thead><tr><th>工作中心</th><th>标准工时</th><th>投入人时</th><th>人效</th><th>作业产值</th><th>质量损耗数量</th></tr></thead>
        <tbody>{''.join(f'<tr><td>{esc(r["workcenter_id"])}</td><td>{r["standard_hours"]}</td><td>{r["actual_hours"]}</td><td>{r["productivity"]}</td><td>{r["work_value"]}</td><td>{r["loss_quantity"]}</td></tr>' for r in d["fusion"])}</tbody>
      </table>
      <div class="note">质量损耗数量来自质检不良数量；金额损耗需要物料成本口径后再计算。</div>
    </div>
    <div class="card">
      <h2>每日经营简报<span class="tag">报告日 {esc(d["brief"]["date"])} · 08:00</span></h2>
      <table>
        <tbody>
          <tr><td>完成订单</td><td>{d["brief"]["completed"]} 单</td></tr>
          <tr><td>新增异常工单</td><td>{d["brief"]["exceptions"]} 单</td></tr>
          <tr><td>报销提交</td><td>{d["brief"]["reimbursements"][0]} 笔 / {d["brief"]["reimbursements"][1]} 元</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="card" style="margin-top:14px">
    <h2>加工二组 WC02 人效趋势（近30个有作业日）<span class="tag">人效=标准工时产出/实际人时</span></h2>
    {trend_svg}
    <div class="note">
      近7个有作业日均值 <b>{d["wc02_recent7"]}</b>，前7个有作业日均值 <b>{d["wc02_prev7"]}</b>，
      变化 <b style="color:{C_RED}">{d["wc02_change_pct"]}%</b>；近14个有作业日线性回归斜率 <b>{d["wc02_slope14"]}</b>（斜率为负=下降）。
      黄色虚线为7点移动平均。下降原因需结合设备报警/停机与报工记录核查，不在此图上断言。
    </div>
  </div>

  <div class="card" style="margin-top:14px">
    <h2>未交付订单 · 交期最近的 10 单</h2>
    <table>
      <thead><tr><th>订单号</th><th>承诺交期</th><th>状态</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    <div class="note">完整订单清单可通过页面查询和明细入口查看。</div>
  </div>

  <div class="foot">
    数据按统一业务口径计算，详情可进入对应模块查看订单、采集、趋势和日报明细。
  </div>
</div>
</body>
</html>"""
    os.makedirs(out_dir, exist_ok=True)
    fp = os.path.join(out_dir, "index.html")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(page)
    return fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    ap.add_argument("--out")
    args = ap.parse_args()
    db = find_db(args.db)
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard")
    d = load(db)
    fp = render(d, out)
    print("dashboard written:", fp)
    print("kpi: effective=%d completed=%d unfinished=%d overdue=%d" %
          (d["effective"], d["completed"], d["unfinished"], d["overdue"]))
    print("risk: red=%d yellow=%d green=%d" % (d["risk"]["red"], d["risk"]["yellow"], d["risk"]["green"]))
    print("wc02: recent7=%.6f prev7=%.6f change=%.2f%% slope14=%.6f" %
          (d["wc02_recent7"], d["wc02_prev7"], d["wc02_change_pct"], d["wc02_slope14"]))


if __name__ == "__main__":
    main()
