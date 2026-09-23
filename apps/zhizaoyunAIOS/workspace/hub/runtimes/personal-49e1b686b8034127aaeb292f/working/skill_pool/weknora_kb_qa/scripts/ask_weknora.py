#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智造云知识库(WeKnora)问数脚本：登录 -> 建会话 -> 绑定知识库 -> 提问 -> 汇总SSE答案"""
import argparse
import json
import os
import sys
import urllib.request

BASE = os.environ.get("WEKNORA_BASE", "http://127.0.0.1:18000")
EMAIL = "jinhanlong@qq.com"
PASSWORD = "jinhanlong@2025."
DEFAULT_KB = "b861158f-4b89-4715-bada-01d4bed1e40b"  # 通用产品知识库
SUMMARY_MODEL_ID = "a15af007-e7a6-410d-ace1-1cdb22eb8d9b"  # 内部问数模型


def post_json(url, body, token=None, timeout=30):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def login():
    r = post_json(BASE + "/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    if not r.get("success"):
        raise RuntimeError("登录失败: " + json.dumps(r, ensure_ascii=False)[:300])
    return r["token"]


def create_session(token, kb_ids):
    body = {
        "agent_config": {
            "enabled": True,
            "max_iterations": 5,
            "temperature": 0.7,
            "knowledge_bases": kb_ids,
            "knowledge_ids": [],
            "allowed_tools": [],
        }
    }
    r = post_json(BASE + "/api/v1/sessions", body, token)
    return r["data"]["id"]


def ask(token, session_id, query):
    body = {
        "query": query,
        "agent_enabled": False,
        "agent_id": "builtin-quick-answer",
        "web_search_enabled": False,
        "summary_model_id": SUMMARY_MODEL_ID,
        "channel": "web",
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/v1/knowledge-chat/" + session_id,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST",
    )
    answer_parts, refs, done = [], [], False
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            try:
                evt = json.loads(line[5:])
            except json.JSONDecodeError:
                continue
            rt = evt.get("response_type")
            if rt == "answer":
                answer_parts.append(evt.get("content", ""))
            elif rt == "reference" and evt.get("data"):
                d = evt["data"]
                name = d.get("knowledge_name") or d.get("file_name") or ""
                if name:
                    refs.append(name)
            if evt.get("done") and rt not in ("answer",):
                pass
    return "".join(answer_parts), refs


def main():
    ap = argparse.ArgumentParser(description="智造云知识库问数")
    ap.add_argument("query", help="要询问知识库的问题")
    ap.add_argument("--kb", default=DEFAULT_KB, help="知识库ID，多个用逗号分隔")
    args = ap.parse_args()

    kb_ids = [x.strip() for x in args.kb.split(",") if x.strip()]
    try:
        token = login()
        sid = create_session(token, kb_ids)
        answer, refs = ask(token, sid, args.query)
    except Exception as e:
        print("知识库问数失败: %s" % e, file=sys.stderr)
        sys.exit(1)

    print(answer.strip())
    if refs:
        print("\n\n参考来源: " + "；".join(dict.fromkeys(refs)))


if __name__ == "__main__":
    main()
