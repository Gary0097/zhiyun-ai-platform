# -*- coding: utf-8 -*-
"""QwenPaw Creator 原版 · 平台统一鉴权守卫（纯标准库）。

与 zhiyun-auth / Creator 视频压缩版同源的本地 HMAC Token 校验；
密钥类端点要求有效登录且为管理员。为避免共享 sys.path 上的模块名冲突，
本文件使用唯一命名（studio_auth_guard）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from fastapi import Header, HTTPException


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


def _verify_token_user(authorization: str) -> dict | None:
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not token:
        return None
    try:
        secret = _auth_dir_file("auth", "token_secret.txt").read_text(encoding="utf-8").strip()
        if not secret:
            return None
        b64, sig = token.split(".", 1)
        expected = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(b64.encode("ascii")))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        username = str(payload.get("sub") or "")
        users = json.loads(_auth_dir_file("auth", "users.json").read_text(encoding="utf-8"))
        user = next((u for u in users if u.get("username") == username), None)
        if not user or not user.get("active", True):
            return None
        return user
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def require_studio_admin(authorization: str = Header(default="")) -> dict:
    user = _verify_token_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录或凭证已过期")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅系统管理员可访问密钥配置")
    return user
