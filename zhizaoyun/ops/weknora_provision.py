#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WeKnora 13家专属工作空间供给: 租户+3知识库+7智能体/家, 产出网关路由映射"""
import json, urllib.request, time

BASE = os.environ.get('WEKNORA_API', 'http://127.0.0.1:18000/api/v1')
EMAIL = os.environ.get("WEKNORA_EMAIL", "")
PASSWORD = os.environ.get("WEKNORA_PASSWORD", "")
accounts = json.load(open('/tmp/ent/accounts.json'))
profiles = json.load(open('/tmp/ent/profiles.json'))
itl = json.load(open('/tmp/ent/it_landscape.json'))
prods = json.load(open('/tmp/ent/chat_products.json'))
stats = json.load(open('/tmp/ent/chat_stats.json'))
ctx = json.load(open('/tmp/ent/context.json'))

def call(m, p, b=None, tok=None, timeout=25, _retry=0):
    req = urllib.request.Request(BASE + p, method=m,
        data=json.dumps(b).encode() if b is not None else None,
        headers={'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + tok} if tok else {})})
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 429 and _retry < 6:
            time.sleep(45 * (_retry + 1))
            return call(m, p, b, tok, timeout, _retry + 1)
        raise
    return json.loads(r.read())

def login(tid=None):
    tok = call('POST', '/auth/login', {'email': EMAIL, 'password': PASSWORD})['token']
    if tid:
        call('PUT', '/auth/me/preferences', {'last_active_tenant_id': tid}, tok=tok)
        tok = call('POST', '/auth/login', {'email': EMAIL, 'password': PASSWORD})['token']
    return tok

# 基准配置(来自10002/10000的成熟agent)
tok02 = login(10002)
src_agents = {a['name']: a for a in call('GET', '/agents', tok=tok02)['data'] if not a.get('is_builtin')}
tok00 = login(10000)
src_agents.update({a['name']: a for a in call('GET', '/agents', tok=tok00)['data'] if not a.get('is_builtin')})
EMB = call('GET', '/knowledge-bases', tok=tok02)['data'][0]['embedding_model_id']

def clone_cfg(src_name, kb_ids, prompt):
    c = json.loads(json.dumps(src_agents[src_name]['config']))
    c['knowledge_bases'] = kb_ids
    c['system_prompt'] = prompt
    return c

# 清理探测租户
try:
    tok = login()
    call('DELETE', '/tenants/10003', tok=tok)
    print('探测租户10003已删')
except Exception as e:
    print('10003清理:', str(e)[:60])

mapping = {}
for a in accounts:
    ent = a['ent']
    full_ctx = ctx.get(ent, {})
    loc = full_ctx.get('loc', '佛山')
    P = prods.get(ent, ['标准机型'])[:6]
    P3 = '、'.join(P[:3]); P4 = '、'.join(P[:4]); P5 = '、'.join(P[:5])
    S = stats.get(ent, {'n': 0, 'amt': 0})
    tok = login()
    # 已存在则跳过
    mine = call('GET', '/auth/me', tok=tok)['data']['memberships']
    exist = [m for m in mine if m['tenant_name'] == f'{ent}专属工作空间']
    if exist:
        tid = exist[0]['tenant_id']
        mapping[a['username']] = tid
        print(f'{ent}: 已存在 {tid}, 跳过')
        continue
    t = call('POST', '/tenants', {'name': f'{ent}专属工作空间',
        'description': f'{ent}智能客服与订单业务专属空间'}, tok=tok)['data']
    tid = t['id']
    time.sleep(2)
    tok = login(tid)
    # 3 KB
    kb_ids = {}
    for kname, desc in [
        (f'{ent}-订单业务', f'{ent}订单政策、交付流程与对账口径'),
        (f'{ent}-产品知识', f'{ent}设备知识：{P3}等'),
        (f'{ent}-售后支持', f'{ent}售后政策、维修案例与配件供应')]:
        kb = call('POST', '/knowledge-bases', {'name': kname, 'description': desc,
            'embedding_model_id': EMB}, tok=tok)['data']
        kb_ids[kname] = kb['id']
        time.sleep(2)
    kb_all = list(kb_ids.values())
    # 7 智能体
    AG = [
        ('订单业务问答智能体', '订单业务问答智能体', [kb_ids[f'{ent}-订单业务']],
         f'你是「{ent}订单业务问答智能体」。基于《{ent}-订单业务》知识库回答{ent}客户关于下单、交付进度、对账开票的问题。'
         f'{ent}累计成交 {S["n"]} 单，主力机型 {P3}。回复用中文、简洁专业，涉及具体订单时提示客户提供订单号。'),
        ('订单语义解析智能体', '订单语义解析智能体', [kb_ids[f'{ent}-订单业务']],
         f'你是「{ent}订单语义解析智能体」。解析客户发来的订单文本（邮件/PDF/微信），提取品名、数量、交期、收货信息，'
         f'参照《{ent}-产品知识》机型（{P5}）做规格归一，输出结构化JSON。'),
        ('模板适配智能体', '模板适配智能体', [kb_ids[f'{ent}-订单业务']],
         f'你是「{ent}模板适配智能体」。把解析后的订单字段适配到{ent}的ERP录入模板，缺失字段给出默认值建议与提醒。'),
        ('产品咨询智能体', '产品咨询智能体', [kb_ids[f'{ent}-产品知识'], kb_ids[f'{ent}-售后支持']],
         f'你是「{ent}产品咨询智能体」。基于《{ent}-产品知识》回答设备选型、参数、耗材问题，'
         f'主打机型 {P4}；超出知识库时建议联系{loc}售后工程师。'),
        ('售后支持智能体', '售后支持智能体', [kb_ids[f'{ent}-售后支持']],
         f'你是「{ent}售后支持智能体」。解析报修描述，从《{ent}-售后支持》匹配案例（现象→原因→方案→配件），'
         '给出建议技师方向、配件清单与预计处理时长；紧急故障提示拨打服务热线。'),
        ('意图识别与语义理解智能体', '意图识别与语义理解智能体', kb_all,
         f'你是「{ent}意图识别智能体」。判断客户消息意图（订单查询/产品咨询/售后报修/投诉建议），输出意图标签与置信度，'
         '并路由到对应智能体。'),
        ('知识抽取与标签智能体', '知识抽取与标签智能体', kb_all,
         f'你是「{ent}知识抽取智能体」。从对话与文档中抽取关键信息（机型、故障码、配件、日期），打上业务标签归档。'),
    ]
    src_pool = ['订单业务问答智能体', '订单语义解析智能体', '模板适配智能体', '客户意图响应智能体',
                '售后工单调度智能体', '意图识别与语义理解智能体', '知识抽取与标签智能体']
    for (name, src_name, kbs, prompt), fallback in zip(AG, src_pool):
        src = src_name if src_name in src_agents else fallback
        try:
            call('POST', '/agents', {'name': name, 'description': f'你是「{name}」',
                'config': clone_cfg(src, kbs, prompt)}, tok=tok)
        except Exception as e:
            print(f'  {ent} {name} 创建失败: {str(e)[:60]}')
        time.sleep(2)
    mapping[a['username']] = tid
    print(f'{ent}: 租户{tid} KB×3 智能体×7 完成')

json.dump(mapping, open('/data/actions/weknora-gateway/ent_tenants.json', 'w'), ensure_ascii=False, indent=1)
print('\n映射已保存:', len(mapping), '家')
