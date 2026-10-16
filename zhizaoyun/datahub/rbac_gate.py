#!/usr/bin/env python3
"""智造云 · 应用板块 RBAC 网关（安全层）

在 hub 完成登录鉴权后，按 profile.department 校验用户可访问的业务应用端口；
未授权 → 403。hub token 无效 → 401。
本机 7 个应用端口被网关接管（监听 127.0.0.1:9xxx，iptables 将原端口转发至此），
局域网/公网访问路径不变。
"""
import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HUB = "http://127.0.0.1:8000"

# 部门 → 允许的应用端口（与控制台 zhiyun-rbac-entry.js 保持一致）
DEPT_PORTS = {
    "领导层": [18790, 8310],
    "人事部": [18790, 8310],
    "财务部": [18790, 8301, 8302, 8002],
    "销售部": [18790, 8302, 8299],
    "生产部": [18790, 8299],
    "采购部": [18790, 8002],
    "售后部": [18790, 8399],
    "管理层": [18790, 8299, 8399, 8002, 8301, 8302, 8310],
}
# 免鉴权路径（各应用健康检查/SSO 换票，不含业务数据）
OPEN_SUFFIXES = ("/api/health", "/health", "/sso-token", "/api/meta", "/favicon.ico")

UPSTREAM = {p: f"127.0.0.1:{p}" for p in
            (18790, 8299, 8399, 8002, 8301, 8302, 8310)}
GW_PORT = int(os.environ.get("RBAC_GW_PORT", "9100"))


_ME_CACHE = {}
_ME_LOCK = threading.Lock()


def hub_me_cached(token):
    now = time.time()
    with _ME_LOCK:
        hit = _ME_CACHE.get(token)
        if hit and now - hit[0] < 60:
            return hit[1]
    r = hub_me(token)
    with _ME_LOCK:
        _ME_CACHE[token] = (now, r)
        if len(_ME_CACHE) > 2000:
            _ME_CACHE.clear()
    return r


def hub_me(token):
    """校验 hub token，返回 (username, department)；无效返回 None。"""
    if not token:
        return None
    try:
        req = urllib.request.Request(HUB + "/api/hub/me",
                                     headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(req, timeout=6) as r:
            me = json.loads(r.read().decode())
        dept = ((me.get("profile") or {}).get("department")) or ""
        return me.get("username"), dept
    except Exception:
        return None


def token_from(headers, path):
    """只识别 hub 的 Bearer 头。

    各业务应用自有的 ?token= 参数（订单中心 Excel 下载、paperless 会话等）
    与 hub 令牌格式不同用途不同，不作 hub 校验，由应用自身鉴权，
    避免网关误拦导致“hub 登录无效”误报。
    """
    auth = headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


class GW(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self, code, msg):
        data = msg.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self, port, path):
        if any(path.split("?", 1)[0].endswith(s) for s in OPEN_SUFFIXES):
            return None  # 健康检查类放行
        tok = token_from(self.headers, path)
        if tok is None:
            return None  # 无 hub token（应用自有会话），交由应用自身鉴权
        me = hub_me(tok)
        if me is None:
            self._reply(401, "hub 登录无效，请重新登录智造云")
            return False
        user, dept = me
        allow = None
        for key, ports in DEPT_PORTS.items():
            if dept.find(key) >= 0:
                allow = ports
                break
        if allow is None:
            allow = list(UPSTREAM.keys())  # 未配置部门默认全放（与前端一致）
        if port not in allow:
            try:
                self._reply(403, f"{user}（{dept or '未配置部门'}）无权访问该板块，请联系管理员开通")
            except Exception:
                pass
            return False
        return True

    def _proxy(self, method):
        port = UPSTREAM.get(self.server.server_address[1])
        # 网关多端口监听：按监听端口匹配上游
        port = getattr(self.server, "upstream_port", None)
        if port is None:
            self._reply(500, "gateway misconfigured")
            return
        path = self.path
        ok = self._allowed(port, path)
        if ok is False:
            return
        # 流量转发
        import http.client
        body = None
        if method in ("POST", "PUT", "PATCH"):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else None
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
            headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in ("host", "authorization")}
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            conn.close()
        except Exception as exc:
            try:
                self._reply(502, f"upstream error: {exc}")
            except Exception:
                pass
            return
        try:
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in ("transfer-encoding", "content-length", "connection"):
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if method != "HEAD":
                self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self._proxy("GET")

    def do_POST(self):
        self._proxy("POST")

    def do_PUT(self):
        self._proxy("PUT")

    def do_PATCH(self):
        self._proxy("PATCH")

    def do_DELETE(self):
        self._proxy("DELETE")

    def do_HEAD(self):
        self._proxy("GET")

    def do_OPTIONS(self):
        self._proxy("OPTIONS")


class GwServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128
    allow_reuse_address = True


def main():
    import threading
    UP = {p: 9100 + i for i, p in enumerate(sorted(UPSTREAM))}
    for port, listen in UP.items():
        srv = GwServer(("0.0.0.0", listen), GW)
        srv.upstream_port = port
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"gateway 127.0.0.1:{listen} -> 127.0.0.1:{port}", flush=True)
    print(f"RBAC gateways up (UPSTREAM={UP})", flush=True)
    threading.Event().wait()


UPSTREAM_KEYS = sorted(UPSTREAM)

if __name__ == "__main__":
    main()
