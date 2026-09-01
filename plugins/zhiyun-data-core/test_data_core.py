# -*- coding: utf-8 -*-
"""Data Core behavioral tests with an isolated SQLite database."""

import tempfile
import io
import unittest
from pathlib import Path

from data_core import DataCore, DataCoreError


class DataCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.core = DataCore(Path(self.temp.name) / "data-core.sqlite")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_default_order_schema_exists(self) -> None:
        schema = self.core.list_schema("orders")
        self.assertIn("order_no", [field["name"] for field in schema["fields"]])

    def test_default_production_template_exists(self) -> None:
        schema = self.core.list_schema("production")
        self.assertEqual(schema["label"], "生产日报")
        self.assertEqual([field["name"] for field in schema["fields"]], ["record_date", "department", "output", "labor_hours", "employee_count", "cost", "loss"])

    def test_entity_overview_reflects_real_and_simulated_records(self) -> None:
        row = {"order_no": "REAL-1", "customer_name": "客户", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50}
        self.core.import_rows("orders", [row])
        self.core.generate_orders(3, seed=9)
        overview = self.core.list_entities()[0]
        self.assertEqual(overview["entity"], "orders")
        self.assertEqual(overview["record_count"], 4)
        self.assertEqual(overview["real_count"], 1)
        self.assertEqual(overview["simulated_count"], 3)

    def test_user_can_add_rename_and_disable_field(self) -> None:
        self.core.add_field("orders", "sales_region", "销售区域")
        schema = self.core.update_field("orders", "sales_region", label="所属区域", active=False)
        field = next(item for item in schema["fields"] if item["name"] == "sales_region")
        self.assertEqual(field["label"], "所属区域")
        self.assertFalse(field["active"])

    def test_user_can_create_department_dataset_and_import_rows(self) -> None:
        schema = self.core.create_schema("work_logs", "车间工时", [
            {"name": "work_date", "label": "日期", "field_type": "date", "required": True},
            {"name": "department", "label": "部门", "field_type": "text", "required": True},
            {"name": "output", "label": "产量", "field_type": "number"},
            {"name": "labor_hours", "label": "工时", "field_type": "number"},
        ])
        self.assertEqual(schema["entity"], "work_logs")
        self.core.import_rows("work_logs", [{"work_date": "2026-08-22", "department": "一车间", "output": 120, "labor_hours": 24}])
        self.assertEqual(self.core.list_records("work_logs")[0]["data"]["output"], 120)

    def test_duplicate_or_unsafe_dataset_is_rejected(self) -> None:
        with self.assertRaises(DataCoreError):
            self.core.create_schema("DROP TABLE", "危险", [{"name": "value", "label": "值"}])
        self.core.create_schema("finance", "财务", [{"name": "amount", "label": "金额", "field_type": "number"}])
        with self.assertRaisesRegex(DataCoreError, "already exists"):
            self.core.create_schema("finance", "财务", [{"name": "amount", "label": "金额"}])

    def test_invalid_field_identifier_is_rejected(self) -> None:
        with self.assertRaises(DataCoreError):
            self.core.add_field("orders", "DROP TABLE", "危险字段")

    def test_import_preview_reports_row_errors(self) -> None:
        preview = self.core.preview_import(
            "orders",
            [{"order_no": "A-1", "customer_name": "客户", "product_name": "电机", "quantity": "abc", "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50}],
        )
        self.assertEqual(preview["error_count"], 1)
        self.assertIn("quantity must be integer", preview["errors"][0]["errors"])

    def test_real_import_is_traceable_and_reversible(self) -> None:
        row = {"order_no": "A-1", "customer_name": "客户", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50}
        batch = self.core.import_rows("orders", [row], source_name="orders.xlsx")
        records = self.core.list_records("orders")
        self.assertEqual(records[0]["source_type"], "real")
        self.assertEqual(records[0]["batch_id"], batch["batch_id"])
        rollback = self.core.rollback_batch(batch["batch_id"])
        self.assertEqual(rollback["deleted_records"], 1)
        self.assertEqual(self.core.list_records("orders"), [])

    def test_simulation_is_deterministic_and_does_not_touch_real_data(self) -> None:
        real = {"order_no": "REAL-1", "customer_name": "客户", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50}
        self.core.import_rows("orders", [real])
        simulated = self.core.generate_orders(4, seed=7)
        self.assertEqual(len(self.core.list_records("orders", source_type="simulated")), 4)
        self.core.rollback_batch(simulated["batch_id"])
        remaining = self.core.list_records("orders")
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["data"]["order_no"], "REAL-1")

    def test_production_simulation_is_reversible(self) -> None:
        batch = self.core.generate_production(12, seed=17)
        records = self.core.list_records("production", source_type="simulated")
        self.assertEqual(len(records), 12)
        self.assertIn(records[0]["data"]["department"], ["机加工一部", "装配一部", "表面处理", "质量检验"])
        self.core.rollback_batch(batch["batch_id"])
        self.assertEqual(self.core.list_records("production"), [])

    def test_agent_search_filters_orders_without_sql(self) -> None:
        rows = [
            {"order_no": "A-1", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50},
            {"order_no": "B-1", "customer_name": "星联科技", "product_name": "传感器", "quantity": 20, "order_date": "2026-08-02", "promised_date": "2026-08-22", "status": "已完成", "progress": 100},
        ]
        self.core.import_rows("orders", rows)
        result = self.core.search_records("orders", keyword="海川", filters={"status": "生产中"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["data"]["order_no"], "A-1")

    def test_agent_search_rejects_unknown_filter(self) -> None:
        with self.assertRaisesRegex(DataCoreError, "unknown filter fields"):
            self.core.search_records("orders", filters={"sql": "DROP TABLE"})

    def test_order_dashboard_query_can_filter_real_records(self) -> None:
        rows = [
            {"order_no": "REAL-OPEN", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50},
            {"order_no": "REAL-DONE", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "已完成", "progress": 100},
        ]
        self.core.import_rows("orders", rows)
        self.core.generate_orders(2, seed=12)

        result = self.core.search_records(
            "orders",
            keyword="海川",
            filters={"status": "生产中"},
            source_type="real",
            limit=200,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_type"], "real")
        self.assertEqual(result[0]["data"]["order_no"], "REAL-OPEN")
        self.assertEqual(result[0]["data"]["progress"], 50)

    def test_order_dashboard_query_has_a_hard_result_limit(self) -> None:
        self.core.generate_orders(220, seed=31)
        result = self.core.search_records("orders", limit=1000)
        self.assertEqual(len(result), 200)

    def test_demo_and_production_environments_are_isolated(self) -> None:
        real = {"order_no": "PROD-1", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50}
        self.core.import_rows("orders", [real])  # real import lands in production env by default
        self.core.generate_orders(3, seed=9)  # simulation lands in demo env by default

        # Isolated views: each environment only sees its own records.
        self.assertEqual(len(self.core.list_records("orders", data_mode="production")), 1)
        self.assertEqual(len(self.core.list_records("orders", data_mode="demo")), 3)
        self.assertEqual(len(self.core.list_records("orders", data_mode="production", source_type="real")), 1)
        self.assertEqual(len(self.core.list_records("orders", data_mode="demo", source_type="real")), 0)

        # Overview carries per-environment counts even when listing both.
        overview = self.core.list_entities()[0]
        self.assertEqual(overview["record_count"], 4)
        self.assertEqual(overview["demo_count"], 3)
        self.assertEqual(overview["production_count"], 1)

        # Batches are segmented by environment too.
        prod_batches = self.core.list_batches("orders", data_mode="production")
        self.assertEqual(len(prod_batches), 1)
        self.assertEqual(prod_batches[0]["data_mode"], "production")

# ---------------------------------------------------------------------------
# App-Dock 应用接入默认智能体（与 zhiyun-app-discovery 同源）安全护栏测试
# ---------------------------------------------------------------------------
try:
    import data_core_plugin as dcp

    _HAS_PLUGIN = True
except ImportError as _e:  # pragma: no cover - 依赖缺失环境
    dcp = None
    _HAS_PLUGIN = False


@unittest.skipUnless(_HAS_PLUGIN, "data_core_plugin 依赖（fastapi/httpx/qwenpaw）不可用")
class DataCoreChatBoundTests(unittest.TestCase):
    """校验 AgentChatRequest 对 context/history 的长度约束与截断逻辑。"""

    def test_context_too_long_rejected(self) -> None:
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            dcp.AgentChatRequest(text="hi", context="x" * 8001)

    def test_context_at_limit_accepted(self) -> None:
        req = dcp.AgentChatRequest(text="hi", context="x" * 8000)
        self.assertEqual(len(req.context), 8000)

    def test_history_too_many_turns_rejected(self) -> None:
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            dcp.AgentChatRequest(text="hi", history=[{"role": "user", "text": "hi"}] * 25)

    def test_history_at_limit_accepted(self) -> None:
        req = dcp.AgentChatRequest(text="hi", history=[{"role": "user", "text": "hi"}] * 24)
        self.assertEqual(len(req.history), 24)

    def test_normal_payload_validates(self) -> None:
        req = dcp.AgentChatRequest(
            text="hi",
            context="系统上下文",
            history=[{"role": "user", "text": "上一轮问题"}, {"role": "assistant", "text": "上一轮回答"}],
        )
        self.assertEqual(req.app_id, "zhiyun-data-core")

    def test_build_input_truncates_history_text(self) -> None:
        req = dcp.AgentChatRequest(
            text="现在的问题",
            context="系统上下文",
            history=[{"role": "user", "text": "x" * 9000}],
        )
        messages = dcp._build_input(req)
        self.assertEqual(len(messages), 3)
        user_payloads = [m for m in messages if m["role"] == "user"]
        self.assertLessEqual(
            len(user_payloads[0]["content"][0]["text"]), 4000,
            "历史单轮文本必须被截断到 4000 以内",
        )
        self.assertEqual(user_payloads[1]["content"][0]["text"], "现在的问题")


@unittest.skipUnless(_HAS_PLUGIN, "data_core_plugin 依赖（fastapi/httpx/qwenpaw）不可用")
class DataCoreAppAccessTests(unittest.TestCase):
    """校验应用访问授权：非管理员必须拥有 agent_app_access，管理员可绕过。"""

    def setUp(self):
        if not _HAS_PLUGIN:
            return
        self.tmp = Path(tempfile.mkdtemp(prefix="zi_data_core_access_"))
        self._orig = (
            dcp.ENTERPRISE_DIR, dcp.ENTERPRISE_DB,
            dcp.AUTH_USERS_FILE, dcp.AUTH_SECRET_FILE, dcp.CONFIG_FILE,
        )
        dcp.ENTERPRISE_DIR = self.tmp
        dcp.ENTERPRISE_DB = self.tmp / "enterprise.db"
        dcp.AUTH_USERS_FILE = self.tmp / "users.json"
        dcp.AUTH_SECRET_FILE = self.tmp / "token_secret.txt"
        dcp.CONFIG_FILE = self.tmp / "config.json"
        conn = dcp._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS org_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    env_id TEXT, tenant_id TEXT, data_mode TEXT,
                    username TEXT, display_name TEXT, email TEXT, phone TEXT, department TEXT,
                    role TEXT, title TEXT, agent_id TEXT, data_scope TEXT, kb_scope TEXT,
                    active INTEGER, dormant INTEGER, hired_on TEXT, created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_app_access (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    env_id TEXT, tenant_id TEXT, data_mode TEXT,
                    agent_id TEXT, app_id TEXT, data_scope TEXT, kb_scope TEXT,
                    enabled INTEGER, created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS apps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id TEXT, env_id TEXT, data_mode TEXT,
                    agent_id TEXT, enabled INTEGER, created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS enterprise_meta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    env_id TEXT, data_mode TEXT, enterprise TEXT
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        if not _HAS_PLUGIN:
            return
        (dcp.ENTERPRISE_DIR, dcp.ENTERPRISE_DB,
         dcp.AUTH_USERS_FILE, dcp.AUTH_SECRET_FILE, dcp.CONFIG_FILE) = self._orig

    def _insert(self, sql: str, args: tuple) -> None:
        conn = dcp._connect()
        try:
            conn.execute(sql, args)
            conn.commit()
        finally:
            conn.close()

    def _seed_user(self, username: str, role: str = "member", agent_id: str | None = "agent_a",
                   env_id: str = "envX") -> None:
        self._insert(
            "INSERT INTO org_users (env_id, data_mode, username, role, agent_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (env_id, "demo", username, role, agent_id),
        )

    def test_no_agent_binding_raises_403(self):
        from fastapi import HTTPException
        self._seed_user("alice", role="member", agent_id=None)
        user = {"username": "alice", "role": "member"}
        with self.assertRaises(HTTPException) as ctx:
            dcp._require_app_access(user, "envX", "demo", "app_1")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_no_access_row_raises_403(self):
        from fastapi import HTTPException
        self._seed_user("bob", role="member", agent_id="agent_a")
        user = {"username": "bob", "role": "member"}
        with self.assertRaises(HTTPException) as ctx:
            dcp._require_app_access(user, "envX", "demo", "app_1")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_disabled_access_row_raises_403(self):
        from fastapi import HTTPException
        self._seed_user("carol", role="member", agent_id="agent_a")
        self._insert(
            "INSERT INTO agent_app_access (env_id, data_mode, agent_id, app_id, enabled) "
            "VALUES (?, ?, ?, ?, ?)",
            ("envX", "demo", "agent_a", "app_1", 0),
        )
        user = {"username": "carol", "role": "member"}
        with self.assertRaises(HTTPException) as ctx:
            dcp._require_app_access(user, "envX", "demo", "app_1")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_wrong_env_no_access_raises_403(self):
        from fastapi import HTTPException
        self._seed_user("dave", role="member", agent_id="agent_a", env_id="envX")
        self._insert(
            "INSERT INTO agent_app_access (env_id, data_mode, agent_id, app_id, enabled) "
            "VALUES (?, ?, ?, ?, ?)",
            ("envY", "demo", "agent_a", "app_1", 1),
        )
        user = {"username": "dave", "role": "member"}
        with self.assertRaises(HTTPException) as ctx:
            dcp._require_app_access(user, "envX", "demo", "app_1")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_valid_access_row_passes(self):
        self._seed_user("eve", role="member", agent_id="agent_a")
        self._insert(
            "INSERT INTO agent_app_access (env_id, data_mode, agent_id, app_id, enabled) "
            "VALUES (?, ?, ?, ?, ?)",
            ("envX", "demo", "agent_a", "app_1", 1),
        )
        user = {"username": "eve", "role": "member"}
        dcp._require_app_access(user, "envX", "demo", "app_1")

    def test_admin_bypasses_access(self):
        self._seed_user("admin", role="admin", agent_id=None)
        user = {"username": "admin", "role": "admin"}
        dcp._require_app_access(user, "envX", "demo", "app_1")

    def test_admin_without_fixed_env_uses_latest_enterprise_environment(self):
        self._insert(
            "INSERT INTO enterprise_meta (env_id, data_mode, enterprise) VALUES (?, ?, ?)",
            ("env_latest", "demo", "另一企业"),
        )
        self.assertEqual(
            dcp._user_env({"username": "admin", "role": "admin", "enterprise": "旧企业"}),
            ("env_latest", "demo"),
        )

    def test_member_without_matching_enterprise_never_uses_admin_fallback(self):
        self._insert(
            "INSERT INTO enterprise_meta (env_id, data_mode, enterprise) VALUES (?, ?, ?)",
            ("env_other", "demo", "另一企业"),
        )
        self.assertEqual(
            dcp._user_env({"username": "member", "role": "member", "enterprise": "未知企业"}),
            ("", ""),
        )

    def test_lookup_app_agent_returns_bound_agent(self):
        self._insert(
            "INSERT INTO apps (app_id, env_id, data_mode, agent_id, enabled) "
            "VALUES (?, ?, ?, ?, ?)",
            ("app_1", "envX", "demo", "agent_a", 1),
        )
        self.assertEqual(dcp._lookup_app_agent("app_1", "envX", "demo"), "agent_a")

    def test_lookup_app_agent_returns_none_for_disabled(self):
        self._insert(
            "INSERT INTO apps (app_id, env_id, data_mode, agent_id, enabled) "
            "VALUES (?, ?, ?, ?, ?)",
            ("app_1", "envX", "demo", "agent_a", 0),
        )
        self.assertIsNone(dcp._lookup_app_agent("app_1", "envX", "demo"))

    def test_lookup_app_agent_returns_none_for_wrong_env(self):
        self._insert(
            "INSERT INTO apps (app_id, env_id, data_mode, agent_id, enabled) "
            "VALUES (?, ?, ?, ?, ?)",
            ("app_1", "envY", "demo", "agent_a", 1),
        )
        self.assertIsNone(dcp._lookup_app_agent("app_1", "envX", "demo"))



class DataCoreRouteGuardTests(unittest.TestCase):
    """路由分层鉴权（PRD §15/§17.16）：需要 fastapi，缺失时整组跳过（CI 兼容）。"""

    def setUp(self):
        try:
            import data_core_plugin as dcp
        except Exception:
            raise unittest.SkipTest("data_core_plugin 依赖（fastapi/httpx/qwenpaw）不可用")
        self.dcp = dcp

    def test_guarded_route_counts(self):
        import re
        src = io.open(Path(__file__).parent / "data_core_plugin.py", encoding="utf-8").read()
        self.assertEqual(len(re.findall(r"Depends\(require_admin\)", src)), 8)
        self.assertEqual(len(re.findall(r"Depends\(require_auth\)", src)), 12)

    def test_require_admin_rejects_member(self):
        from fastapi import HTTPException
        dcp = self.dcp
        dcp._find_user = lambda username: {"username": username, "role": "member", "active": True}
        with self.assertRaises(HTTPException) as ctx:
            dcp.require_admin("Bearer bad-token")
        self.assertEqual(ctx.exception.status_code, 401)



class DepartmentScopingTests(unittest.TestCase):
    """记录级部门数据范围（PRD 21.2/§15）：v4 迁移、导入盖章、读取过滤。"""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.core = DataCore(Path(self.temp.name) / "data-core.sqlite")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_v4_migration_and_department_filter(self):
        import tempfile
        from data_core import DataCore
        with tempfile.TemporaryDirectory() as tmp:
            core = DataCore(Path(tmp) / "dc.sqlite")
            core.create_schema("dept_t", "部门验收", [
                {"name": "order_no", "label": "订单号", "field_type": "text", "required": True}])
            core.import_rows("dept_t", [{"order_no": "D1"}], source_name="s1", owner_department="销售部")
            core.import_rows("dept_t", [{"order_no": "D2"}], source_name="s2", owner_department="财务部")
            core.import_rows("dept_t", [{"order_no": "D3"}], source_name="s3")
            sales = [r["data"]["order_no"] for r in core.list_records("dept_t", owner_department="销售部")]
            self.assertEqual(sales, ["D1"])
            all_rows = [r["data"]["order_no"] for r in core.list_records("dept_t")]
            self.assertEqual(sorted(all_rows), ["D1", "D2", "D3"])
            self.assertEqual(len(core.list_batches("dept_t", owner_department="销售部")), 1)
            self.assertEqual(len(core.list_batches("dept_t")), 3)
            with core.connect() as conn:
                version = conn.execute("SELECT value FROM data_core_meta WHERE key = 'schema_version'").fetchone()["value"]
            self.assertEqual(int(version), 5)



    def test_backfill_only_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = DataCore(Path(tmp) / "dc.sqlite")
            core.create_schema("bf_t", "补盖", [{"name": "order_no", "label": "订单号", "field_type": "text", "required": True}])
            core.import_rows("bf_t", [{"order_no": "B1"}], source_name="x")            # 空戳
            core.import_rows("bf_t", [{"order_no": "B2"}], source_name="y", owner_department="财务部")
            updated = core.backfill_department("bf_t", "销售部")
            self.assertEqual(updated, 1)
            got = {r["data"]["order_no"]: r for r in core.list_records("bf_t", limit=10)}
            self.assertEqual(len(core.list_records("bf_t", owner_department="销售部")), 1)
            self.assertEqual(len(core.list_records("bf_t", owner_department="财务部")), 1)
            # 二次补盖不重复影响
            self.assertEqual(core.backfill_department("bf_t", "销售部"), 0)



    def test_agent_scope_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = DataCore(Path(tmp) / "dc.sqlite")
            core.create_schema("ag_t", "智能体范围", [{"name": "order_no", "label": "订单号", "field_type": "text", "required": True}])
            core.import_rows("ag_t", [{"order_no": "A1"}], source_name="a", owner_agent="default")
            core.import_rows("ag_t", [{"order_no": "A2"}], source_name="b", owner_agent="business_analyst")
            mine = [r["data"]["order_no"] for r in core.list_records("ag_t", owner_agent="default")]
            self.assertEqual(mine, ["A1"])
            self.assertEqual(len(core.list_records("ag_t")), 2)
            self.assertEqual(len(core.list_batches("ag_t", owner_agent="business_analyst")), 1)



    def test_preview_import_reports_duplicate_rows(self) -> None:
        rows = [
            {"order_no": "DUP-1", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50},
            {"order_no": "DUP-1", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50},
        ]
        preview = self.core.preview_import("orders", rows)
        self.assertEqual(preview["duplicate_count"], 2)
        self.assertEqual(len(preview["duplicate_rows"]), 2)

    def test_cross_batch_duplicate_key_is_detected_against_existing_records(self) -> None:
        row = {"order_no": "PROD-2", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50}
        self.core.import_rows("orders", [row], data_mode="production")
        duplicate = {"order_no": "PROD-2", "customer_name": "星联科技", "product_name": "伺服电机", "quantity": 5, "order_date": "2026-08-05", "promised_date": "2026-08-25", "status": "待排产", "progress": 0}
        preview = self.core.preview_import("orders", [duplicate], data_mode="production")
        self.assertEqual(preview["duplicate_count"], 1)
        self.assertEqual(preview["duplicate_rows"][0]["fields"]["order_no"], "PROD-2")
        self.assertTrue(preview["duplicate_rows"][0]["existing"])
        with self.assertRaisesRegex(DataCoreError, "duplicate"):
            self.core.import_rows("orders", [duplicate], data_mode="production")

    def test_duplicate_rows_block_commit(self) -> None:
        rows = [
            {"order_no": "DUP-2", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50},
            {"order_no": "DUP-2", "customer_name": "星联科技", "product_name": "伺服电机", "quantity": 5, "order_date": "2026-08-05", "promised_date": "2026-08-25", "status": "待排产", "progress": 0},
        ]
        preview = self.core.preview_import("orders", rows, data_mode="production")
        self.assertEqual(preview["duplicate_count"], 2)
        with self.assertRaisesRegex(DataCoreError, "duplicate"):
            self.core.import_rows("orders", rows, data_mode="production")

    def test_duplicate_key_across_environments_is_isolated(self) -> None:
        prod = {"order_no": "SHARED-1", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50}
        self.core.import_rows("orders", [prod], data_mode="production")
        demo = {"order_no": "SHARED-1", "customer_name": "星联科技", "product_name": "伺服电机", "quantity": 5, "order_date": "2026-08-05", "promised_date": "2026-08-25", "status": "待排产", "progress": 0}
        preview = self.core.preview_import("orders", [demo], data_mode="demo")
        self.assertEqual(preview["duplicate_count"], 0)
        batch = self.core.import_rows("orders", [demo], data_mode="demo")
        self.assertEqual(batch["data_mode"], "demo")

    def test_export_respects_data_mode_isolation(self) -> None:
        real = {"order_no": "PROD-1", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50}
        self.core.import_rows("orders", [real])  # real import lands in production by default
        self.core.generate_orders(3, seed=9)     # simulation lands in demo by default
        data, media_type, suggested = self.core.export_records("orders", format="csv", data_mode="production")
        self.assertEqual(media_type, "text/csv; charset=utf-8")
        self.assertEqual(suggested, "orders.csv")
        text = data.decode("utf-8-sig")
        self.assertIn("PROD-1", text)
        self.assertNotIn("SIM-", text)
        demo_data, _, _ = self.core.export_records("orders", format="csv", data_mode="demo")
        demo_text = demo_data.decode("utf-8-sig")
        self.assertNotIn("PROD-1", demo_text)
        self.assertIn("SIM-", demo_text)

    def test_export_respects_source_type_filter(self) -> None:
        real = {"order_no": "REAL-1", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50}
        self.core.import_rows("orders", [real])
        self.core.generate_orders(3, seed=11)
        data, _, _ = self.core.export_records("orders", format="csv", data_mode="production", source_type="real")
        text = data.decode("utf-8-sig")
        self.assertIn("REAL-1", text)
        self.assertNotIn("SIM-", text)

    def test_export_rejects_invalid_format(self) -> None:
        with self.assertRaisesRegex(DataCoreError, "xlsx"):
            self.core.export_records("orders", format="json")

if __name__ == "__main__":
    unittest.main()
