# -*- coding: utf-8 -*-
"""Agent Factory 单元测试（Epic 2）。不依赖宿主插件，直接导入 agent_factory。"""

import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_factory import (  # noqa: E402
    TOOL_CATALOG,
    build_agent_config,
    make_agent_row,
    new_agent_id,
    persist_bindings,
    reconcile_bindings,
    validate_agent_config,
)


SPEC = {
    "id": "business_analyst",
    "name": "经营分析数字员工",
    "position": "经营分析",
    "department": "管理层",
    "category": "analytics",
    "max_tokens": 12288,
    "execution_freq": 4,
    "auto_tasks": 2,
    "manual_tasks": 1,
    "success_rate": 0.97,
    "avg_response_ms": 2400,
    "skills": [("指标归因", "attribution"), ("报表生成", "report")],
    "tools": ["query_enterprise_orders"],
}


class TestAgentFactory(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE models (
                id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
                model_id TEXT, name TEXT, provider TEXT, base_model TEXT, context_window INTEGER,
                max_tokens INTEGER, input_price_per_k REAL, output_price_per_k REAL,
                enabled INTEGER, created_at TEXT
            );
            CREATE TABLE agent_tools (
                id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
                agent_id TEXT, tool_id TEXT, tool_name TEXT, tool_category TEXT,
                enabled INTEGER, created_at TEXT
            );
            CREATE TABLE agent_app_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
                agent_id TEXT, app_id TEXT, data_scope TEXT, kb_scope TEXT,
                enabled INTEGER, created_at TEXT
            );
            """
        )

    def test_build_config(self) -> None:
        cfg = build_agent_config(SPEC)
        self.assertEqual(cfg["agent_id"], "business_analyst")
        self.assertEqual(cfg["model_id"], "local-qwen2.5-72b")
        self.assertIn("business_analyst_attribution", [s["skill_id"] for s in cfg["skills"]])
        self.assertTrue(all(t["tool_id"] in TOOL_CATALOG for t in cfg["tools"]))
        self.assertIn("sales_center", cfg["apps"])

    def test_validate_ok(self) -> None:
        cfg = build_agent_config(SPEC)
        self.assertEqual(validate_agent_config(cfg), [])

    def test_validate_bad(self) -> None:
        cfg = build_agent_config(SPEC)
        cfg["success_rate"] = 1.5
        cfg["tools"] = [{"tool_id": "nope", "name": "x", "category": "x"}]
        errs = validate_agent_config(cfg)
        self.assertTrue(any("成功率" in e["message"] for e in errs))
        self.assertTrue(any("未在编目注册" in e["message"] for e in errs))

    def test_persist_bindings(self) -> None:
        res = persist_bindings(self.conn, "env_x", "t_x", "demo", SPEC, "2026-01-01 00:00:00")
        self.assertEqual(res["agent_id"], "business_analyst")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS c FROM models").fetchone()["c"], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS c FROM agent_tools").fetchone()["c"], 1)
        # 管理层可访问 4 个应用（finance/sales/data/project）
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS c FROM agent_app_access").fetchone()["c"], 4)
        # 幂等：同环境再写一次不新增模型
        persist_bindings(self.conn, "env_x", "t_x", "demo", SPEC, "2026-01-01 00:00:00")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS c FROM models").fetchone()["c"], 1)

    def test_reconcile(self) -> None:
        row = {
            "agent_id": "business_analyst",
            "tenant_id": "t_x",
            "name": "经营分析数字员工",
            "position": "经营分析",
            "department": "管理层",
            "model": "本地 Qwen2.5 7B",
            "max_tokens": 12288,
            "execution_freq": 4,
            "work_start": "09:00",
            "work_end": "18:00",
            "auto_tasks": 2,
            "manual_tasks": 1,
            "success_rate": 0.97,
            "avg_response_ms": 2400,
            "kb_scope": "enterprise",
            "data_scope": "enterprise",
            "skills": '["指标归因","报表生成"]',
            "tools": '["query_enterprise_orders"]',
        }
        res = reconcile_bindings(self.conn, "env_x", "demo", row)
        self.assertEqual(res["agent_id"], "business_analyst")
        self.assertGreaterEqual(self.conn.execute("SELECT COUNT(*) AS c FROM agent_tools").fetchone()["c"], 1)

    def test_make_agent_row(self) -> None:
        row, skills = make_agent_row("env_x", "t_x", "demo", SPEC, "2026-01-01 00:00:00")
        self.assertEqual(row["agent_id"], "business_analyst")
        self.assertEqual(len(skills), 2)

    def test_new_agent_id(self) -> None:
        self.assertTrue(new_agent_id("analyst").startswith("analyst_"))


if __name__ == "__main__":
    unittest.main()
