# -*- coding: utf-8 -*-
"""企业记录数据域/知识域隔离与跨环境隔离单元测试。

覆盖 PR review 修复的两个回归点：

* Bug C（跨环境隔离）：非管理员通过 ``/records/{entity}`` 查询时，服务端必须
  强制使用其账号所属企业环境，即使客户端显式传入其他 env_id 也不得泄露数据。
* Bug D（知识域与数据域独立判定）：用户 ``data_scope=enterprise`` 但
  ``kb_scope=department`` 时，知识库类实体（files/data_sources）必须仍按
  部门过滤，而业务实体（org_users）不受 kb_scope 影响。

本插件依赖 fastapi/pydantic 与宿主 qwenpaw 运行时，发布门禁的全局 Python
（缺少 anyio）无法导入，请使用 QwenPaw venv Python 运行。
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import enterprise_plugin as ep  # noqa: E402


def _mint_token(username: str, secret: str) -> str:
    """构造与 enterprise_plugin._verify_token 兼容的 Bearer token。"""
    payload = {"sub": username, "exp": int(time.time()) + 7200}
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    sig = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


class RecordsScopingTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_base = Path(tempfile.mkdtemp(prefix="zi_scoping_"))

    def setUp(self):
        # 每个用例独立临时目录与数据库，避免跨用例污染
        self.tmp = Path(tempfile.mkdtemp(prefix="zi_scoping_db_"))
        ep.DB = self.tmp / "enterprise.db"
        ep.ENTERPRISE_DIR = self.tmp
        ep.AUTH_USERS_FILE = self.tmp / "users.json"
        ep.AUTH_SECRET_FILE = self.tmp / "token_secret.txt"
        ep._schema_lock = False
        ep._ensure_schema()
        # 固定 token secret，便于构造校验 token
        ep.AUTH_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        ep.AUTH_SECRET_FILE.write_text("test-secret", encoding="utf-8")

    def tearDown(self):
        ep._schema_lock = False

    def _write_users(self, users: list[dict]) -> None:
        ep._write_json(ep.AUTH_USERS_FILE, users)

    def _insert(self, sql: str, args: tuple) -> None:
        conn = ep._connect()
        try:
            conn.execute(sql, args)
            conn.commit()
        finally:
            conn.close()


class TestCrossEnvIsolation(RecordsScopingTestBase):
    """Bug C：非管理员 /records 查询必须被强制限定在账号所属企业环境。"""

    def test_non_admin_records_forced_to_own_env(self):
        for env in ("envA", "envB"):
            self._insert(
                "INSERT INTO org_users (env_id, data_mode, username, department, role, data_scope, kb_scope, active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                (env, "demo", f"user_{env}", "研发部", "member", "enterprise", "enterprise"),
            )
            self._insert(
                "INSERT INTO sessions (env_id, data_mode, session_id, user_id, messages, status) "
                "VALUES (?, ?, ?, ?, 2, 'active')",
                (env, "demo", f"session_{env}", f"user_{env}"),
            )

        # userA 属于 envA
        user_a = {
            "username": "user_envA",
            "role": "member",
            "env_id": "envA",
            "data_mode": "demo",
            "active": True,
        }
        self._write_users([user_a])
        token = _mint_token("user_envA", "test-secret")

        # 客户端恶意请求 envB，但非管理员应被强制回账号所属 envA
        result = asyncio.run(ep.records(
            entity="org_users",
            authorization=f"Bearer {token}",
            limit=100,
            offset=0,
            data_mode="demo",
            env_id="envB",
            start_date="",
            end_date="",
        ))
        self.assertEqual(result["env_id"], "envA", "非管理员环境必须被强制为账号所属环境")
        self.assertEqual(result["data_mode"], "demo")
        rows = result["rows"]
        self.assertTrue(rows, "应返回本环境 org_users")
        for row in rows:
            self.assertEqual(row["env_id"], "envA", "不得泄露其他环境数据")
        self.assertNotIn("user_envB", [r["username"] for r in rows])

        # sessions 同样隔离
        sess = asyncio.run(ep.records(
            entity="sessions",
            authorization=f"Bearer {token}",
            limit=100,
            offset=0,
            data_mode="demo",
            env_id="envB",
            start_date="",
            end_date="",
        ))
        self.assertEqual(sess["env_id"], "envA")
        session_ids = [r["session_id"] for r in sess["rows"]]
        self.assertIn("session_envA", session_ids)
        self.assertNotIn("session_envB", session_ids, "不得泄露其他环境会话")

    def test_admin_can_query_any_env(self):
        self._write_users([{"username": "admin1", "role": "admin", "active": True}])
        token = _mint_token("admin1", "test-secret")
        for env in ("envA", "envB"):
            self._insert(
                "INSERT INTO org_users (env_id, data_mode, username, department, role, data_scope, kb_scope, active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                (env, "demo", f"user_{env}", "研发部", "member", "enterprise", "enterprise"),
            )
        # 管理员保留客户端传入的 env_id=envB
        result = asyncio.run(ep.records(
            entity="org_users",
            authorization=f"Bearer {token}",
            limit=100,
            offset=0,
            data_mode="demo",
            env_id="envB",
            start_date="",
            end_date="",
        ))
        self.assertEqual(result["env_id"], "envB")
        self.assertEqual([r["username"] for r in result["rows"]], ["user_envB"])


class TestKbScopeDepartment(RecordsScopingTestBase):
    """Bug D：kb_scope=department 与 data_scope=enterprise 独立判定。"""

    def _seed_dept_data(self, env: str = "envX"):
        self._insert(
            "INSERT INTO org_users (env_id, data_mode, username, department, role, data_scope, kb_scope, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (env, "demo", "user_rd", "研发部", "member", "enterprise", "department"),
        )
        self._insert(
            "INSERT INTO org_users (env_id, data_mode, username, department, role, data_scope, kb_scope, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (env, "demo", "user_prod", "生产部", "member", "enterprise", "enterprise"),
        )
        self._insert(
            "INSERT INTO agents (env_id, data_mode, agent_id, department, name, enabled) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (env, "demo", "agent_rd", "研发部", "研发助理"),
        )
        self._insert(
            "INSERT INTO agents (env_id, data_mode, agent_id, department, name, enabled) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (env, "demo", "agent_prod", "生产部", "生产助理"),
        )
        self._insert(
            "INSERT INTO apps (env_id, data_mode, app_id, agent_id, name, enabled) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (env, "demo", "app_rd", "agent_rd", "研发中心"),
        )
        self._insert(
            "INSERT INTO apps (env_id, data_mode, app_id, agent_id, name, enabled) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (env, "demo", "app_prod", "agent_prod", "生产中心"),
        )
        self._insert(
            "INSERT INTO data_sources (env_id, data_mode, source_id, app_id, records, shared) "
            "VALUES (?, ?, ?, ?, 10, 0)",
            (env, "demo", "ds_rd", "app_rd"),
        )
        self._insert(
            "INSERT INTO data_sources (env_id, data_mode, source_id, app_id, records, shared) "
            "VALUES (?, ?, ?, ?, 20, 0)",
            (env, "demo", "ds_prod", "app_prod"),
        )
        self._insert(
            "INSERT INTO files (env_id, data_mode, file_id, agent_id, user_id, app_id, name) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (env, "demo", "f_rd", "agent_rd", "user_rd", "app_rd", "研发需求.docx"),
        )
        self._insert(
            "INSERT INTO files (env_id, data_mode, file_id, agent_id, user_id, app_id, name) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (env, "demo", "f_prod", "agent_prod", "user_prod", "app_prod", "生产排程.xlsx"),
        )

    def test_kb_scope_department_filters_kb_entities(self):
        env = "envX"
        self._seed_dept_data(env)
        user = {"username": "user_rd", "role": "member", "data_scope": "enterprise", "kb_scope": "department"}

        # 知识域=部门，files 只返回研发部
        files = ep._records("files", 100, 0, env_id=env, data_mode="demo", user=user)
        file_names = [r["name"] for r in files]
        self.assertIn("研发需求.docx", file_names)
        self.assertNotIn("生产排程.xlsx", file_names, "知识域=部门时应排除其他部门文件")

        # data_sources 同样按部门
        sources = ep._records("data_sources", 100, 0, env_id=env, data_mode="demo", user=user)
        src_apps = [r["app_id"] for r in sources]
        self.assertIn("app_rd", src_apps)
        self.assertNotIn("app_prod", src_apps, "知识域=部门时应排除其他部门数据源")

    def test_org_users_not_restricted_by_kb_scope(self):
        env = "envX"
        self._seed_dept_data(env)
        user = {"username": "user_rd", "role": "member", "data_scope": "enterprise", "kb_scope": "department"}
        # 业务实体 org_users 受 data_scope=enterprise 控制 => 返回全部环境用户
        users = ep._records("org_users", 100, 0, env_id=env, data_mode="demo", user=user)
        unames = [r["username"] for r in users]
        self.assertIn("user_rd", unames)
        self.assertIn("user_prod", unames, "数据域=企业时 org_users 不应被知识域部门限制")


if __name__ == "__main__":
    unittest.main()
