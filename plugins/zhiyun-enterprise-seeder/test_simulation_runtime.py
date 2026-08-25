# -*- coding: utf-8 -*-
"""Simulation Runtime 单元测试（Epic 3）。不依赖宿主插件，直接导入 simulation_runtime。"""

import os
import sqlite3
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulation_runtime import (  # noqa: E402
    ensure_schema,
    build_day_events,
    execute_day_events,
    preview_interval,
    run_interval,
    list_events,
    _stable_day_seed,
)

ENV_ID = "env_unit_test"
TENANT_ID = "unit_tenant"
MODE = "demo"


def _schema() -> str:
    return """
    CREATE TABLE enterprise_meta (
        id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
        enterprise TEXT, template TEXT, start_date TEXT, end_date TEXT, scale INTEGER,
        departments INTEGER, agent_count INTEGER, activity TEXT, created_at TEXT, updated_at TEXT
    );
    CREATE TABLE org_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
        username TEXT, display_name TEXT, department TEXT, role TEXT, title TEXT,
        agent_id TEXT, data_scope TEXT, kb_scope TEXT, active INTEGER, dormant INTEGER,
        hired_on TEXT, created_at TEXT
    );
    CREATE TABLE agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
        agent_id TEXT, name TEXT, position TEXT, department TEXT, system_prompt TEXT,
        model TEXT, skills TEXT, tools TEXT, kb_scope TEXT, data_scope TEXT, max_tokens INTEGER,
        execution_freq INTEGER, work_start TEXT, work_end TEXT, auto_tasks INTEGER,
        manual_tasks INTEGER, success_rate REAL, avg_response_ms INTEGER, enabled INTEGER,
        created_at TEXT
    );
    CREATE TABLE skills (
        id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
        agent_id TEXT, skill_id TEXT, name TEXT, category TEXT, description TEXT,
        enabled INTEGER, created_at TEXT
    );
    CREATE TABLE agent_tools (
        id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
        agent_id TEXT, tool_id TEXT, tool_name TEXT, tool_category TEXT, enabled INTEGER,
        created_at TEXT
    );
    CREATE TABLE apps (
        id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
        app_id TEXT, name TEXT, category TEXT, agent_id TEXT, icon TEXT, enabled INTEGER,
        created_at TEXT
    );
    CREATE TABLE sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
        session_id TEXT, user_id TEXT, agent_id TEXT, app_id TEXT, messages INTEGER,
        started_at TEXT, ended_at TEXT, status TEXT, created_at TEXT
    );
    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
        task_id TEXT, session_id TEXT, agent_id TEXT, user_id TEXT, app_id TEXT, skill_id TEXT,
        label TEXT, status TEXT, success INTEGER, started_at TEXT, finished_at TEXT,
        latency_ms INTEGER, tokens INTEGER, result TEXT, created_at TEXT
    );
    CREATE TABLE files (
        id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
        file_id TEXT, task_id TEXT, session_id TEXT, agent_id TEXT, user_id TEXT, app_id TEXT,
        name TEXT, category TEXT, format TEXT, size_kb INTEGER, download_count INTEGER,
        downloaded INTEGER, created_at TEXT
    );
    CREATE TABLE file_downloads (
        id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
        download_id TEXT, file_id TEXT, task_id TEXT, user_id TEXT, agent_id TEXT, app_id TEXT,
        downloaded_at TEXT, ip TEXT, device TEXT, created_at TEXT
    );
    CREATE TABLE token_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
        day TEXT, agent_id TEXT, app_id TEXT, user_id TEXT, tokens INTEGER, calls INTEGER,
        success INTEGER, failed INTEGER, created_at TEXT
    );
    CREATE TABLE login_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
        day TEXT, user_id TEXT, agent_id TEXT, app_id TEXT, login_at TEXT, ip TEXT,
        device TEXT, success INTEGER, status TEXT, created_at TEXT
    );
    CREATE TABLE operation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
        day TEXT, user_id TEXT, agent_id TEXT, app_id TEXT, action TEXT, detail TEXT,
        level TEXT, created_at TEXT
    );
    """


class TestSimulationRuntime(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_schema())
        ensure_schema(self.conn)
        self.conn.execute(
            "INSERT INTO enterprise_meta (env_id, tenant_id, data_mode, enterprise, template, start_date, end_date, scale, departments, agent_count, activity, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ENV_ID, TENANT_ID, MODE, "单元测试企业", "manufacturing", "2026-01-01", "2026-01-10",
             20, 3, 2, "medium", "2026-01-01 09:00:00", "2026-01-10 18:00:00"),
        )
        self.conn.execute(
            "INSERT INTO agents (env_id, tenant_id, data_mode, agent_id, name, position, department, system_prompt, model, skills, tools, kb_scope, data_scope, max_tokens, execution_freq, work_start, work_end, auto_tasks, manual_tasks, success_rate, avg_response_ms, enabled, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ENV_ID, TENANT_ID, MODE, "sales_quote", "销售报价", "销售报价", "销售部", "p", "本地 Qwen", "[]", "[]",
             "enterprise", "enterprise", 8192, 8, "09:00", "18:00", 2, 2, 0.94, 1800, 1, "2026-01-01 09:00:00"),
        )
        self.conn.execute(
            "INSERT INTO skills (env_id, tenant_id, data_mode, agent_id, skill_id, name, category, description, enabled, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ENV_ID, TENANT_ID, MODE, "sales_quote", "sales_quote_quote", "报价测算", "sales", "d", 1, "2026-01-01 09:00:00"),
        )
        self.conn.execute(
            "INSERT INTO agent_tools (env_id, tenant_id, data_mode, agent_id, tool_id, tool_name, tool_category, enabled, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (ENV_ID, TENANT_ID, MODE, "sales_quote", "query_enterprise_orders", "订单查询", "data", 1, "2026-01-01 09:00:00"),
        )
        for app in [("zhiyun-data-core", "统一数据中心", "系统"), ("zhiyun-sales-studio", "智能销售中心", "业务")]:
            self.conn.execute(
                "INSERT INTO apps (env_id, tenant_id, data_mode, app_id, name, category, agent_id, icon, enabled, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ENV_ID, TENANT_ID, MODE, app[0], app[1], app[2], "sales_quote", "🗄️", 1, "2026-01-01 09:00:00"),
            )
        for i in range(8):
            self.conn.execute(
                "INSERT INTO org_users (env_id, tenant_id, data_mode, username, display_name, department, role, title, agent_id, data_scope, kb_scope, active, dormant, hired_on, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ENV_ID, TENANT_ID, MODE, f"user{i:02d}", f"用户{i:02d}", "销售部", "member", "销售", "sales_quote",
                 "department", "department", 1, 0, "2025-12-01", "2025-12-01 09:00:00"),
            )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def _count(self, table: str) -> int:
        return self.conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]

    def test_stable_seed_deterministic(self) -> None:
        a = _stable_day_seed(42, 3, ENV_ID, date(2026, 1, 5))
        b = _stable_day_seed(42, 3, ENV_ID, date(2026, 1, 5))
        c = _stable_day_seed(42, 3, ENV_ID, date(2026, 1, 6))
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_build_day_events_plan(self) -> None:
        rng = _rng(1)
        ctx = _load_ctx(self.conn)
        plan = build_day_events(date(2026, 1, 5), ctx["active_users"], ctx["enabled_agents"], ctx["agents_by_id"],
                                ctx["dept_apps"], ctx["apps_by_id"], ENV_ID, TENANT_ID, MODE, 1.0, rng)
        self.assertEqual(plan["day"], "2026-01-05")
        self.assertGreater(plan["stats"]["sessions"], 0)
        ev_types = {ev["type"] for ev in plan["events"]}
        self.assertIn("session", ev_types)
        self.assertIn("task", ev_types)
        # 计划应携带登录与操作日志，形成完整行为链路。
        self.assertIn("logins", plan)
        self.assertIn("operations", plan)
        self.assertGreater(len(plan.get("logins", [])), 0)
        # 构建计划不写库
        self.assertEqual(self._count("sessions"), 0)
        self.assertEqual(self._count("business_events"), 0)

    def test_preview_does_not_write(self) -> None:
        before_s = self._count("sessions")
        before_e = self._count("business_events")
        res = preview_interval(self.conn, ENV_ID, MODE, "2026-01-01", "2026-01-06", "medium", 1)
        self.assertTrue(res["ok"])
        self.assertIn("summary", res)
        self.assertEqual(self._count("sessions"), before_s)
        self.assertEqual(self._count("business_events"), before_e)

    def test_run_writes_and_skips(self) -> None:
        res = run_interval(self.conn, ENV_ID, MODE, "2026-01-01", "2026-01-06", seed=1)
        self.assertTrue(res["ok"])
        self.assertGreater(res["days_written"], 0)
        self.assertGreater(self._count("sessions"), 0)
        self.assertGreater(self._count("tasks"), 0)
        self.assertGreater(self._count("business_events"), 0)
        self.assertGreater(self._count("login_activity"), 0)
        self.assertGreater(self._count("operation_logs"), 0)
        ev = list_events(self.conn, ENV_ID, MODE, "2026-01-01", "2026-01-06", 10)
        self.assertGreater(len(ev), 0)
        self.assertEqual(ev[0]["env_id"], ENV_ID)
        # 再次运行（不强制）应全部跳过
        res2 = run_interval(self.conn, ENV_ID, MODE, "2026-01-01", "2026-01-06", seed=1)
        self.assertEqual(res2["days_written"], 0)
        self.assertGreater(res2["days_skipped"], 0)

    def test_run_force_replaces_without_duplicates(self) -> None:
        res = run_interval(self.conn, ENV_ID, MODE, "2026-01-01", "2026-01-04", seed=5)
        self.assertGreater(res["days_written"], 0)
        s1 = self._count("sessions")
        e1 = self._count("business_events")
        # 强制重跑应清表重建，而不是在既有数据上再插一遍。
        res2 = run_interval(self.conn, ENV_ID, MODE, "2026-01-01", "2026-01-04", seed=5, force=True)
        self.assertEqual(self._count("sessions"), s1)
        self.assertEqual(self._count("business_events"), e1)
        self.assertEqual(res2["days_written"], res["days_written"])
        # 再次强制应幂等。
        run_interval(self.conn, ENV_ID, MODE, "2026-01-01", "2026-01-04", seed=5, force=True)
        self.assertEqual(self._count("sessions"), s1)
        self.assertEqual(self._count("business_events"), e1)

    def test_execute_day_matches_stats(self) -> None:
        rng = _rng(7)
        ctx = _load_ctx(self.conn)
        plan = build_day_events(date(2026, 1, 7), ctx["active_users"], ctx["enabled_agents"], ctx["agents_by_id"],
                                ctx["dept_apps"], ctx["apps_by_id"], ENV_ID, TENANT_ID, MODE, 1.0, rng)
        stats = execute_day_events(self.conn, plan)
        self.assertEqual(stats["sessions"], self._count("sessions"))
        self.assertEqual(stats["calls"], self._count("tasks"))
        self.assertEqual(stats["tokens"], sum(r["tokens"] for r in self.conn.execute("SELECT tokens FROM token_usage")))
        self.assertGreater(self._count("login_activity"), 0)

    def test_business_events_token_not_double_counted(self) -> None:
        rng = _rng(11)
        ctx = _load_ctx(self.conn)
        plan = build_day_events(date(2026, 1, 8), ctx["active_users"], ctx["enabled_agents"], ctx["agents_by_id"],
                                ctx["dept_apps"], ctx["apps_by_id"], ENV_ID, TENANT_ID, MODE, 1.0, rng)
        stats = execute_day_events(self.conn, plan)
        self.assertGreater(stats["tokens"], 0)

        def one(sql: str) -> int:
            return int(self.conn.execute(sql).fetchone()[0])

        all_bus = one("SELECT COALESCE(SUM(tokens),0) FROM business_events")
        task_bus = one("SELECT COALESCE(SUM(tokens),0) FROM business_events WHERE event_type='task'")
        token_usage = one("SELECT COALESCE(SUM(tokens),0) FROM token_usage")
        task_tokens = one("SELECT COALESCE(SUM(tokens),0) FROM tasks")
        # 审计 Token 只以任务级记一次；session/file/download 事件不重复记 Token。
        self.assertEqual(all_bus, task_bus)
        self.assertEqual(task_bus, token_usage)
        self.assertEqual(task_bus, task_tokens)


def _rng(seed: int):
    import random
    return random.Random(seed)


def _load_ctx(conn):
    """在给定连接上通过公开 API 构造当日上下文（模拟 _generate_enterprise 的输入形状）。"""
    import simulation_runtime as sr
    rng = _rng(1)
    return sr._load_day_context(conn, ENV_ID, MODE, 1.0, 20, rng)


if __name__ == "__main__":
    unittest.main()
