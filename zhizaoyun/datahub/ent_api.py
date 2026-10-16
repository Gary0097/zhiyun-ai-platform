#!/usr/bin/env python3
"""企业专属ERP — 按品牌差异化UI(金蝶/用友/鼎捷/智造云/未接入)"""
import json, os, sqlite3, sys, hashlib, hmac, base64, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

DB = os.environ.get("ENT_DB","")
PORT = int(os.environ.get("ENT_PORT","0"))
ENT = os.environ.get("ENT_NAME","")
BRAND = os.environ.get("ERP_BRAND","")
COLOR = os.environ.get("ERP_COLOR","#666")
ICON = os.environ.get("ERP_ICON","📋")
INTEG = os.environ.get("ERP_INTEG","")
STATUS = os.environ.get("ERP_STATUS","")
CRM = os.environ.get("ENT_CRM","false")=="true"

def db():
    con = sqlite3.connect(f"file:{DB}?mode=ro",uri=True)
    con.row_factory = sqlite3.Row
    return con

BRAND_UI = {
 "金蝶": {"nav":"金蝶云·订单管理","style":"font-size:13px;background:#fff;border-bottom:2px solid {c};.kpi{{border-top:3px solid {c}}}th{{background:{c}15}}"},
 "用友": {"nav":"畅捷通·销售管理","style":"font-size:14px;background:#fafafa;border-bottom:1px solid {c};.kpi{{border-left:3px solid {c}}}th{{background:{c}08}}"},
 "鼎捷": {"nav":"鼎捷·生产订单","style":"font-size:13px;background:#f0f4f4;border-bottom:2px solid {c};.kpi{{border-radius:0;border-top:3px solid {c}}}th{{color:{c}}}"},
 "智造云": {"nav":"智造云·订单处理中心","style":"font-size:14px;background:#fff;border-bottom:1px solid #e0e0e0;.kpi{{border-radius:12px;border:1px solid #eee}}th{{background:{c}10;color:{c}}}"},
}
def get_brand_ui():
    if not BRAND: return {"nav":"订单管理 · 手工录入","style":".kpi{{opacity:.5}}"}
    for k,v in BRAND_UI.items():
        if k in BRAND: return v
    return BRAND_UI["智造云"]

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>{ent}·{nav}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:{font};background:{bg};color:#222}}
.top{{height:50px;background:#fff;border-bottom:2px solid {c};display:flex;align-items:center;padding:0 18px;gap:10px}}
.ic{{font-size:22px}}
.tt{{font-size:15px;font-weight:700;color:{c}}}
.st{{font-size:11px;color:{c}aa;border:1px solid {c}44;padding:1px 8px;border-radius:10px;margin-left:6px}}
.sep{{flex:1}}
.env{{font-size:11px;color:#999}}.integ{{font-size:11px;color:{c}}}
.wrap{{padding:18px;max-width:1200px;margin:0 auto}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}}
.kpi{{background:#fff;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06);{kstyle}}}
.kpi .k{{font-size:11px;color:#999}}.kpi .v{{font-size:24px;font-weight:700;color:{c}}}
.card{{background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.06);overflow:hidden}}
.card h3{{font-size:13px;padding:12px 16px;border-bottom:1px solid #f0f0f0;color:#555}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th{{padding:9px 14px;text-align:left;font-weight:600;{thstyle}}}
td{{padding:9px 14px;border-bottom:1px solid #f5f5f5}}
.tag{{padding:2px 8px;border-radius:10px;font-size:10.5px}}
.g{{background:#e8f5e9;color:#2e7d32}}.o{{background:#fff3e0;color:#ef6c00}}.b{{background:#e3f2fd;color:#1565c0}}.n{{background:#f5f5f5;color:#999}}
.noerp{{text-align:center;padding:60px 20px;background:#fff;border-radius:12px}}
.noerp .i{{font-size:48px}}.noerp p{{color:#999;margin-top:12px;font-size:14px}}
</style></head><body>
<div class="top">
  <span class="ic">{icon}</span><span class="tt">{nav}</span><span class="st">{status}</span>
  <div class="sep"></div><span class="integ">{integ}</span><span class="env">{ent}</span>
</div>
<div class="wrap">
{body}
</div>
<script>
fetch('/api/orders').then(r=>r.json()).then(d=>{{
  if(document.getElementById('kpis')){{
    document.getElementById('kpis').innerHTML=[
      ['订单总数',d.kpi.orders],['累计金额',d.kpi.amount+'万'],['已完工',d.kpi.completed+'单'],['逾期预警',d.kpi.overdue+'单']
    ].map(x=>'<div class="kpi"><div class="k">'+x[0]+'</div><div class="v">'+x[1]+'</div></div>').join('');
    document.getElementById('ob').innerHTML=d.orders.map(o=>
      '<tr><td><b>'+o.id+'</b></td><td>'+o.device+'</td><td>'+o.qty+'</td><td>'+o.amount+'</td><td>'+o.due+'</td><td>'+o.stage+'</td><td><span class="tag '+o.cls+'">'+o.status+'</span></td></tr>'
    ).join('')||'<tr><td colspan=7 style="color:#999;text-align:center;padding:16px">暂无</td></tr>';
  }}
}});
</script></body></html>"""

def build_page():
    ui=get_brand_ui()
    font = "'PingFang SC','Microsoft YaHei',sans-serif"
    bg = "#f5f6f7" if "智造云" in BRAND else ("#f0f4f8" if "金蝶" in BRAND else "#fafafa")
    if BRAND and "金蝶" in BRAND:
        kstyle=f"border-top:3px solid {COLOR}"; thstyle=f"background:{COLOR}15;color:{COLOR}"
    elif BRAND and ("用友" in BRAND or "畅捷通" in BRAND):
        kstyle=f"border-left:3px solid {COLOR}"; thstyle=f"background:{COLOR}08;color:{COLOR}"
    elif BRAND and "鼎捷" in BRAND:
        kstyle=f"border-radius:0;border-top:3px solid {COLOR}"; thstyle=f"color:{COLOR};border-bottom:2px solid {COLOR}"
    else:
        kstyle="border:1px solid #eee;border-radius:12px"; thstyle=f"background:{COLOR}10;color:{COLOR}"
    if not BRAND:
        body='<div class="noerp"><div class="i">📋</div><p>订单管理（Excel 手工录入模式）</p><p style="font-size:12px;margin-top:6px">当前数据通过'+INTEG+'维护</p></div>'
    else:
        body=('<div class="kpis" id="kpis"></div>'
              '<div class="card"><h3>订单明细</h3><table><thead><tr><th>订单号</th><th>设备</th><th>数量</th><th>金额(万)</th><th>交期</th><th>当前节点</th><th>状态</th></tr></thead><tbody id="ob"></tbody></table></div>')
    return PAGE.format(ent=ENT,nav=ui["nav"],c=COLOR,icon=ICON,status=STATUS,integ=INTEG,
                       font=font,bg=bg,kstyle=kstyle,thstyle=thstyle,body=body)

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _send(self,code,data,ctype="application/json;charset=utf-8"):
        b=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(b)))
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        p=urlparse(self.path).path
        if p=="/api/orders":
            con=db()
            rows=[dict(r) for r in con.execute("""
                SELECT o.sales_order_id id,o.packaged_goods device,o.quantity qty,
                       ROUND(o.contract_amount/10000,1) amount,
                       substr(o.promised_delivery_at,1,10) due,
                       (SELECT GROUP_CONCAT(stage_code||':'||stage_status) FROM stage_nodes n WHERE n.sales_order_id=o.sales_order_id) stages
                FROM orders o ORDER BY o.created_at DESC""")]
            ov=con.execute("SELECT COUNT(*) FROM orders o JOIN stage_nodes n ON n.sales_order_id=o.sales_order_id WHERE n.planned_end_at<(SELECT config_value FROM configuration WHERE config_key='snapshot_at') AND n.stage_status<>'已完成'").fetchone()[0]
            cp=con.execute("SELECT COUNT(DISTINCT sales_order_id) FROM stage_nodes WHERE stage_code='SIGN' AND stage_status='已完成'").fetchone()[0]
            con.close()
            out=[]
            for r in rows:
                st=r.pop('stages','') or ''
                cur,stat,cls='—','排产中','b'
                if 'PROCESS:进行中' in st: cur,stat,cls='加工','加工中','o'
                if 'QC:进行中' in st: cur,stat,cls='质检','质检中','o'
                if 'SHIP:已完成' in st and 'SIGN:未开始' in st: cur,stat,cls='在途','已发货','b'
                if 'SIGN:已完成' in st: cur,stat,cls='签收','已签收','g'
                r['stage'],r['status'],r['cls']=cur,stat,cls
                out.append(r)
            return self._send(200,{"kpi":{"orders":len(rows),"amount":round(sum(r['amount'] or 0 for r in rows),1),"completed":cp,"overdue":ov},"orders":out})
        return self._send(200,build_page().encode(),"text/html;charset=utf-8")

if __name__=="__main__":
    print(f"ERP on :{PORT} [{ENT}] brand={BRAND} status={STATUS}",flush=True)
    ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
