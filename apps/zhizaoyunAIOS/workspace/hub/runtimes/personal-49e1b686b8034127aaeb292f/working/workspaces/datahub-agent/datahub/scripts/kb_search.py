#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金汉隆-数据中枢 知识库检索脚本：登录 -> 建会话 -> 绑定知识库 -> 提问 -> 汇总SSE答案"""
import argparse
import json
import os
import sys
import time
import urllib.request

BASE = os.environ.get("WEKNORA_BASE", "http://127.0.0.1:18000")
EMAIL = "jinhanlong@qq.com"
PASSWORD = "jinhanlong@2025."
DEFAULT_KB = "4a945ef5-5157-41ca-b6f2-79fa1452f382"  # 金汉隆-数据中枢
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
    last = None
    for i in range(3):
        try:
            r = post_json(BASE + "/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
            if r.get("success"):
                return r["token"]
            last = r
        except Exception as e:
            last = e
        time.sleep(2)
    raise RuntimeError("登录失败: %s" % last)


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
    ap = argparse.ArgumentParser(description="金汉隆-数据中枢 知识库问数")
    ap.add_argument("query", help="要询问知识库的问题")
    ap.add_argument("--kb", default=DEFAULT_KB, help="知识库ID，多个用逗号分隔")
    args = ap.parse_args()

    kb_ids = [x.strip() for x in args.kb.split(",") if x.strip()]
    last_err = None
    for attempt in range(1, 4):
        try:
            token = login()
            sid = create_session(token, kb_ids)
            answer, refs = ask(token, sid, args.query)
            print(answer.strip())
            if refs:
                print("\n\n参考来源: " + "；".join(dict.fromkeys(refs)))
            return
        except Exception as e:
            last_err = e
            # 429 限流（向量化排队）时退避重试
            if "rate" in str(e).lower() or "429" in str(e):
                time.sleep(10 * attempt)
                continue
            break
    print("知识库问数失败: %s" % last_err, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
