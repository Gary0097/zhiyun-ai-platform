# -*- coding: utf-8 -*-
"""zhiyun-auth 回归：品牌保存语义与最后管理员保护。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import auth_plugin as ap
    _HAS_DEPS = True
except Exception:  # CI 环境可能缺 fastapi/pydantic，此时优雅跳过（宿主环境全量执行）
    _HAS_DEPS = False

unittest_skip = unittest.skipUnless(_HAS_DEPS, "auth_plugin 依赖（fastapi/pydantic）不可用")


def _repoint(ap, tmp):
    """把模块的派生路径常量指到临时目录。"""
    ap.AUTH_DIR = Path(tmp) / "auth"
    ap.USERS_FILE = ap.AUTH_DIR / "users.json"
    ap.SECRET_FILE = ap.AUTH_DIR / "token_secret.txt"
    ap.BRANDING_DIR = Path(tmp) / "branding"
    ap.LOGIN_CONFIG_FILE = ap.BRANDING_DIR / "login-config.json"
    ap.CONFIG_FILE = Path(tmp) / "config.json"


@unittest_skip
class BrandingSemanticsTests(unittest.TestCase):
    def test_empty_background_keeps_existing_cover(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._repoint(tmp)
            (Path(tmp) / "branding").mkdir()
            (Path(tmp) / "branding" / "login-config.json").write_text(
                json.dumps({"brand_name": "B", "enterprise": "E", "background_data_url": "data:image/png;base64,OLD"}),
                encoding="utf-8",
            )
            req = ap.BrandingRequest(brand_name="B2", enterprise="E2", background_data_url="")
            import asyncio

            asyncio.run(ap.update_branding(req, authorization=self._admin_auth(tmp)))
            cfg = json.loads((Path(tmp) / "branding" / "login-config.json").read_text(encoding="utf-8"))
            self.assertEqual(cfg["background_data_url"], "data:image/png;base64,OLD")
            self.assertEqual(cfg["brand_name"], "B2")

    def _repoint(self, tmp):
        _repoint(ap, tmp)

    def _admin_auth(self, tmp):
        (Path(tmp) / "auth").mkdir(exist_ok=True)
        users = [{"username": "admin", "role": "admin", "active": True,
                  "password_hash": "", "password_salt": "", "display_name": "a",
                  "agent_id": "default", "data_scope": "enterprise", "kb_scope": "", "created_at": ""}]
        (Path(tmp) / "auth" / "users.json").write_text(json.dumps(users), encoding="utf-8")
        return "Bearer " + ap._create_token("admin")


@unittest_skip
class LastAdminGuardTests(unittest.TestCase):
    def test_cannot_demote_last_active_admin(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._repoint(tmp)
            (Path(tmp) / "auth").mkdir()
            users = [
                {"username": "admin", "role": "admin", "active": True, "display_name": "a",
                 "password_hash": "", "password_salt": "", "agent_id": "default",
                 "data_scope": "enterprise", "kb_scope": "", "created_at": ""},
                {"username": "m1", "role": "member", "active": True, "display_name": "m",
                 "password_hash": "", "password_salt": "", "agent_id": "default",
                 "data_scope": "enterprise", "kb_scope": "", "created_at": ""},
            ]
            (Path(tmp) / "auth" / "users.json").write_text(json.dumps(users), encoding="utf-8")
            req = ap.UserUpsertRequest(username="admin", password="", display_name="a", role="member",
                                       agent_id="default", data_scope="enterprise", kb_scope="", active=True)
            import asyncio

            with self.assertRaises(Exception) as ctx:
                asyncio.run(ap.upsert_user(req, authorization=self._admin_auth(tmp)))
            self.assertIn("最后一个", str(ctx.exception.detail) if hasattr(ctx.exception, "detail") else str(ctx.exception))

    def _repoint(self, tmp):
        _repoint(ap, tmp)

    def _admin_auth(self, tmp):
        return "Bearer " + ap._create_token("admin")


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# server-side RBAC hardening (issue-77): PBKDF2 / token / admin-guard / routes
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402
import base64  # noqa: E402
import hashlib  # noqa: E402
import hmac  # noqa: E402
import time  # noqa: E402


def _make_legacy_hash(password: str, salt: str) -> str:
    """模拟旧版 sha256(salt + password) 十六进制哈希。"""
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _make_expired_token(username: str) -> str:
    secret = ap._token_secret()
    payload = json.dumps({
        "sub": username,
        "iat": int(time.time()) - 120,
        "exp": int(time.time()) - 10,
    })
    b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    sig = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


@unittest_skip
class AuthPasswordTests(unittest.TestCase):
    """PBKDF2 与旧版 SHA256 密码校验。"""

    def test_pbkdf2_create_and_verify(self) -> None:
        pw_hash, salt = ap._hash_password("Secret#123")
        self.assertTrue(pw_hash.startswith(ap.PBKDF2_PREFIX))
        self.assertTrue(ap._verify_password("Secret#123", pw_hash, salt))
        self.assertFalse(ap._verify_password("wrong", pw_hash, salt))

    def test_pbkdf2_hash_is_not_legacy(self) -> None:
        pw_hash, _ = ap._hash_password("Secret#123")
        self.assertFalse(ap._is_legacy_hash(pw_hash))

    def test_pbkdf2_uses_random_salt(self) -> None:
        h1, salt1 = ap._hash_password("Secret#123")
        h2, salt2 = ap._hash_password("Secret#123")
        self.assertNotEqual(salt1, salt2)
        self.assertNotEqual(h1, h2)

    def test_legacy_sha256_verify_and_detect(self) -> None:
        legacy = _make_legacy_hash("OldPass1", "salt1234")
        self.assertTrue(ap._is_legacy_hash(legacy))
        self.assertTrue(ap._verify_password("OldPass1", legacy, "salt1234"))
        self.assertFalse(ap._verify_password("wrong", legacy, "salt1234"))

    def test_upgrade_password_for_user(self) -> None:
        username = "legacy_user"
        legacy = _make_legacy_hash("OldPass1", "salt1234")
        ap._save_users([{
            "username": username,
            "role": "member",
            "active": True,
            "password_hash": legacy,
            "password_salt": "salt1234",
        }])
        ap._upgrade_password_for_user(username, "OldPass1")
        user = ap._find_user(username)
        self.assertIsNotNone(user)
        self.assertFalse(ap._is_legacy_hash(user["password_hash"]))
        self.assertTrue(ap._verify_password("OldPass1", user["password_hash"], user["password_salt"]))


@unittest_skip
class AuthTokenTests(unittest.TestCase):
    """Token 生成、校验与 _bearer_token 解析。"""

    def setUp(self) -> None:
        ap._save_users([])

    def _add_user(self, username: str, role: str = "member",
                  active: bool = True, password: str = "pw123456") -> None:
        pw_hash, salt = ap._hash_password(password)
        users = ap._load_users()
        users.append({
            "username": username,
            "display_name": username,
            "role": role,
            "password_hash": pw_hash,
            "password_salt": salt,
            "active": active,
        })
        ap._save_users(users)

    def test_bearer_token_parsing(self) -> None:
        self.assertEqual(ap._bearer_token("Bearer abc"), "abc")
        self.assertEqual(ap._bearer_token("abc"), "")
        self.assertEqual(ap._bearer_token(""), "")

    def test_create_and_verify_token(self) -> None:
        self._add_user("alice")
        token = ap._create_token("alice")
        self.assertEqual(ap._verify_token(token), "alice")

    def test_tampered_signature_rejected(self) -> None:
        self._add_user("alice")
        token = ap._create_token("alice")
        flipped = "0" if token[-1] != "0" else "1"
        self.assertIsNone(ap._verify_token(token[:-1] + flipped))

    def test_malformed_token_rejected(self) -> None:
        self.assertIsNone(ap._verify_token("no-dot-here"))

    def test_unknown_user_rejected(self) -> None:
        self.assertIsNone(ap._verify_token(ap._create_token("ghost")))

    def test_inactive_user_rejected(self) -> None:
        self._add_user("bob", active=False)
        self.assertIsNone(ap._verify_token(ap._create_token("bob")))

    def test_expired_token_rejected(self) -> None:
        self._add_user("carol")
        self.assertIsNone(ap._verify_token(_make_expired_token("carol")))


@unittest_skip
class AuthAdminGuardTests(unittest.TestCase):
    """_require_admin 路由保护。"""

    def setUp(self) -> None:
        ap._save_users([])
        ap._ensure_admin()

    def _add_member(self, username: str = "member1") -> str:
        pw_hash, salt = ap._hash_password("pw123456")
        users = ap._load_users()
        users.append({
            "username": username,
            "display_name": username,
            "role": "member",
            "password_hash": pw_hash,
            "password_salt": salt,
            "active": True,
        })
        ap._save_users(users)
        return ap._create_token(username)

    def test_require_admin_no_token_returns_401(self) -> None:
        with self.assertRaises(ap.HTTPException) as ctx:
            ap._require_admin("")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_require_admin_member_returns_403(self) -> None:
        token = self._add_member()
        with self.assertRaises(ap.HTTPException) as ctx:
            ap._require_admin("Bearer " + token)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_require_admin_returns_username(self) -> None:
        token = ap._create_token("admin")
        self.assertEqual(ap._require_admin("Bearer " + token), "admin")


@unittest_skip
class AuthRoutesTests(unittest.TestCase):
    """login / me / list_users 异步路由。"""

    def setUp(self) -> None:
        ap._save_users([])
        ap._ensure_admin()

    def _run(self, coro):
        return asyncio.run(coro)

    def test_login_success(self) -> None:
        resp = self._run(ap.login(ap.LoginRequest(username="admin", password=ap.DEFAULT_ADMIN_PASSWORD)))
        self.assertTrue(resp["token"])
        self.assertEqual(resp["user"]["role"], "admin")

    def test_login_wrong_password_returns_401(self) -> None:
        with self.assertRaises(ap.HTTPException) as ctx:
            self._run(ap.login(ap.LoginRequest(username="admin", password="wrong")))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_login_unknown_user_returns_401(self) -> None:
        with self.assertRaises(ap.HTTPException) as ctx:
            self._run(ap.login(ap.LoginRequest(username="nobody", password="wrong")))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_me_requires_token(self) -> None:
        with self.assertRaises(ap.HTTPException) as ctx:
            self._run(ap.me(""))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_me_with_valid_token(self) -> None:
        token = self._run(ap.login(ap.LoginRequest(
            username="admin", password=ap.DEFAULT_ADMIN_PASSWORD)))["token"]
        resp = self._run(ap.me(authorization="Bearer " + token))
        self.assertEqual(resp["user"]["role"], "admin")

    def test_list_users_requires_admin(self) -> None:
        with self.assertRaises(ap.HTTPException) as ctx:
            self._run(ap.list_users(""))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_list_users_member_forbidden(self) -> None:
        pw_hash, salt = ap._hash_password("pw123456")
        users = ap._load_users()
        users.append({
            "username": "member1",
            "display_name": "member1",
            "role": "member",
            "password_hash": pw_hash,
            "password_salt": salt,
            "active": True,
        })
        ap._save_users(users)
        token = ap._create_token("member1")
        with self.assertRaises(ap.HTTPException) as ctx:
            self._run(ap.list_users(authorization="Bearer " + token))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_list_users_admin_ok(self) -> None:
        token = self._run(ap.login(ap.LoginRequest(
            username="admin", password=ap.DEFAULT_ADMIN_PASSWORD)))["token"]
        resp = self._run(ap.list_users(authorization="Bearer " + token))
        self.assertEqual(resp["current"], "admin")
        self.assertGreaterEqual(len(resp["users"]), 1)


if __name__ == "__main__":
    unittest.main()