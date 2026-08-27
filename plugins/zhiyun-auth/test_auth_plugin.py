# -*- coding: utf-8 -*-
"""zhiyun-auth 回归：品牌保存语义与最后管理员保护。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import auth_plugin as ap


def _repoint(ap, tmp):
    """把模块的派生路径常量指到临时目录。"""
    ap.AUTH_DIR = Path(tmp) / "auth"
    ap.USERS_FILE = ap.AUTH_DIR / "users.json"
    ap.SECRET_FILE = ap.AUTH_DIR / "token_secret.txt"
    ap.BRANDING_DIR = Path(tmp) / "branding"
    ap.LOGIN_CONFIG_FILE = ap.BRANDING_DIR / "login-config.json"
    ap.CONFIG_FILE = Path(tmp) / "config.json"


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
