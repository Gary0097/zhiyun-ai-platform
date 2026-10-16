#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""13家专属财务实例: 生成各家企业口径finance.db + 启动容器(8311-8323) + 改标题"""
import sqlite3, json, random, subprocess, os, shutil
from datetime import date, timedelta

random.seed(20261022)
accounts = json.load(open('/tmp/ent/accounts.json'))
LEGAL = {'泓佳': '佛山市泓佳包装机械有限公司', '捷泰克': '广东捷泰克智能装备有限公司',
         '阳诚': '佛山市阳诚机械设备有限公司', '大铁': '广东大铁数控机械有限公司',
         '达健': '佛山达健食品包装设备有限公司', '金汉隆': '广东金汉隆智能装备科技有限公司',
         '瑞铂特': '佛山市瑞铂特智能装备有限公司', '程旭': '佛山程旭包装机械有限公司',
         '浩铭达': '广东浩铭达智能包装设备有限公司', '纳丰': '佛山市纳丰机械有限公司',
         '枫源': '佛山枫源智能装备有限公司', '卡史特': '佛山市卡史特包装机械有限公司',
         '高益美': '佛山高益美包装设备有限公司'}
FEES = ['差旅费', '业务招待费', '办公费', '交通费', '维修费', '展会费']
SUPS = ['佛山崎峻金属材料', '东莞博创精密件', '广州亿铭电气', '顺德洛钢五金', '深圳合信传感器',
        '中山精工轴件', '佛山华亚包装材料', '宁波宏达液压']
MATS = [('电气件', 'PLC控制器'), ('电气件', '伺服电机'), ('结构件', '机架型材'), ('结构件', '精密轴承'),
        ('气动件', '气缸组件'), ('传动件', '减速机'), ('耗材', '切刀组件'), ('电气件', '变频器'),
        ('结构件', '导轨丝杆'), ('辅料', '防护罩板')]


def gen_finance(ent, uname):
    src = sqlite3.connect('file:/data/actions/zhizaoyun-datahub/ent/%s.sqlite?mode=ro' % uname, uri=True)
    d = f'/data/ent-finance/{uname}'
    os.makedirs(d, exist_ok=True)
    db = f'{d}/finance.db'
    if os.path.exists(db):
        os.unlink(db)
    con = sqlite3.connect(db)
    con.executescript("""CREATE TABLE reimburse(id INTEGER PRIMARY KEY, req_date TEXT, fee_type TEXT,
        title TEXT, tax_no TEXT, amount REAL, company TEXT, invoice_date TEXT, forbidden INTEGER, result TEXT);
        CREATE TABLE ar(contract_no TEXT, customer TEXT, occur_date TEXT, amount REAL, kind TEXT,
        aging_days INTEGER, warn60 INTEGER, status TEXT);
        CREATE TABLE ap(pay_no TEXT, supplier TEXT, pay_date TEXT, amount REAL, kind TEXT, status TEXT);
        CREATE TABLE orders(order_no TEXT, customer TEXT, device_model TEXT, bom_cost REAL,
        material_count INTEGER, origin_no TEXT);
        CREATE TABLE order_bom(order_no TEXT, seq INTEGER, material_code TEXT, prefix TEXT,
        category TEXT, name TEXT, qty REAL, unit_cost REAL, cost REAL, supply TEXT);
        CREATE TABLE monthly(month TEXT, revenue REAL, cost REAL, profit REAL, margin REAL, anomalies TEXT);
        CREATE TABLE parts(id INTEGER PRIMARY KEY, code TEXT, name TEXT, category TEXT, unit TEXT,
        std_cost REAL, supply TEXT);""")
    full = LEGAL[ent]
    # 订单+BOM
    rows = src.execute("SELECT sales_order_id, contract_no, packaged_goods, contract_amount, created_at "
                       "FROM orders WHERE order_source='佛山企业订单' ORDER BY created_at").fetchall()
    for so, ct, dev, amt, cr in rows:
        bomc = round(amt * random.uniform(.58, .72), 2)
        con.execute("INSERT INTO orders VALUES(?,?,?,?,?,?)",
                    (so, full, dev, bomc, random.randint(3, 8), ct))
        k = random.randint(3, 6)
        for i in range(1, k + 1):
            cat, name = random.choice(MATS)
            unit = round(random.uniform(80, 4200), 2)
            qty = random.randint(1, 6)
            con.execute("INSERT INTO order_bom VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (so, i, f'M{random.randint(1000, 9999)}', f'{ent[:1].upper()}{i:02d}', cat, name,
                         qty, unit, round(qty * unit, 2), random.choice(SUPS)))
    # 应收(合同口径, 按企业合同来源; 客户取订单客户名)
    buyers = {r[0]: r[1] for r in src.execute(
        "SELECT o.contract_no, c.customer_name FROM orders o LEFT JOIN customers c ON c.customer_id=o.customer_id "
        "WHERE o.order_source='佛山企业订单'")}
    for ct, recv, unpaid, signed in src.execute(
            "SELECT contract_no, COALESCE(received_amount,0), COALESCE(unpaid_amount,0), signed_at "
            "FROM contracts WHERE source_file='佛山企业订单.xlsx' ORDER BY signed_at DESC LIMIT 400").fetchall():
        if not ct:
            continue
        d0 = date.fromisoformat(signed[:10])
        aging = max(0, (date(2026, 10, 7) - d0).days - 30)
        st = '已回款' if unpaid <= 0 else ('逾期' if aging > 30 else '未到期')
        con.execute("INSERT INTO ar VALUES(?,?,?,?,?,?,?,?)",
                    (ct, buyers.get(ct) or full, signed[:10], round(unpaid or 0, 2), '合同尾款', aging,
                     1 if aging > 60 else 0, st))
    # 应付
    for i in range(random.randint(12, 26)):
        pd = date(2026, random.randint(6, 9), random.randint(1, 28))
        con.execute("INSERT INTO ap VALUES(?,?,?,?,?,?)",
                    (f'AP{pd.strftime("%y%m")}{i:03d}', random.choice(SUPS), pd.isoformat(),
                     round(random.uniform(8000, 260000), 2), random.choice(['材料款', '加工费', '外协费']),
                     random.choice(['已付', '已付', '待付'])))
    # 报销
    for i in range(random.randint(36, 64)):
        rd = date(2026, random.randint(5, 9), random.randint(1, 28))
        amt = round(random.uniform(180, 5800), 2)
        con.execute("INSERT INTO reimburse VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (i + 1, rd.isoformat(), random.choice(FEES), full, full,
                     f'9144060{random.randint(10, 99)}MA{random.randint(10, 99)}X{random.randint(10, 99)}',
                     amt, (rd + timedelta(days=random.randint(0, 5))).isoformat(), 0, '通过'))
    # 月度经营
    mon = {}
    for so, amt, cr in src.execute("SELECT sales_order_id, contract_amount, created_at FROM orders "
                                   "WHERE order_source='佛山企业订单'").fetchall():
        m = cr[:7]
        if m < '2026-01':
            continue
        mon.setdefault(m, [0, 0])
        mon[m][0] += amt
        mon[m][1] += amt * .66
    for m in sorted(mon):
        rev, cost = mon[m]
        prof = rev - cost
        con.execute("INSERT INTO monthly VALUES(?,?,?,?,?,?)",
                    (m, round(rev, 2), round(cost, 2), round(prof, 2),
                     round(prof / rev * 100, 1) if rev else 0, ''))
    # 物料主数据
    for i in range(60):
        cat, name = random.choice(MATS)
        con.execute("INSERT INTO parts VALUES(?,?,?,?,?,?,?)",
                    (i + 1, f'M{random.randint(1000, 9999)}', f'{name}{i + 1:02d}', cat, '件',
                     round(random.uniform(80, 4200), 2), random.choice(SUPS)))
    con.commit()
    n = [con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in
         ('orders', 'order_bom', 'ar', 'ap', 'reimburse', 'monthly')]
    con.close()
    src.close()
    return n


BASEPORT = 8311
env_keys = subprocess.run(['docker', 'inspect', 'finance-hub-app', '--format',
                           '{{range .Config.Env}}{{println .}}{{end}}'], capture_output=True, text=True).stdout
llm_env = [l for l in env_keys.splitlines() if l.startswith('FINANCE_LLM')]
for i, a in enumerate(accounts):
    ent, uname = a['ent'], a['username']
    n = gen_finance(ent, uname)
    port = BASEPORT + i
    name = f'finance-ent-{uname}'
    subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
    r = subprocess.run(['docker', 'run', '-d', '--name', name, '-p', f'{port}:8080',
                        '-v', f'/data/ent-finance/{uname}:/app/data',
                        '-e', f'FINANCE_COMPANY={LEGAL[ent]}', '-e', 'TZ=Asia/Shanghai',
                        *sum([['-e', e] for e in llm_env], []), 'finance-hub:v1'],
                       capture_output=True, text=True)
    if r.returncode:
        print(f'{ent}: 容器失败 {r.stderr[:80]}')
        continue
    # 标题改企业名
    subprocess.run(['docker', 'exec', name, 'sed', '-i',
                    f's/· 金汉隆</· {ent}</', '/app/templates/base.html'], capture_output=True)
    print(f'{ent}: 端口{port} 订单{n[0]} BOM{n[1]} 应收{n[2]} 应付{n[3]} 报销{n[4]} 月度{n[5]}')
print('\n财务13实例完成')
