from openpyxl import load_workbook
from datetime import datetime, date
import json, os, re

SRC = '/data/actions/zhizaoyun-datahub/agent_upload/production_progress_20260916.xlsx'
OUT = '/data/actions/zhizaoyun-datahub/dashboard/production_data.json'
MILESTONES = ['确认刀模图（业务部门）','图纸','采购下单','回料','备料','装配','电控打板','电控接外线','调试完成','验机完成']

def clean(v):
    if v is None: return ''
    if isinstance(v, datetime): return v.strftime('%Y-%m-%d')
    if isinstance(v, date): return v.isoformat()
    s = str(v).strip()
    if s in ('00:00:00','1900-01-00','1900-01-01'): return ''
    if re.fullmatch(r'\d{5}', s):
        try:
            d = date.fromordinal(date(1899,12,30).toordinal()+int(s)); return d.isoformat()
        except Exception: return s
    return s

def stage_for(status):
    s = status or ''
    if '已出货' in s or '已完成' in s: return 10
    if '待出货' in s: return 10
    if '验收' in s: return 9
    if '调试' in s: return 8
    if '接电' in s: return 8
    if '打板' in s or '电控' in s: return 7
    if '组装' in s or '装配' in s: return 6
    if '备料' in s or '回料' in s: return 4
    if '采购' in s: return 3
    if '图纸' in s or '刀模' in s: return 2
    return 1

wb = load_workbook(SRC, read_only=True, data_only=True)
ws = wb['生产进度总表']
rows=[]; seen=set()
for i,row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
    vals=list(row)
    order=clean(vals[4] if len(vals)>4 else '')
    if not order or order in seen: continue
    seen.add(order)
    status=clean(vals[8] if len(vals)>8 else '')
    due=clean(vals[7] if len(vals)>7 else '')
    try:
        due_dt=datetime.fromisoformat(due).date() if due else None
    except Exception: due_dt=None
    today=date(2026,9,20)
    idx=stage_for(status)
    if idx>=10: risk='green'
    elif due_dt and due_dt < today: risk='red'
    elif due_dt and (due_dt-today).days <= 7: risk='yellow'
    else: risk='green'
    nodes=[]
    for n,name in enumerate(MILESTONES,1):
        st='done' if n<idx or idx==10 else ('active' if n==idx else 'wait')
        if idx==10: st='done'
        nodes.append({'name':name,'status':st,'sourceStatus':status})
    rows.append({'order':order,'project':clean(vals[5] if len(vals)>5 else ''),'owner':clean(vals[2] if len(vals)>2 else ''),'category':clean(vals[3] if len(vals)>3 else ''),'qty':clean(vals[6] if len(vals)>6 else ''),'due':due,'status':status,'delayDays':clean(vals[13] if len(vals)>13 else ''),'exception':clean(vals[14] if len(vals)>14 else ''),'solution':clean(vals[15] if len(vals)>15 else ''),'stage':idx,'risk':risk,'nodes':nodes,'sourceRow':i})
data={'source':'生产进度表9.16.xlsx / 生产进度总表','snapshot':'2026-09-16','generatedAt':datetime.now().isoformat(timespec='seconds'),'milestones':MILESTONES,'rows':rows}
os.makedirs(os.path.dirname(OUT),exist_ok=True)
open(OUT,'w',encoding='utf-8').write(json.dumps(data,ensure_ascii=False))
print(len(rows),OUT)
