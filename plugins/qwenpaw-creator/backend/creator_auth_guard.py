# -*- coding: utf-8 -*-
"""统一登录鉴权守卫（纯标准库，可独立测试）：与 zhiyun-auth 相同的 HMAC Token 本地校验。

与各 Studio 的 auth_guard 同源：读取 QWENPAW_WORKING_DIR/auth 下的
token_secret.txt 与 users.json，本地校验 Bearer Token，不发起网络请求。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path


def _auth_dir_file(*parts: str) -> Path:
    env = os.environ.get("QWENPAW_WORKING_DIR", "")
    if env:
        base = Path(env)
    else:
        try:
            from qwenpaw.constant import WORKING_DIR
            base = Path(WORKING_DIR)
        except Exception:  # noqa: BLE001
            base = Path.cwd()
    return base.joinpath(*parts)


def _token_secret() -> str:
    secret_file = _auth_dir_file("auth", "token_secret.txt")
    try:
        if secret_file.is_file():
            val = secret_file.read_text(encoding="utf-8").strip()
            if val:
                return val
    except OSError:
        pass
    return ""


def _load_user(username: str) -> dict | None:
    users_file = _auth_dir_file("auth", "users.json")
    try:
        users = json.loads(users_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    user = next((u for u in users if u.get("username") == username), None)
    if not user or not user.get("active", True):
        return None
    return user


def verify_token_user(authorization: str) -> dict | None:
    """校验 ``Authorization: Bearer <token>``，返回用户 dict；失败返回 None。"""
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not token:
        return None
    secret = _token_secret()
    if not secret:
        return None
    try:
        b64, sig = token.split(".", 1)
        expected = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(b64.encode("ascii")))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        username = str(payload.get("sub") or "")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return _load_user(username)
