#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重渲染 qwenpaw 控制台 datahub-dashboard.html（数据批次 20260920）。"""
import html
import json
import sqlite3
import datetime as dt

DB = "/data/actions/zhizaoyun-datahub/agent_data.sqlite"
OUT = ("/root/zhiyun-ai-platform/apps/zhizaoyunAIOS/runtime/qwenpaw-hub/venv/lib/"
       "python3.12/site-packages/qwenpaw/console/datahub-dashboard.html")

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
q = lambda s, *a: con.execute(s, a).fetchall()

snap = q("SELECT config_value FROM configuration WHERE config_key='snapshot_at'")[0][0]
snap_day = dt.date.fromisoformat(snap[:10])
red_line = (snap_day + dt.timedelta(days=7)).isoformat()
yellow_line = (snap_day + dt.timedelta(days=30)).isoformat()

BASE = """
WITH s AS (
  SELECT sales_order_id, COUNT(*) AS batches,
         SUM(CASE WHEN status='已签收' AND received_at IS NOT NULL AND received_at<>'' THEN 1 ELSE 0 END) AS signed
  FROM shipments GROUP BY sales_order_id)
"""
effective = q("SELECT COUNT(*) FROM v_current_orders")[0][0]
completed = q(BASE + """SELECT COUNT(*) FROM v_current_orders o JOIN s USING(sales_order_id)
                        WHERE s.signed = s.batches""")[0][0]
unfinished = effective - completed
overdue = q(BASE + """SELECT COUNT(*) FROM v_current_orders o LEFT JOIN s USING(sales_order_id)
                      WHERE (s.signed IS NULL OR s.signed < s.batches)
                        AND o.promised_delivery_at IS NOT NULL
                        AND o.promised_delivery_at < ?""", snap)[0][0]

risk_rows = q(BASE + """SELECT o.sales_order_id, o.promised_delivery_at
                        FROM v_current_orders o LEFT JOIN s USING(sales_order_id)
                        WHERE (s.signed IS NULL OR s.signed < s.batches)""")
risk = {"red": 0, "yellow": 0, "green": 0}
for r in risk_rows:
    p = r["promised_delivery_at"]
    if p and p < red_line:
        risk["red"] += 1
    elif p and p < yellow_line:
        risk["yellow"] += 1
    else:
        risk["green"] += 1

# 工序节点（87 单）
stage_rows = q("""
SELECT stage_code, MAX(stage_name) AS name,
       SUM(CASE WHEN stage_status='已完成' THEN 1 ELSE 0 END) done,
       SUM(CASE WHEN stage_status='进行中' THEN 1 ELSE 0 END) act,
       SUM(CASE WHEN stage_status='未开始' THEN 1 ELSE 0 END) pend,
       SUM(CASE WHEN planned_end_at IS NOT NULL AND planned_end_at < ?
                 AND stage_status <> '已完成' THEN 1 ELSE 0 END) over
FROM stage_nodes GROUP BY stage_code ORDER BY MIN(sequence)""", snap)
COLORS = {"PLAN": "#722ED1", "PROCESS": "#1677FF", "QC": "#D48806",
          "SHIP": "#2E8B57", "SIGN": "#8C8C8C"}

# 生产状态位相分布（由"当天状态"映射）
phase = q("""
SELECT CASE WHEN p.stage_status <> '已完成' THEN '备料/图纸/确认'
            WHEN x.stage_status <> '已完成' THEN '加工/调试'
            WHEN c.stage_status <> '已完成' THEN '验收'
            WHEN h.stage_status <> '已完成' THEN '待出货'
            ELSE '已出货' END AS ph, COUNT(DISTINCT n.sales_order_id) n
FROM stage_nodes n
JOIN stage_nodes p ON p.sales_order_id=n.sales_order_id AND p.stage_code='PLAN'
JOIN stage_nodes x ON x.sales_order_id=n.sales_order_id AND x.stage_code='PROCESS'
JOIN stage_nodes c ON c.sales_order_id=n.sales_order_id AND c.stage_code='QC'
JOIN stage_nodes h ON h.sales_order_id=n.sales_order_id AND h.stage_code='SHIP'
GROUP BY ph ORDER BY n DESC""")

ing = q("""SELECT source_system, input_record_count, loaded_record_count,
                  quarantined_record_count, run_status FROM ingestion_runs
           ORDER BY run_id""")
prod_cls = q("SELECT category_code, category_name, product_count FROM product_classification_stats ORDER BY category_code")
n_wms = q("SELECT COUNT(*) FROM wms_transactions")[0][0]
n_ship = q("SELECT COUNT(*) FROM shipments")[0][0]
n_exc = q("SELECT COUNT(*) FROM exceptions")[0][0]
n_proc = q("SELECT COUNT(*) FROM procurement_lines")[0][0]
n_contract = q("SELECT COUNT(*) FROM contracts")[0][0]

top10 = q(BASE + """SELECT o.sales_order_id, o.promised_delivery_at,
       CASE WHEN s.sales_order_id IS NULL THEN '未发货' ELSE '在途未签' END kind
FROM v_current_orders o LEFT JOIN s USING(sales_order_id)
WHERE (s.signed IS NULL OR s.signed < s.batches)
  AND o.promised_delivery_at IS NOT NULL
ORDER BY o.promised_delivery_at LIMIT 10""")

esc = html.escape
stage_html = ""
for r in stage_rows:
    total = r["done"] + r["act"] + r["pend"]
    pct = round(r["done"] / total * 100, 1) if total else 0
    color = COLORS.get(r["stage_code"], "#1677FF")
    badge = (f'<span class="node-alert">超时 {r["over"]} 单</span>' if r["over"]
             else '<span class="node-ok">按期</span>')
    stage_html += (
        f'<div class="stage-row"><div class="stage-head">'
        f'<span class="stage-name"><span class="dot" style="background:{color}"></span>{esc(r["name"])}</span>'
        f'<b>{r["done"]}/{total} 完成（{pct}%）</b>{badge}</div>'
        f'<div class="stage-bar"><span style="width:{pct}%;background:{color}"></span></div>'
        f'<div class="stage-meta">进行中 {r["act"]} · 未开始 {r["pend"]} · 数据来自 stage_nodes（生产总表）</div></div>')

mx = max([p["n"] for p in phase] or [1])
phase_bars = "".join(
    f'<div class="ph-row"><span class="ph-name">{esc(p["ph"])}</span>'
    f'<div class="ph-bar"><span style="width:{round(p["n"] / mx * 100)}%"></span></div>'
    f'<b>{p["n"]} 单</b></div>' for p in phase)

ing_rows = "".join(
    f'<tr><td title="{esc(r["source_system"])}">{esc(r["source_system"][:34])}</td>'
    f'<td>{r["input_record_count"]:,}</td><td>{r["loaded_record_count"]:,}</td>'
    f'<td><span class="source-status">{esc(r["run_status"])}</span></td></tr>' for r in ing)

cls_rows = "".join(
    f'<tr><td>{esc(r["category_code"])}</td><td>{esc(r["category_name"])}</td>'
    f'<td>{r["product_count"]:,}</td></tr>' for r in prod_cls)

top_rows = "".join(
    f'<tr><td>{esc(r["sales_order_id"])}</td>'
    f'<td>{esc((r["promised_delivery_at"] or "")[:10])}</td>'
    f'<td>{esc(r["kind"])}</td></tr>' for r in top10)

risk_max = max(risk.values() or [1])

page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>金汉隆 AI数据中枢 · 经营看板</title>
<style>
  :root {{ --ink:#1F2329; --sub:#646A73; --bg:#F5F6F7; }}
  * {{ box-sizing:border-box; }}
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
  th,td {{ text-align:left; padding:7px 8px; border-bottom:1px solid #F0F0F0; font-size:13px; }}
  th {{ color:var(--sub); font-weight:500; }}
  .note {{ margin-top:8px; font-size:12px; color:var(--sub); }}
  .stage-card {{ grid-column:1 / -1; }}
  .stage-row {{ padding:10px 0; border-top:1px solid #F0F0F0; }}
  .stage-head {{ display:flex; align-items:center; gap:12px; font-size:13px; }}
  .stage-name {{ min-width:86px; display:flex; align-items:center; }}
  .stage-head b {{ font-size:12px; font-weight:600; }}
  .stage-bar {{ height:8px; background:#F0F0F0; border-radius:8px; overflow:hidden; margin:7px 0 4px 18px; }}
  .stage-bar span {{ display:block; height:100%; border-radius:8px; }}
  .stage-meta {{ margin-left:18px; color:var(--sub); font-size:11px; }}
  .node-alert,.node-ok {{ margin-left:auto; border-radius:10px; padding:2px 7px; font-size:11px; }}
  .node-alert {{ color:#C7000B; background:#FFF1F0; }}
  .node-ok {{ color:#2E8B57; background:#F0FFF4; }}
  .dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; margin-right:8px; }}
  .ph-row {{ display:flex; align-items:center; gap:10px; margin:8px 0; font-size:13px; }}
  .ph-name {{ min-width:110px; }}
  .ph-bar {{ flex:1; height:14px; background:#F0F0F0; border-radius:7px; overflow:hidden; }}
  .ph-bar span {{ display:block; height:100%; background:linear-gradient(90deg,#1677FF,#722ED1); }}
  .fusion-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
  .metric-label {{ font-size:12px; color:var(--sub); }}
  .metric-value {{ font-size:22px; font-weight:700; margin:4px 0 2px; }}
  .source-status {{ font-size:12px; color:#1F6FEB; }}
  .foot {{ max-width:1080px; margin:6px auto 0; padding:0 16px; font-size:12px; color:var(--sub); }}
</style>
</head>
<body>
<div class="top">
  <h1>金汉隆 AI数据中枢 · 经营看板</h1>
  <div class="sub">快照时点 2026-09-20 08:00（北京时间） · 数据批次 20260920（14个业务表导出） · 只读计算副本 agent_data.sqlite</div>
</div>
<div class="wrap">
  <div class="kpis">
    <div class="kpi"><div class="kpi-label">已生效订单</div><div class="kpi-value" style="color:#1F2329">{effective:,} 单</div></div>
    <div class="kpi"><div class="kpi-label">已全量签收</div><div class="kpi-value" style="color:#2E8B57">{completed:,} 单</div></div>
    <div class="kpi"><div class="kpi-label">未全量交付</div><div class="kpi-value" style="color:#D48806">{unfinished:,} 单</div></div>
    <div class="kpi"><div class="kpi-label">其中已逾期</div><div class="kpi-value" style="color:#C7000B">{overdue:,} 单</div></div>
  </div>

  <div class="grid">
    <div class="card stage-card">
      <h2>客户订单进度 <span class="tag">计划 → 加工 → 质检 → 发货 → 签收（生产总表状态映射）</span></h2>
      <div class="stage-intro" style="font-size:12px;color:var(--sub);margin:-4px 0 12px">按订单节点展示当前进度；计划结束时间已到但节点未完成时自动标红。节点事实来自生产进度总表 87 张去重生产订单。</div>
      {stage_html}
      <div style="display:flex;gap:16px;margin-top:10px;font-size:11px;color:var(--sub)">
        <span class="node-alert">红色=节点超时</span><span class="node-ok">绿色=无超时节点</span>
        <span>工单维度进度仅覆盖已提取的 87/1228 行生产订单，其余排产表待接入</span>
      </div>
    </div>

    <div class="card">
      <h2>交付风险分布<span class="tag">交期紧迫度</span></h2>
      <svg width="100%" viewBox="0 0 760 108" preserveAspectRatio="xMidYMid meet">
        <text x="0" y="18" font-size="13" fill="#1F2329">高风险（红）</text>
        <rect x="150" y="0" width="{round(risk['red']/risk_max*500,1)}" height="26" rx="4" fill="#C7000B"/>
        <text x="658" y="18" font-size="13" fill="#646A73">{risk['red']:,}</text>
        <text x="0" y="54" font-size="13" fill="#1F2329">中风险（黄）</text>
        <rect x="150" y="36" width="{round(risk['yellow']/risk_max*500,1)}" height="26" rx="4" fill="#D48806"/>
        <text x="658" y="54" font-size="13" fill="#646A73">{risk['yellow']:,}</text>
        <text x="0" y="90" font-size="13" fill="#1F2329">低风险（绿）</text>
        <rect x="150" y="72" width="{round(risk['green']/risk_max*500,1)}" height="26" rx="4" fill="#2E8B57"/>
        <text x="658" y="90" font-size="13" fill="#646A73">{risk['green']:,}</text>
      </svg>
      <div class="note">红：已逾期或 7 天内到期；黄：8–30 天；绿：其余或无承诺交期。未交付口径含"已出货未回签"（源表交付/验收回填率 536/2328）。</div>
    </div>

    <div class="card">
      <h2>生产订单状态分布<span class="tag">生产进度总表 · 当天状态</span></h2>
      {phase_bars}
      <div class="note">由"当天状态"（待回料/待出货/待调试/调试中/待图纸/待验收等）映射到节点位相；工时/人效日志来源待接入。</div>
    </div>

    <div class="card">
      <h2>产品分类统计<span class="tag">1084 条产品逐行初分</span></h2>
      <table><thead><tr><th>编码</th><th>一级分类</th><th>产品数</th></tr></thead><tbody>{cls_rows}</tbody></table>
      <div class="note">99 待确认隔离区 41 条不建议导入正式目录；API 导入待系统 Sort1/Unitjb。</div>
    </div>
  </div>

  <div class="card" style="margin-top:14px">
    <h2>数据接入 <span class="tag">合同 · 订单 · 生产 · 采购 · 库存 · 售后</span></h2>
    <div class="fusion-grid">
      <div><div class="metric-label">合同</div><div class="metric-value">{n_contract:,} 行</div><div class="note">合同表 6881 行导出</div></div>
      <div><div class="metric-label">订单</div><div class="metric-value">{effective:,} 单</div><div class="note">机器下单 2322 + 生产总表 87</div></div>
      <div><div class="metric-label">采购/物料</div><div class="metric-value">{n_proc:,} 行</div><div class="note">物料 {len(prod_cls)*0+q('SELECT COUNT(*) FROM materials')[0][0]:,} 项</div></div>
      <div><div class="metric-label">库存期初</div><div class="metric-value">{n_wms:,} 笔</div><div class="note">发货 {n_ship:,} · 售后 {n_exc:,}</div></div>
    </div>
    <table style="margin-top:12px"><thead><tr><th>源文件</th><th>源行数</th><th>已载入</th><th>状态</th></tr></thead><tbody>{ing_rows}</tbody></table>
  </div>

  <div class="card" style="margin-top:14px">
    <h2>未交付订单 · 交期最近的 10 单</h2>
    <table><thead><tr><th>订单号</th><th>承诺交期</th><th>状态</th></tr></thead><tbody>{top_rows}</tbody></table>
    <div class="note">完整清单可通过只读 API 查询：POST /api/sql（SELECT ... FROM v_current_orders ...）。</div>
  </div>

  <div class="foot">
    <p style="margin:0 0 6px"><a href="http://127.0.0.1:18790/" target="_blank" style="color:#C7000B;font-weight:600">→ 打开订单交付与生产协同交互看板</a>　<a href="http://127.0.0.1:18790/sql.html" target="_blank" style="color:#C7000B;font-weight:600">→ SQL 只读查询台</a>（SELECT/PRAGMA，最多2000行）</p>
    数据来源：金汉隆 14 个业务表导出（2026-09-20 批次）；模拟数据已清空，来源与行级血缘见 ingestion_runs / source_file_profile / real_data_sources。
  </div>
</div>
</body>
</html>
"""
with open(OUT, "w", encoding="utf-8") as f:
    f.write(page)
print("written", OUT, len(page), "bytes")
print(json.dumps({"effective": effective, "completed": completed, "unfinished": unfinished,
                  "overdue": overdue, "risk": risk}, ensure_ascii=False))
