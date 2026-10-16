#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""18条盲测执行器：通过运行时控制台API向 datahub-agent 提问并保存回答。
用法:
  python3 blind_test.py --cases T01,T02        # 指定用例
  python3 blind_test.py --all                  # 全部18条
输出: /data/actions/zhizaoyun-datahub/blind_results/<case>.json + 汇总 json
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.request

from cryptography.fernet import Fernet

RUNTIME = 'http://127.0.0.1:58399'
AGENT = 'datahub-agent'
CASES_FILE = '/data/actions/zhizaoyun-datahub/blind_cases.json'
OUT_DIR = '/data/actions/zhizaoyun-datahub/blind_results'
VAULT = '/root/zhiyun-ai-platform/apps/zhizaoyunAIOS/workspace/hub/secrets/.vault_key'
CONTROL_DB = '/root/zhiyun-ai-platform/apps/zhizaoyunAIOS/workspace/hub/control.db'


def get_token():
    f = Fernet(open(VAULT).read().strip().encode())
    con = sqlite3.connect(CONTROL_DB)
    enc = con.execute(
        "SELECT encrypted_value FROM tenant_credentials WHERE credential_name="
        "'QWENPAW_RUNTIME_INTERNAL_TOKEN' AND scope LIKE 'runtime-control:personal-49e1%'"
    ).fetchone()[0]
    return f.decrypt(enc).decode()


TOKEN = get_token()
HDRS = {'X-QwenPaw-Runtime-Token': TOKEN, 'X-Agent-Id': AGENT, 'Content-Type': 'application/json'}


def api(path, method='GET', body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(RUNTIME + path, data=data, method=method, headers=HDRS)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def stream_chat(session_id, text, timeout=600):
    """POST console/chat, read SSE till end. Returns list of event dicts."""
    body = {
        'channel': 'console', 'user_id': 'default', 'session_id': session_id,
        'request_context': {'approval_level': 'OFF'},
        'input': [{'role': 'user', 'type': 'message',
                   'content': [{'type': 'text', 'text': text}]}],
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(RUNTIME + '/api/console/chat', data=data, method='POST', headers=HDRS)
    events = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        buf = b''
        while True:
            try:
                chunk = resp.read(4096)
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                line = line.decode('utf-8', 'replace').strip()
                if line.startswith('data:'):
                    payload = line[5:].strip()
                    if payload and payload != '[DONE]':
                        try:
                            events.append(json.loads(payload))
                        except Exception:
                            pass
    return events


def fetch_answer(session_id_hint):
    """Find the latest chat and its last assistant message."""
    try:
        chats = api('/api/chats?archived=false&include_app_owned=false')
    except Exception as e:
        return None, 'chats list err: %s' % e
    if isinstance(chats, list):
        items = chats
    else:
        items = chats.get('chats') or chats.get('items') or chats.get('data') or []
    if not items:
        return None, 'no chats'
    best = None
    for c in items:
        ids = ' '.join(str(c.get(k, '')) for k in ('id', 'session_id', 'chat_id', 'name', 'title'))
        if session_id_hint and session_id_hint in ids:
            best = c
            break
    if best is None:
        best = sorted(items, key=lambda c: str(c.get('updated_at') or c.get('created_at') or ''))[-1]
    cid = best.get('id') or best.get('chat_id')
    detail = api('/api/chats/%s?include_app_owned=false' % cid)
    if isinstance(detail, dict):
        msgs = detail.get('messages') or detail.get('data', {}).get('messages') or detail.get('chat', {}).get('messages') or []
    else:
        msgs = []
    answer = None
    for m in reversed(msgs):
        role = m.get('role')
        if role in ('assistant', 'agent'):
            content = m.get('content')
            text = ''
            if isinstance(content, list):
                for p in content:
                    if isinstance(p, dict) and p.get('type') in ('text', 'output_text'):
                        text += p.get('text', '')
            elif isinstance(content, dict):
                text = str(content.get('text') or content.get('content') or '')
            else:
                text = str(content or '')
            if text.strip():
                answer = text
                break
    return {'chat_id': cid, 'answer': answer, 'n_messages': len(msgs)}, None


def run_case(case):
    sid = 'bt-%s-%d' % (case['case_id'].lower(), int(time.time()))
    t0 = time.time()
    out = {'case_id': case['case_id'], 'prompt': case['prompt'], 'session_id': sid}
    events = None
    for attempt in range(4):
        try:
            events = stream_chat(sid, case['prompt'])
            break
        except Exception as e:
            msg = str(e)
            out['stream_error'] = msg[:300]
            if 'refused' in msg.lower() or 'timed out' in msg.lower() or 'reset' in msg.lower():
                time.sleep(20)
                continue
            break
    try:
        if events is None:
            raise RuntimeError(out.get('stream_error', 'no events'))
        out['n_events'] = len(events)
        # try to pull text from events as fallback evidence
        ev_texts = []
        for e in events:
            if isinstance(e, dict):
                for k in ('text', 'content', 'delta'):
                    v = e.get(k)
                    if isinstance(v, str) and len(v) > 10:
                        ev_texts.append(v)
        out['event_text_chars'] = sum(len(t) for t in ev_texts)
    except Exception as e:
        out['stream_error'] = str(e)[:300]
    time.sleep(3)
    info, err = None, None
    for attempt in range(4):
        try:
            info, err = fetch_answer(sid)
            if info:
                break
        except Exception as e:
            err = str(e)[:300]
        time.sleep(15)
    if info:
        out.update(info)
    if err:
        out['fetch_error'] = err
    out['elapsed_s'] = round(time.time() - t0, 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', help='逗号分隔用例编号')
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()
    cases = json.load(open(CASES_FILE, encoding='utf-8'))
    os.makedirs(OUT_DIR, exist_ok=True)
    if args.all:
        sel = cases
    else:
        want = set(x.strip().upper() for x in (args.cases or '').split(',') if x.strip())
        sel = [c for c in cases if c['case_id'].upper() in want]
    print('running %d cases' % len(sel), flush=True)
    for c in sel:
        r = run_case(c)
        fp = os.path.join(OUT_DIR, c['case_id'] + '.json')
        json.dump(r, open(fp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        ans = (r.get('answer') or '')[:80].replace('\n', ' ')
        print('[%s] %.0fs events=%s answer=%s' % (c['case_id'], r.get('elapsed_s', 0),
                                                  r.get('n_events'), ans), flush=True)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
