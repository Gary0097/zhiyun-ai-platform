# -*- coding: utf-8 -*-
"""WeKnora(8001 知识库) 客户端：登录、智能体 JSON 问答、会话、知识库概览。"""
import json
import re
import threading
import os
import urllib.request
import urllib.error

BASE = os.environ.get("WEKNORA_API", "http://host.docker.internal:18000/api/v1")
EMAIL = os.environ.get("WEKNORA_EMAIL", "")
PASSWORD = os.environ.get("WEKNORA_PASSWORD", "")
KB_NAME = os.environ.get("WEKNORA_ORDER_KB", "金汉隆-订单业务")

AGENT_NAMES = {
    "parser": "订单语义解析智能体",
    "adapter": "模板适配智能体",
    "qa": "订单业务问答智能体",
}

_lock = threading.Lock()
_token = None
_agent_ids = None


class WeKnoraError(Exception):
    pass


def _login():
    global _token
    req = urllib.request.Request(BASE + "/auth/login", method="POST",
                                 data=json.dumps({"email": EMAIL, "password": PASSWORD}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            _token = json.loads(r.read().decode())["token"]
    except Exception as e:  # noqa: BLE001
        raise WeKnoraError("WeKnora 登录失败: %s" % e)


def _tok():
    with _lock:
        t = _token
    if not t:
        _login()
        with _lock:
            t = _token
    return t


def call(method, path, body=None, timeout=60):
    global _token
    token = _tok()
    for attempt in (1, 2):
        req = urllib.request.Request(BASE + path, method=method,
                                     headers={"Authorization": "Bearer " + (token or ""),
                                              "Content-Type": "application/json"})
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urllib.request.urlopen(req, data, timeout=timeout) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 1:
                _login()
                token = _token
                continue
            raise WeKnoraError("WeKnora %s %s -> HTTP %s" % (method, path, e.code))
        except Exception as e:  # noqa: BLE001
            raise WeKnoraError("WeKnora 请求异常: %s" % e)
    raise WeKnoraError("WeKnora 认证重试失败")


def agent_ids(force=False):
    global _agent_ids
    with _lock:
        cached = None if force else _agent_ids
    if cached:
        return cached
    d = call("GET", "/agents", timeout=20)
    data = d.get("data")
    if isinstance(data, dict):
        data = data.get("list") or []
    ids = {a.get("name"): a.get("id") for a in (data or [])}
    with _lock:
        _agent_ids = ids
    return ids


def agent_id_for(kind):
    name = AGENT_NAMES.get(kind)
    if not name:
        raise WeKnoraError("未知智能体: %s" % kind)
    aid = agent_ids().get(name)
    if not aid:
        raise WeKnoraError("智能体未就绪: %s" % name)
    return aid


def create_session(title="订单处理会话"):
    d = call("POST", "/sessions", {"title": title}, timeout=20)
    return (d.get("data") or d).get("id")


def agent_answer(kind, query, session_id=None):
    """向指定智能体提问并聚合完整回答（非流式，用于结构化解析）。"""
    aid = agent_id_for(kind)
    sid = session_id or create_session()
    token = _tok()
    req = urllib.request.Request(BASE + "/agent-chat/" + sid, method="POST",
                                 data=json.dumps({"query": query, "agent_id": aid,
                                                  "agent_enabled": True}).encode(),
                                 headers={"Authorization": "Bearer " + (token or ""),
                                          "Content-Type": "application/json"})
    buf = []
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            for raw in r:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    d = json.loads(line[5:])
                except Exception:
                    continue
                if d.get("response_type") == "answer":
                    buf.append(d.get("content") or "")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            _login()
            return agent_answer(kind, query, session_id)
        raise WeKnoraError("智能体问答失败: HTTP %s" % e.code)
    except Exception as e:  # noqa: BLE001
        raise WeKnoraError("智能体问答异常: %s" % e)
    return "".join(buf), sid


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_json_answer(text: str):
    """从智能体回答中稳健提取 JSON 对象（容忍代码块、前后缀说明）。"""
    if not text:
        raise WeKnoraError("智能体未返回内容")
    candidates = []
    for m in _JSON_FENCE.finditer(text):
        candidates.append(m.group(1))
    candidates.append(text)
    for cand in candidates:
        s = cand.strip()
        start = s.find("{")
        if start < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    frag = s[start:i + 1]
                    try:
                        return json.loads(frag)
                    except Exception:
                        try:
                            return json.loads(frag.replace("\n", " "))
                        except Exception:
                            break
    raise WeKnoraError("智能体返回内容无法解析为 JSON：%s" % text[:200])


def kb_overview():
    d = call("GET", "/knowledge-bases", timeout=15)
    out = []
    for kb in d.get("data") or []:
        if kb.get("name") == KB_NAME:
            out.append({"id": kb["id"], "name": kb.get("name"),
                        "knowledge_count": kb.get("knowledge_count") or 0})
    return out


def health():
    try:
        call("GET", "/models", timeout=10)
        return True
    except Exception:  # noqa: BLE001
        return False
