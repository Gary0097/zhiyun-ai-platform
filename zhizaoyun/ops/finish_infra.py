#!/usr/bin/env python3
import json, time, subprocess, sqlite3, urllib.request, os
def tenants_now():
    BASE='http://127.0.0.1:18000/api/v1'
    req=urllib.request.Request(BASE+'/auth/login',method='POST',
        data=json.dumps({'email': EMAIL, 'password': PASSWORD}).encode(),
        headers={'Content-Type':'application/json'})
    tok=json.loads(urllib.request.urlopen(req,timeout=20).read())['token']
    req=urllib.request.Request(BASE+'/auth/me',headers={'Authorization':'Bearer '+tok})
    ms=json.loads(urllib.request.urlopen(req,timeout=20).read())['data']['memberships']
    return {m['tenant_name'].replace('专属工作空间',''):m['tenant_id'] for m in ms if '专属' in m['tenant_name']}
for round_ in range(40):
    t=tenants_now()
    if len(t)>=13: break
    subprocess.run(['python3','/tmp/ent/weknora_provision.py'],capture_output=True,timeout=900)
    time.sleep(120)
t=tenants_now()
accounts=json.load(open('/tmp/ent/accounts.json'))
mapping={a['username']:t.get(a['ent']) for a in accounts if t.get(a['ent'])}
json.dump(mapping,open('/data/actions/weknora-gateway/ent_tenants.json','w'),ensure_ascii=False,indent=1)
# 启动未开的订单中心容器
import shutil
LEGAL={'泓佳':'泓佳包装机械','捷泰克':'捷泰克智能装备','阳诚':'阳诚机械设备','大铁':'大铁数控机械',
 '达健':'达健食品包装设备','金汉隆':'金汉隆智能装备科技','瑞铂特':'瑞铂特智能装备','程旭':'程旭包装机械',
 '浩铭达':'浩铭达智能包装设备','纳丰':'纳丰机械','枫源':'枫源智能装备','卡史特':'卡史特包装机械','高益美':'高益美包装设备'}
SRC='/data/docker/volumes/app_order_center_data/_data/orders.db'
for i,a in enumerate(accounts):
    ent,uname=a['ent'],a['username']
    if not mapping.get(uname): continue
    d=f'/data/ent-ordercenter/{uname}'; os.makedirs(d,exist_ok=True)
    db=f'{d}/orders.db'; shutil.copy(SRC,db)
    c=sqlite3.connect(db); c.execute("DELETE FROM orders WHERE source_type='佛山企业订单' AND customer NOT LIKE ?",(f'%{LEGAL[ent]}%',)); c.commit(); c.close()
    port=8241+i; name=f'order-center-{uname}'
    have=subprocess.run(['docker','ps','-a','--format','{{.Names}}'],capture_output=True,text=True).stdout
    if name in have: continue
    env=['-e',f'WEKNORA_ORDER_KB={ent}-订单业务','-e',f'WEKNORA_TENANT={mapping[uname]}','-e','TZ=Asia/Shanghai']
    subprocess.run(['docker','run','-d','--name',name,'-p',f'{port}:8100','-v',f'{d}:/app/data',*env,'order-center-app:latest'],capture_output=True)
    subprocess.run(['docker','cp','/tmp/ent/_wk.py',f'{name}:/app/app/weknora.py'],capture_output=True)
    subprocess.run(['docker','restart',name],capture_output=True)
print('infra finish:',len(mapping),'/13')
