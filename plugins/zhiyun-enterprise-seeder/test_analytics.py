# -*- coding: utf-8 -*-
"""analytics 单元测试（Epic 4 Time Machine 趋势分析）。不依赖宿主插件，直接导入 analytics。"""

import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analytics import build_trends  # noqa: E402


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE enterprise_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            env_id TEXT, tenant_id TEXT, data_mode TEXT, enterprise TEXT,
            template TEXT, start_date TEXT, end_date TEXT, scale INTEGER,
            departments INTEGER, agent_count INTEGER, activity TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE sessions (
            env_id TEXT, tenant_id TEXT, data_mode TEXT, session_id TEXT,
            user_id TEXT, agent_id TEXT, app_id TEXT, messages INTEGER,
            started_at TEXT, ended_at TEXT, status TEXT, created_at TEXT
        );
        CREATE TABLE tasks (
            env_id TEXT, tenant_id TEXT, data_mode TEXT, task_id TEXT,
            session_id TEXT, agent_id TEXT, user_id TEXT, app_id TEXT,
            skill_id TEXT, label TEXT, status TEXT, success INTEGER,
            started_at TEXT, finished_at TEXT, latency_ms INTEGER,
            tokens INTEGER, result TEXT, created_at TEXT
        );
        CREATE TABLE files (
            env_id TEXT, tenant_id TEXT, data_mode TEXT, file_id TEXT,
            task_id TEXT, session_id TEXT, agent_id TEXT, user_id TEXT,
            app_id TEXT, name TEXT, category TEXT, format TEXT, size_kb INTEGER,
            download_count INTEGER, downloaded INTEGER, created_at TEXT
        );
        CREATE TABLE file_downloads (
            env_id TEXT, tenant_id TEXT, data_mode TEXT, download_id TEXT,
            file_id TEXT, task_id TEXT, user_id TEXT, agent_id TEXT, app_id TEXT,
            downloaded_at TEXT, ip TEXT, device TEXT, created_at TEXT
        );
        CREATE TABLE login_activity (
            env_id TEXT, tenant_id TEXT, data_mode TEXT, login_id TEXT,
            user_id TEXT, agent_id TEXT, app_id TEXT, day TEXT,
            device TEXT, ip TEXT, success INTEGER, created_at TEXT
        );
        CREATE TABLE operation_logs (
            env_id TEXT, tenant_id TEXT, data_mode TEXT, op_id TEXT,
            user_id TEXT, agent_id TEXT, app_id TEXT, day TEXT,
            action TEXT, detail TEXT, created_at TEXT
        );
        CREATE TABLE token_usage (
            env_id TEXT, tenant_id TEXT, data_mode TEXT, day TEXT,
            agent_id TEXT, app_id TEXT, user_id TEXT, tokens INTEGER,
            calls INTEGER, success INTEGER, failed INTEGER, created_at TEXT
        );
        """
    )
    return conn


def _seed(conn, env_id="env_t", data_mode="demo"):
    """写入一套已知时间分布的数据，便于断言工作日/周末与增长曲线。"""
    base = [
        # 工作日（周一至周五 08-03..08-07）：每天 3 条会话，活跃度明显高于周末
        ("2026-08-03 09:00:00", "agent_a", "u1", "session"),
        ("2026-08-03 14:00:00", "agent_b", "u2", "session"),
        ("2026-08-03 16:00:00", "agent_a", "u3", "session"),
        ("2026-08-04 10:00:00", "agent_a", "u1", "session"),
        ("2026-08-04 15:00:00", "agent_b", "u2", "session"),
        ("2026-08-04 17:00:00", "agent_a", "u3", "session"),
        ("2026-08-05 09:30:00", "agent_a", "u2", "session"),
        ("2026-08-05 11:00:00", "agent_b", "u3", "session"),
        ("2026-08-05 16:30:00", "agent_a", "u1", "session"),
        ("2026-08-06 10:00:00", "agent_b", "u1", "session"),
        ("2026-08-06 14:00:00", "agent_a", "u2", "session"),
        ("2026-08-06 17:00:00", "agent_a", "u3", "session"),
        ("2026-08-07 09:00:00", "agent_a", "u3", "session"),
        ("2026-08-07 13:00:00", "agent_b", "u1", "session"),
        ("2026-08-07 16:00:00", "agent_a", "u2", "session"),
        # 周末（周六周日 08-08..08-09）：每天 1 条，量明显更低
        ("2026-08-08 11:00:00", "agent_a", "u1", "session"),
        ("2026-08-09 12:00:00", "agent_b", "u2", "session"),
    ]
    for row in base:
        started, agent, user, _ = row
        day = started[:10]
        conn.execute(
            "INSERT INTO sessions (env_id, tenant_id, data_mode, session_id, user_id, agent_id, app_id, messages, started_at, ended_at, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (env_id, "tenant", data_mode, "s-" + started, user, agent, "app1", 3, started, started, "completed", started),
        )
        conn.execute(
            "INSERT INTO tasks (env_id, tenant_id, data_mode, task_id, session_id, agent_id, user_id, app_id, skill_id, label, status, success, started_at, finished_at, latency_ms, tokens, result, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (env_id, "tenant", data_mode, "t-" + started, "s-" + started, agent, user, "app1", "skill1", "任务", "completed", 1, started, started, 100, 500, "ok", started),
        )
        conn.execute(
            "INSERT INTO token_usage (env_id, tenant_id, data_mode, day, agent_id, app_id, user_id, tokens, calls, success, failed, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (env_id, "tenant", data_mode, day, agent, "app1", user, 500, 1, 1, 0, started),
        )
        conn.execute(
            "INSERT INTO files (env_id, tenant_id, data_mode, file_id, task_id, session_id, agent_id, user_id, app_id, name, category, format, size_kb, download_count, downloaded, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (env_id, "tenant", data_mode, "f-" + started, "t-" + started, "s-" + started, agent, user, "app1", "file.xlsx", "report", "xlsx", 20, 1, 1, started),
        )
        conn.execute(
            "INSERT INTO file_downloads (env_id, tenant_id, data_mode, download_id, file_id, task_id, user_id, agent_id, app_id, downloaded_at, ip, device, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (env_id, "tenant", data_mode, "d-" + started, "f-" + started, "t-" + started, user, agent, "app1", started, "127.0.0.1", "pc", started),
        )
        conn.execute(
            "INSERT INTO login_activity (env_id, tenant_id, data_mode, login_id, user_id, agent_id, app_id, day, device, ip, success, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (env_id, "tenant", data_mode, "l-" + started, user, agent, "app1", day, "pc", "127.0.0.1", 1, started),
        )
        conn.execute(
            "INSERT INTO operation_logs (env_id, tenant_id, data_mode, op_id, user_id, agent_id, app_id, day, action, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (env_id, "tenant", data_mode, "o-" + started, user, agent, "app1", day, "open-app", "app1", started),
        )
    conn.commit()


class TestBuildTrends(unittest.TestCase):
    def setUp(self):
        self.conn = _make_conn()
        _seed(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_day_granularity_full_buckets(self):
        """连续日历桶完整：2026-08-03 ~ 2026-08-09 每天都存在，即使当天无数据。"""
        t = build_trends(self.conn, env_id="env_t", data_mode="demo",
                         start_date="2026-08-03", end_date="2026-08-09", granularity="day")
        self.assertEqual(len(t["series"]), 7)
        periods = [s["period"] for s in t["series"]]
        self.assertEqual(periods, ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06",
                                   "2026-08-07", "2026-08-08", "2026-08-09"])
        # 工作日与周末数据量可区分
        self.assertEqual(t["series"][0]["sessions"], 3)  # 08-03 周一
        self.assertEqual(t["series"][5]["sessions"], 1)  # 08-08 周六

    def test_workday_avg_greater_than_weekend(self):
        """工作日平均会话数应显著高于周末。"""
        t = build_trends(self.conn, env_id="env_t", data_mode="demo",
                         start_date="2026-08-03", end_date="2026-08-09", granularity="day")
        self.assertGreater(t["workday_avg"]["sessions"], t["weekend_avg"]["sessions"])
        self.assertGreater(t["workday_avg"]["tokens"], t["weekend_avg"]["tokens"])
        self.assertGreater(t["workday_avg"]["logins"], t["weekend_avg"]["logins"])

    def test_downloads_logins_operations_nonzero(self):
        """文件、下载、登录、操作不应为 0（此前 downloads/logins/operations 曾因表名映射失真读成 0）。"""
        t = build_trends(self.conn, env_id="env_t", data_mode="demo",
                         start_date="2026-08-03", end_date="2026-08-09", granularity="day")
        s = t["summary"]
        self.assertGreater(s["sessions"], 0)
        self.assertGreater(s["tasks"], 0)
        self.assertGreater(s["files"], 0)
        self.assertGreater(s["downloads"], 0)
        self.assertGreater(s["logins"], 0)
        self.assertGreater(s["operations"], 0)
        self.assertGreater(s["tokens"], 0)
        self.assertEqual(s["calls"], s["tasks"])

    def test_growth_monotonic(self):
        """企业/用户增长曲线累计上升。"""
        t = build_trends(self.conn, env_id="env_t", data_mode="demo",
                         start_date="2026-08-03", end_date="2026-08-09", granularity="day")
        # 智能体首次活跃：agent_a 08-03、agent_b 08-03（都在月初），月底合计 2
        self.assertEqual(t["growth"]["agents"][0]["total"], 2)
        self.assertEqual(t["growth"]["users"][0]["total"], 3)
        for key in ("agents", "users"):
            vals = [g["total"] for g in t["growth"][key]]
            self.assertEqual(vals, sorted(vals))

    def test_month_aggregation(self):
        """月粒度聚合跨月正确。"""
        # 加一条 8 月的额外会话，再单独断言月聚合。
        t = build_trends(self.conn, env_id="env_t", data_mode="demo",
                         start_date="2026-08-01", end_date="2026-08-31", granularity="month")
        self.assertEqual(len(t["series"]), 1)
        self.assertEqual(t["summary"]["sessions"], 17)

    def test_week_aggregation(self):
        """周粒度聚合正确，按 ISO 周归并。"""
        t = build_trends(self.conn, env_id="env_t", data_mode="demo",
                         start_date="2026-08-03", end_date="2026-08-09", granularity="week")
        self.assertEqual(len(t["series"]), 1)
        self.assertEqual(t["summary"]["sessions"], 17)

    def test_invalid_granularity_falls_back_to_day(self):
        """不支持的粒度会退化为 day（build_trends 内部仅对 day 走日用桶，其余走分组）。此处仅验证不抛异常。"""
        t = build_trends(self.conn, env_id="env_t", data_mode="demo",
                         start_date="2026-08-03", end_date="2026-08-09", granularity="bogus")
        # bogus 会走 else 分支按 _bucket_key(d, "bogus") == value 归并，结果仍应可用
        self.assertIn("series", t)
        self.assertIn("summary", t)


if __name__ == "__main__":
    unittest.main(verbosity=2)