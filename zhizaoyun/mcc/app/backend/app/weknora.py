# -*- coding: utf-8 -*-
"""WeKnora(8001 知识库) 客户端：登录、会话、智能体 SSE 流式问答、知识库概览。"""
import json
import os
import re
import threading
import urllib.request

BASE = os.environ.get("WEKNORA_API", "http://host.docker.internal:18000/api/v1")
EMAIL = os.environ.get("WEKNORA_EMAIL", "")
PASSWORD = os.environ.get("WEKNORA_PASSWORD", "")
KB_NAME = os.environ.get("WEKNORA_KB_NAME", "金汉隆-管理协同中心")

# 模块 key -> WeKnora 智能体名（setup_mcc_weknora.py 创建后回填 agent id）
AGENT_NAMES = {
    "perm": "权限规则推理智能体",
    "contact": "人员信息关联智能体",
    "kb": "知识结构化与检索智能体",
    "approval": "审批路径推荐智能体",
    "care": "员工关怀触发智能体",
    "hr": "人员流动预测智能体",
}

_lock = threading.Lock()
_token = None
_agent_ids = None  # name -> id 缓存


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
    except Exception as e:
        raise WeKnoraError("WeKnora 登录失败: %s" % e)


def _token_value():
    with _lock:
        t = _token
    if not t:
        _login()
        with _lock:
            t = _token
    return t


def call(method, path, body=None, timeout=60):
    """同步 JSON 调用（401 自动重登一次）。"""
    global _token
    token = _token_value()
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
            raise WeKnoraError("WeKnora %s %s -> %s" % (method, path, e.code))
        except Exception as e:
            raise WeKnoraError("WeKnora 请求异常: %s" % e)
    raise WeKnoraError("WeKnora 认证重试失败")


def agent_ids():
    """name -> agent id 映射（缓存）。"""
    global _agent_ids
    with _lock:
        cached = _agent_ids
    if cached:
        return cached
    d = call("GET", "/agents", timeout=20)
    data = d.get("data")
    if isinstance(data, dict):
        data = data.get("list") or []
    ids = {}
    for a in data or []:
        ids[a.get("name")] = a.get("id")
    with _lock:
        _agent_ids = ids
    return ids


def agent_id_for(module):
    name = AGENT_NAMES.get(module)
    if not name:
        raise WeKnoraError("未知模块: %s" % module)
    aid = agent_ids().get(name)
    if not aid:
        raise WeKnoraError("智能体未创建: %s" % name)
    return aid


def create_session(title="管理协同中心会话"):
    d = call("POST", "/sessions", {"title": title}, timeout=20)
    return (d.get("data") or d).get("id")


def iter_agent_chat(session_id, query, module):
    """SSE 流式问答生成器：yield ("delta", text) / ("refs", [doc]) / ("error", msg)。

    服务端持有账号，向模块对应的 WeKnora 智能体发起 RAG 会话。
    """
    aid = agent_id_for(module)
    token = _token_value()
    req = urllib.request.Request(BASE + "/agent-chat/" + session_id, method="POST",
                                 data=json.dumps({"query": query, "agent_id": aid,
                                                  "agent_enabled": True}).encode(),
                                 headers={"Authorization": "Bearer " + (token or ""),
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            for raw in r:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    d = json.loads(line[5:])
                except Exception:
                    continue
                rt = d.get("response_type")
                if rt == "answer":
                    yield "delta", d.get("content") or ""
                elif rt == "references":
                    docs = []
                    for ref in (d.get("data") or {}).get("references") or []:
                        name = ref.get("knowledge_name") or ref.get("file_name") or ref.get("name")
                        if name and name not in docs:
                            docs.append(name)
                    if docs:
                        yield "refs", docs
    except urllib.error.HTTPError as e:
        if e.code == 401:
            _login()
            yield from iter_agent_chat(session_id, query, module)
            return
        yield "error", "WeKnora 问答失败: HTTP %s" % e.code
    except Exception as e:
        yield "error", "WeKnora 问答异常: %s" % e


KB_TAG_RE = re.compile(r"<kb [^>]*/>")


def clean_inline_tags(text):
    return KB_TAG_RE.sub("", text)


def kb_overview():
    """知识库概览（含管理协同中心 KB 的文档清单）。"""
    d = call("GET", "/knowledge-bases", timeout=15)
    out = []
    for kb in d.get("data") or []:
        if kb.get("name") == KB_NAME:
            docs = []
            try:
                dd = call("GET", "/knowledge-bases/%s/knowledge?page=1&page_size=100" % kb["id"], timeout=20)
                items = dd.get("data") or []
                if isinstance(items, dict):
                    items = items.get("list") or []
                for it in items:
                    docs.append({
                        "id": it.get("id"),
                        "title": it.get("title") or it.get("file_name") or "",
                        "status": it.get("parse_status") or "",
                        "enabled": it.get("enable_status") == "enabled",
                        "size": it.get("file_size") or 0,
                        "updated_at": (it.get("updated_at") or "")[:10],
                    })
            except WeKnoraError:
                pass
            out.append({"id": kb["id"], "name": kb.get("name"),
                        "knowledge_count": kb.get("knowledge_count") or 0,
                        "chunk_count": kb.get("chunk_count") or 0,
                        "docs": docs})
    return out


def health():
    try:
        call("GET", "/models", timeout=10)
        return True
    except Exception:
        return False
