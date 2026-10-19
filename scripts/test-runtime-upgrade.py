"""Real Windows runtime acceptance in an explicitly isolated distribution.

Uses synthetic local accounts only; never reads a production installation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request
import urllib.parse


def main(root, output, single_port, hub_port):
    if os.name != 'nt':
        raise RuntimeError('Windows process-tree acceptance; use Windows')
    app = root / 'apps/zhizaoyunAIOS'
    workspace = app / 'workspace'
    # Prevent accidentally registering test accounts in an existing installation.
    marker = root / '.synthetic-runtime-acceptance'
    if not marker.is_file() or marker.read_text().strip() != 'synthetic-only':
        raise RuntimeError('Explicit synthetic distribution marker required')
    output.mkdir(parents=True, exist_ok=True)
    python = app / 'runtime/zhizaoyunAIOS/venv/Scripts/python.exe'
    command = python.with_name('qwenpaw.exe')
    env = dict(os.environ, PYTHONUTF8='1', QWENPAW_WORKING_DIR=str(workspace),
               QWENPAW_HOME=str(workspace), QWENPAW_SECRET_DIR=str(workspace / 'secret'),
               QWENPAW_AUTH_ENABLED='true')
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    results = []

    def request(port, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=data,
                                     headers={'Content-Type': 'application/json'})
        with client.open(req, timeout=60) as response:
            return json.load(response)

    def run(kind, port, restart=False):
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1', port)) == 0:
                raise RuntimeError('Acceptance port already occupied')
        arguments = [str(command), kind, '--host', '127.0.0.1', '--port', str(port)]
        if kind == 'hub':
            arguments += ['--config', str(root / 'hub.yaml')]
        with (output / f'{kind}-{int(restart)}.log').open('w', encoding='utf-8') as log:
            start = time.monotonic()
            child = subprocess.Popen(arguments, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                while time.monotonic() - start < 120:
                    if child.poll() is not None:
                        raise RuntimeError(f'{kind} exited: inspect isolated log')
                    try:
                        state = request(port, '/api/auth/status')
                        break
                    except (OSError, urllib.error.URLError):
                        time.sleep(.25)
                else:
                    raise TimeoutError(f'{kind} not ready')
                elapsed = round(time.monotonic() - start, 3)
                if not restart and not state.get('has_users'):
                    request(port, '/api/auth/register', {
                        'username': 'synthetic-upgrade-admin', 'password': secrets.token_urlsafe(24)})
                state = request(port, '/api/auth/status')
                if kind == 'app':
                    assert state['enabled'] and state['has_users']
                    version = request(port, '/api/version')
                    assert '2.2.2' in str(version), version
                    try:
                        request(port, '/api/auth/verify')
                    except urllib.error.HTTPError as exc:
                        assert exc.code == 401
                    else:
                        raise AssertionError('Anonymous token verification must fail')
                    name = 'files/合成 #办公%20.txt'
                    sample = workspace / 'workspaces/default' / name
                    sample.parent.mkdir(parents=True, exist_ok=True)
                    sample.write_text('Synthetic Unicode file delivery', encoding='utf-8')
                    query = urllib.parse.urlencode({'root': 'workspace', 'path': name})
                    url = f'http://127.0.0.1:{port}/api/agents/default/workspace/file-download?{query}'
                    with client.open(url, timeout=10) as response:
                        assert response.read() == sample.read_bytes()
                else:
                    # Existing downstream safe-bind query must still understand the
                    # actual 2.2.2 database after first-admin registration.
                    check = subprocess.run([str(python), str(app / 'scripts/hub-bind-host.py')],
                                           env=env, capture_output=True, text=True, check=True)
                    assert check.stdout.strip() == '0.0.0.0', check.stdout
                results.append({'kind': kind, 'restart': restart, 'ready_seconds': elapsed,
                                'synthetic_registration_or_persistence': 'pass'})
            finally:
                if child.poll() is None:
                    subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True)
                child.wait(timeout=20)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    with socket.socket() as s:
                        if s.connect_ex(('127.0.0.1', port)) != 0:
                            break
                    time.sleep(.2)

    workspace.mkdir(parents=True, exist_ok=True)
    sentinel = workspace / 'synthetic-preserved-document.txt'
    sentinel.write_text('Synthetic upgrade preservation fixture', encoding='utf-8')
    run('app', single_port)
    auth = workspace / 'secret/auth.json'
    original = hashlib.sha256(auth.read_bytes()).hexdigest()
    run('app', single_port, restart=True)
    assert hashlib.sha256(auth.read_bytes()).hexdigest() == original
    assert sentinel.read_text() == 'Synthetic upgrade preservation fixture'
    run('hub', hub_port)
    run('hub', hub_port, restart=True)
    (output / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--single-port', type=int, default=18088)
    parser.add_argument('--hub-port', type=int, default=18000)
    args = parser.parse_args()
    main(args.root.resolve(), args.output.resolve(), args.single_port, args.hub_port)
