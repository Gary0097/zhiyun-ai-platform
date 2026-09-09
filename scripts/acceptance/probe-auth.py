"""Live auth probe for a disposable loopback deployment; never calls a model.

Credentials are generated locally and saved only to an explicitly supplied state
file, never stdout. Refuses registration unless --allow-test-registration is set.
"""
import argparse
import json
import secrets
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlparse

p = argparse.ArgumentParser()
p.add_argument('--url', required=True)
p.add_argument('--state', required=True)
p.add_argument('--hub', action='store_true')
p.add_argument('--allow-test-registration', action='store_true')
args = p.parse_args()
assert urlparse(args.url).hostname in ('127.0.0.1', 'localhost'), 'Only loopback test instances are allowed'
state_path = Path(args.state)
state = json.loads(state_path.read_text()) if state_path.exists() else {}

def request(method, path, body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(args.url + path, data=None if body is None else json.dumps(body).encode(), headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')

def check(value, name):
    if not value:
        raise AssertionError(name)
    print('PASS', name, flush=True)

code, info = request('GET', '/api/auth/status')
check(code == 200 and info['enabled'], 'native authentication enabled')
if not state:
    check(args.allow_test_registration and not info['has_users'], 'fresh disposable instance before registration')
    state['admin'] = {'username': 'acceptance_admin', 'password': secrets.token_urlsafe(24)}
    code, _ = request('POST', '/api/auth/register', state['admin'])
    check(code == 200, 'first user registration')
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state), encoding='utf-8')
code, login = request('POST', '/api/auth/login', state['admin'])
check(code == 200 and bool(login.get('token')), 'native login succeeds')
token = login['token']
check(request('GET', '/api/auth/verify')[0] == 401, 'anonymous access rejected')
check(request('GET', '/api/auth/verify', token=token)[0] == 200, 'authenticated session verifies')
if args.hub:
    check(login['user']['role'] == 'admin', 'bootstrap account is administrator')
    if 'employee' not in state:
        state['employee'] = {'username': 'acceptance_employee', 'password': secrets.token_urlsafe(24)}
        check(request('POST', '/api/hub/admin/users', state['employee'], token)[0] == 201, 'administrator creates employee')
        state_path.write_text(json.dumps(state), encoding='utf-8')
    code, employee = request('POST', '/api/auth/login', state['employee'])
    check(code == 200 and employee['user']['role'] == 'user', 'employee login and role')
    check(request('GET', '/api/hub/admin/users', token=employee['token'])[0] == 403, 'employee cannot access administrator users')
    runtime_id = state.get('runtime_id')
    if not runtime_id:
        runtime_id = 'acceptance-' + secrets.token_hex(4)
        code, data = request('POST', '/api/hub/runtimes', {'runtime_id': runtime_id}, token)
        if code != 201:
            print('RUNTIME_CREATE', code, str(data.get('detail', 'unknown'))[:600], flush=True)
        check(code == 201, 'create isolated runtime record')
        state['runtime_id'] = runtime_id
        state_path.write_text(json.dumps(state), encoding='utf-8')
    check(request('GET', '/api/hub/runtimes/' + runtime_id, token=employee['token'])[0] in (403,404), 'cross-user runtime access rejected')
    code, data = request('POST', '/api/hub/runtimes/' + runtime_id + '/start', {}, token)
    print('RUNTIME_START', code, str(data.get('detail', data.get('state', 'unknown')))[:600], flush=True)
    check(code == 200 and data.get('state') == 'running', 'isolated runtime starts successfully')
else:
    check(request('POST', '/api/auth/register', state['admin'])[0] == 403, 'single-user registration cannot create another account')
