#!/usr/bin/env python3
"""WeKnora 免密网关（0.0.0.0:8001）
- /autologin：服务端登录 WeKnora -> 注入 token 到 localStorage -> 跳转知识库（供控制台 iframe 嵌入）
- 其余路径：反向代理 WeKnora 前端(18000)，剥离 X-Frame-Options/CSP 允许 iframe 嵌套；支持流式(SSE)
"""
import json
import threading
from datetime import datetime
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

UPSTREAM = "http://127.0.0.1:18000"
EMAIL = ""
PASSWORD = ""
PORT = 8001

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
       "te", "trailer", "trailers", "transfer-encoding", "upgrade",
       "x-frame-options", "content-security-policy"}

_tok_cache = {"token": "", "refresh": "", "exp": 0}
_tok_lock = threading.Lock()

def _jwt_exp(token):
    try:
        payload = token.split(".")[1]
        payload += "=" * ((4 - len(payload) % 4) % 4)
        import base64
        return int(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
    except Exception:
        return 0

def _switch_tenant(token, tid):
    """将账号偏好切到指定工作空间并重登，返回该空间的 token。"""
    call("PUT", "/auth/me/preferences", {"last_active_tenant_id": tid}, token)
    d = call("POST", "/auth/login", {"email": EMAIL, "password": PASSWORD})
    return d["token"], d.get("refresh_token") or ""

def call(method, path, body=None, token=None, timeout=15):
    req = urllib.request.Request(UPSTREAM + "/api/v1" + path, method=method)
    if token: req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    if body is not None: req.data = json.dumps(body).encode()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def gateway_token(force=False):
    """服务端获取「智能客服中心」空间的 token：
    临时切换工作空间取 token，随后立即还原偏好，不影响其他应用。"""
    import time as _t
    with _tok_lock:
        if not force and _tok_cache["token"] and _t.time() < _tok_cache["exp"] - 300:
            return _tok_cache["token"]
        base_token, _ = upstream_login()
        token, refresh = _switch_tenant(base_token, 10002)
        _tok_cache.update({"token": token, "refresh": refresh, "exp": _jwt_exp(token)})
        try:
            base2, _ = upstream_login()
            call("PUT", "/auth/me/preferences", {"last_active_tenant_id": 10000}, token=base2)
        except Exception:  # noqa: BLE001 - 还原失败不影响本次服务
            pass
        return token

def _ent_tenants():
    """企业账号 → 专属工作空间映射(由 weknora_provision 生成)"""
    try:
        import os as _os
        with open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ent_tenants.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


REQ_LOG = "/data/actions/weknora-gateway/requests.log"
ERR_LOG = "/data/actions/weknora-gateway/jserrors.log"

def _log(line, path=REQ_LOG):
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def upstream_login():
    req = urllib.request.Request(UPSTREAM + "/api/v1/auth/login", method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"email": EMAIL, "password": PASSWORD}).encode())
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode())
    if not d.get("token"):
        raise RuntimeError("login failed: %s" % d.get("message"))
    return d["token"], d.get("refresh_token") or ""

HIDE_GITHUB_JS = """(function(){
  function hideGH(){
    document.querySelectorAll('body *').forEach(function(el){
      if(el.childElementCount===0){
        var t=(el.textContent||'').trim();
        if(t==='GitHub'){
          var p=el.closest('a,li,[role=menuitem],button,div')||el;
          p.style.display='none';
        }
      }
    });
  }
  window.addEventListener('error',function(ev){var t=ev.target;if(t&&(t.src||t.href))send('resource: '+(t.src||t.href));},true);
  new MutationObserver(hideGH).observe(document.documentElement,{childList:true,subtree:true});
  window.addEventListener('load',hideGH);
})();"""
FORCE_ZH = """(function(){try{if(localStorage.getItem('locale')!=='zh-CN')localStorage.setItem('locale','zh-CN');}catch(e){}})();"""
ERR_COLLECT = """(function(){\n  function send(m){try{var x=new XMLHttpRequest();x.open('POST','/__jserror');x.send(String(m).slice(0,500));}catch(e){}}\n  window.onerror=function(m,s,l,c,e){send('onerror: '+m+' @'+(s||'')+':'+l);};\n  window.addEventListener('unhandledrejection',function(ev){send('promise: '+(ev.reason&&ev.reason.message||ev.reason));});\n  window.addEventListener('error',function(ev){var t=ev.target;if(t&&(t.src||t.href)){send('resource: '+(t.src||t.href));}},true);\n})();"""
AUTOLOGIN_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>正在进入知识库…</title></head>
<body style="font-family:sans-serif;background:#f6f7f9;text-align:center;padding-top:18vh">
<div style="font-size:40px">📚</div><p>正在免密进入 WeKnora 知识库…</p>
<script>
(function(){
  function send(m){try{var x=new XMLHttpRequest();x.open('POST','/__jserror');x.send(String(m).slice(0,500));}catch(e){}}
  window.onerror=function(m,s,l,c,e){send('onerror: '+m+' @'+(s||'')+':'+l);};
  window.addEventListener('unhandledrejection',function(ev){send('promise: '+(ev.reason&&ev.reason.message||ev.reason));});
  window.addEventListener('error',function(ev){var t=ev.target;if(t&&(t.src||t.href)){send('resource: '+(t.src||t.href));}},true);
})();
localStorage.setItem("weknora_token", __TOKEN_JSON__);
__REFRESH__
__TENANT_SET__
__HIDE_GITHUB__
location.replace("/platform/knowledge-bases");
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass

    def _proxy(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(UPSTREAM + self.path, method=method, data=body)
        for h in ("Content-Type", "Accept", "Authorization"):
            if self.headers.get(h):
                req.add_header(h, self.headers[h])
        # API 请求统一注入服务端有效 token，杜绝 401
        if self.path.startswith("/api/") and method != "OPTIONS" \
                and "/auth/login" not in self.path and "/auth/refresh" not in self.path:
            browser_tok = self.headers.get("Authorization", "").replace("Bearer ", "").strip()
            tok = browser_tok if browser_tok else gateway_token()
            try:
                req.add_header("Authorization", "Bearer " + tok)
                req.add_unredirected_header("Authorization", "Bearer " + tok)
            except Exception:  # noqa: BLE001
                pass
        try:
            resp = urllib.request.urlopen(req, timeout=600)
            _log(f'{datetime.now().isoformat(timespec="seconds")} {method} {self.path[:120]} -> {getattr(resp,"status",200)} auth={"Y" if self.headers.get("Authorization") else "N"}')
            if getattr(resp, "status", 200) == 401:
                tok = gateway_token(force=True)
                req2 = urllib.request.Request(UPSTREAM + self.path, method=method, data=body)
                for h in ("Content-Type", "Accept"):
                    if self.headers.get(h):
                        req2.add_header(h, self.headers[h])
                req2.add_header("Authorization", "Bearer " + tok)
                if body:
                    req2.add_header("Content-Length", str(len(body)))
                resp = urllib.request.urlopen(req2, timeout=600)
        except urllib.error.HTTPError as e:
            resp = e
        except Exception as e:
            msg = ("服务暂时不可用，请稍后刷新重试。%s" % e).encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return
        with resp:
            ctype = (resp.headers.get("Content-Type") or "")
            patch_html = ("text/html" in ctype and method == "GET"
                          and urlparse(self.path).path.rstrip("/") != "/autologin")
            buf = None
            if patch_html:
                buf = resp.read()
                try:
                    text = buf.decode("utf-8")
                    inject = ("<script>" + FORCE_ZH + ERR_COLLECT + HIDE_GITHUB_JS + "</script>")
                    if "</body>" in text:
                        text = text.replace("</body>", inject + "</body>", 1)
                    else:
                        text += inject
                    buf = text.encode("utf-8")
                except Exception:  # noqa: BLE001
                    pass
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() in HOP or k.lower() == "content-length": continue
                self.send_header(k, v)
            if patch_html and buf is not None:
                self.send_header("Content-Length", str(len(buf)))
                self.end_headers()
                self.wfile.write(buf)
                return
            cl = resp.headers.get("Content-Length")
            if cl is not None:
                self.send_header("Content-Length", cl)
                self.end_headers()
                remaining = int(cl)
                while remaining > 0:
                    chunk = resp.read(min(65536, remaining))
                    if not chunk: break
                    self.wfile.write(chunk); remaining -= len(chunk)
            else:
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        self.wfile.write(b"0\r\n\r\n"); break
                    self.wfile.write(("%x\r\n" % len(chunk)).encode())
                    self.wfile.write(chunk); self.wfile.write(b"\r\n")
                    self.wfile.flush()

    def do_GET(self):
        if urlparse(self.path).path.rstrip("/") == "/autologin":
            ent = (parse_qs(urlparse(self.path).query).get("ent") or [""])[0]
            ent_map = _ent_tenants()
            tid = ent_map.get(ent) if ent else None
            tname = f"{ent}专属工作空间" if tid else "智能客服中心"
            try:
                if tid:
                    base_tok, _ = upstream_login()
                    token, refresh = _switch_tenant(base_tok, int(tid))
                else:
                    token = gateway_token()
                    refresh = ""
            except Exception as e:
                msg = ("WeKnora 自动登录失败，请稍后重试。%s" % e).encode()
                self.send_response(502)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg); return
            html = AUTOLOGIN_HTML.replace("__TOKEN_JSON__", json.dumps(token))
            tset = ("localStorage.setItem('locale','zh-CN');"
                    "localStorage.setItem('weknora_selected_tenant_id',%s);"
                    "localStorage.setItem('weknora_selected_tenant_name',%s);"
                    % (json.dumps(str(tid or 10002)), json.dumps(tname)))
            html = html.replace("__TENANT_SET__", tset)
            html = html.replace("__HIDE_GITHUB__", HIDE_GITHUB_JS)
            html = html.replace("__REFRESH__",
                "localStorage.setItem('weknora_refresh_token', %s);" % json.dumps(refresh) if refresh else "")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(html.encode())))
            self.end_headers()
            self.wfile.write(html.encode()); return
        self._proxy("GET")

    def do_POST(self):
        if urlparse(self.path).path == "/__jserror":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                msg = self.rfile.read(n).decode("utf-8", "replace")[:600]
                _log(f'{datetime.now().isoformat(timespec="seconds")} JSERROR {msg}', ERR_LOG)
            except Exception: pass
            self.send_response(204); self.send_header("Content-Length", "0"); self.end_headers()
            return
        self._proxy("POST")
    def do_PUT(self): self._proxy("PUT")
    def do_PATCH(self): self._proxy("PATCH")
    def do_DELETE(self): self._proxy("DELETE")
    def do_HEAD(self): self._proxy("HEAD")
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    print(f"WeKnora gateway on 0.0.0.0:{PORT} -> {UPSTREAM}", flush=True)
    srv.serve_forever()
