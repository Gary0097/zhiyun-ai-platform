# -*- coding: utf-8 -*-
"""zhiyun-data-core 插件 RBAC 鉴权单元测试。

该文件由 verify-release.mjs 门禁通过 unittest discover 执行。
data_core_plugin 不提供密码哈希/用户写入辅助函数，因此这里直接写 users.json
并手工构造与插件一致的 HMAC-SHA256 签名 token。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest

# 必须在导入 data_core_plugin 之前设置环境变量，因为模块级常量在导入时计算。
_TMP = tempfile.mkdtemp(prefix="zhiyun-data-core-rbac-")
os.environ["ZHIYUN_DATA_CORE_DIR"] = _TMP
os.environ["QWENPAW_WORKING_DIR"] = _TMP

import data_core_plugin as dp  # noqa: E402


def _write_users(users: list[dict]) -> None:
    """向 USERS_FILE 写入用户列表，若不存在则创建 auth 目录。"""
    dp.AUTH_DIR.mkdir(parents=True, exist_ok=True)
    dp.USERS_FILE.write_text(json.dumps(users, ensure_ascii=False), encoding="utf-8")


def _sign_token(username: str, *, exp: int | None = None, ttl: int = 3600) -> str:
    """用与插件一致的算法生成签名 token。"""
    secret = dp._token_secret()
    if exp is None:
        exp = int(time.time()) + ttl
    payload = json.dumps({"sub": username, "iat": int(time.time()), "exp": exp})
    b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    sig = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def _user(username: str, *, role: str = "admin", active: bool = True) -> dict:
    return {
        "username": username,
        "display_name": username,
        "role": role,
        "password_hash": "unused",
        "password_salt": "unused",
        "active": active,
    }


class RbacHelperTests(unittest.TestCase):
    """_bearer_token / _verify_token / _require_auth 单元测试。"""

    def test_bearer_token_parsing(self) -> None:
        self.assertEqual(dp._bearer_token("Bearer abc"), "abc")
        self.assertEqual(dp._bearer_token("abc"), "")
        self.assertEqual(dp._bearer_token(""), "")

    def test_verify_valid_token(self) -> None:
        _write_users([_user("alice")])
        token = _sign_token("alice")
        self.assertEqual(dp._verify_token(token), "alice")

    def test_verify_tampered_signature_rejected(self) -> None:
        _write_users([_user("alice")])
        token = _sign_token("alice")
        flipped = "0" if token[-1] != "0" else "1"
        self.assertIsNone(dp._verify_token(token[:-1] + flipped))

    def test_verify_malformed_token_rejected(self) -> None:
        self.assertIsNone(dp._verify_token("no-dot-here"))

    def test_verify_unknown_user_rejected(self) -> None:
        _write_users([_user("alice")])
        token = _sign_token("ghost")
        self.assertIsNone(dp._verify_token(token))

    def test_verify_inactive_user_rejected(self) -> None:
        _write_users([_user("bob", active=False)])
        token = _sign_token("bob")
        self.assertIsNone(dp._verify_token(token))

    def test_verify_expired_token_rejected(self) -> None:
        _write_users([_user("carol")])
        token = _sign_token("carol", exp=int(time.time()) - 10)
        self.assertIsNone(dp._verify_token(token))

    def test_require_auth_no_token_returns_401(self) -> None:
        with self.assertRaises(dp.HTTPException) as ctx:
            dp._require_auth("")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_require_auth_with_valid_token_returns_username(self) -> None:
        _write_users([_user("alice")])
        token = _sign_token("alice")
        self.assertEqual(dp._require_auth("Bearer " + token), "alice")


class RbacRouteTests(unittest.TestCase):
    """受保护路由拒绝无 token 请求，健康路由保持公开。"""

    def _write_active_user(self) -> str:
        _write_users([_user("alice")])
        return _sign_token("alice")

    def test_health_stays_public(self) -> None:
        resp = asyncio.run(dp.health())
        self.assertEqual(resp.get("version"), "0.8.0")

    def test_backups_rejects_without_token(self) -> None:
        with self.assertRaises(dp.HTTPException) as ctx:
            asyncio.run(dp.backups())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_backups_accepts_with_token(self) -> None:
        token = self._write_active_user()
        resp = asyncio.run(dp.backups(authorization="Bearer " + token))
        self.assertIn("backups", resp)

    def test_context_rejects_without_token(self) -> None:
        with self.assertRaises(dp.HTTPException) as ctx:
            asyncio.run(dp.read_context())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_context_accepts_with_token(self) -> None:
        token = self._write_active_user()
        resp = asyncio.run(dp.read_context(authorization="Bearer " + token))
        self.assertIn("context", resp)

    def test_entities_rejects_without_token(self) -> None:
        with self.assertRaises(dp.HTTPException) as ctx:
            asyncio.run(dp.entities())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_entities_accepts_with_token(self) -> None:
        token = self._write_active_user()
        resp = asyncio.run(dp.entities(authorization="Bearer " + token))
        self.assertIn("entities", resp)


if __name__ == "__main__":
    unittest.main()
