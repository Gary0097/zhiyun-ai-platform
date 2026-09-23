#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金汉隆-智能采购 知识库检索脚本：登录 -> 按名称解析知识库 -> 建会话 -> 提问 -> 汇总SSE答案"""
import argparse
import json
import os
import sys
import time
import urllib.request

BASE = os.environ.get("WEKNORA_BASE", "http://127.0.0.1:18000")
EMAIL = os.environ.get("WEKNORA_EMAIL", "jinhanlong@qq.com")
PASSWORD = os.environ.get("WEKNORA_PASSWORD", "jinhanlong@2025.")
KB_NAME = os.environ.get("WEKNORA_KB_NAME", "金汉隆-智能采购")
SUMMARY_MODEL_ID = "a15af007-e7a6-410d-ace1-1cdb22eb8d9b"  # 内部问数模型


def req_json(url, body=None, token=None, method=None, timeout=30):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def login():
    last = None
    for _ in range(3):
        try:
            r = req_json(BASE + "/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
            if r.get("success"):
                return r["token"]
            last = r
        except Exception as e:
            last = e
        time.sleep(2)
    raise RuntimeError("登录失败: %s" % last)


def resolve_kb(token):
    r = req_json(BASE + "/api/v1/knowledge-bases", token=token)
    for kb in r.get("data") or []:
        if kb.get("name") == KB_NAME:
            return kb["id"]
    raise RuntimeError("未找到知识库《%s》，请先创建" % KB_NAME)


def create_session(token, kb_ids):
    body = {"agent_config": {"enabled": True, "max_iterations": 5, "temperature": 0.7,
                             "knowledge_bases": kb_ids, "knowledge_ids": [], "allowed_tools": []}}
    r = req_json(BASE + "/api/v1/sessions", body, token)
    return r["data"]["id"]


def ask(token, session_id, query):
    body = {"query": query, "agent_enabled": False, "agent_id": "builtin-quick-answer",
            "web_search_enabled": False, "summary_model_id": SUMMARY_MODEL_ID, "channel": "web"}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + "/api/v1/knowledge-chat/" + session_id, data=data,
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
                                 method="POST")
    answer_parts, refs = [], []
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
    return "".join(answer_parts), refs


def main():
    ap = argparse.ArgumentParser(description="金汉隆-智能采购 知识库问数")
    ap.add_argument("query", help="要询问知识库的问题")
    ap.add_argument("--kb-name", default=KB_NAME, help="知识库名称")
    args = ap.parse_args()

    last_err = None
    for attempt in range(1, 4):
        try:
            token = login()
            kb_id = resolve_kb(token)
            sid = create_session(token, [kb_id])
            answer, refs = ask(token, sid, args.query)
            print(answer.strip())
            if refs:
                print("\n\n参考来源: " + "；".join(dict.fromkeys(refs)))
            return
        except Exception as e:
            last_err = e
            if "rate" in str(e).lower() or "429" in str(e):
                time.sleep(10 * attempt)
                continue
            break
    print("知识库问数失败: %s" % last_err, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
