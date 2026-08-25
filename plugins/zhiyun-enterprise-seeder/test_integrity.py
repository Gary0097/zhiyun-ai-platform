# -*- coding: utf-8 -*-
"""Data Integrity 自动修复 + 每日报告单元测试（Epic 6）。
不依赖宿主插件，直接导入 enterprise_plugin 并在内存/临时 sqlite 上构造损坏数据。"""

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ.setdefault("ZHIYUN_ENTERPRISE_DIR", tempfile.mkdtemp(prefix="zi_integrity_"))
os.environ.setdefault("QWENPAW_WORKING_DIR", tempfile.mkdtemp(prefix="zi_work_"))

import enterprise_plugin as ep  # noqa: E402

ENV_ID = "env_integrity_unit"
TENANT_ID = "tenant_integrity_unit"
MODE = "demo"


class IntegrityTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="zi_integrity_db_"))
        ep.DB = cls.tmp / "enterprise.db"
        ep.ENTERPRISE_DIR = cls.tmp
        ep.AUTH_USERS_FILE = cls.tmp / "users.json"
        ep.AUTH_SECRET_FILE = cls.tmp / "token_secret.txt"
        ep._schema_lock = False
        ep._ensure_schema()

    def setUp(self):
        # 每个用例独立数据库
        if ep.DB.exists():
            os.remove(str(ep.DB))
        ep._schema_lock = False
        ep._ensure_schema()
        self.conn = ep._connect()
        ts = ep._now()
        self.conn.execute(
            "INSERT INTO enterprise_meta (env_id, tenant_id, data_mode, enterprise, template, start_date, end_date, scale, departments, agent_count, activity, created_at, updated_at) "
            "VALUES (?,?,?,'测试企业','manufacturing','2026-01-01','2026-01-31',10,3,1,'medium',?,?)",
            (ENV_ID, TENANT_ID, MODE, ts, ts),
        )
        self.conn.execute(
            "INSERT INTO org_users (env_id, tenant_id, data_mode, username, display_name, department, role, title, agent_id, data_scope, kb_scope, active, dormant, hired_on, created_at) "
            "VALUES (?,?,?,'alice','Alice','研发部','member','工程师','agent_a','dept','enterprise',1,0,'2026-01-01',?)",
            (ENV_ID, TENANT_ID, MODE, ts),
        )
        self.conn.execute(
            "INSERT INTO org_users (env_id, tenant_id, data_mode, username, display_name, department, role, title, agent_id, data_scope, kb_scope, active, dormant, hired_on, created_at) "
            "VALUES (?,?,?,'bob','Bob','生产部','member','工程师',NULL,'dept','enterprise',1,0,'2026-01-01',?)",
            (ENV_ID, TENANT_ID, MODE, ts),
        )
        self.conn.execute(
            "INSERT INTO agents (env_id, tenant_id, data_mode, agent_id, name, position, department, model, success_rate, enabled, created_at) "
            "VALUES (?,?,?,'agent_a','数字员工','研发','研发部','本地Qwen',0.92,1,?)",
            (ENV_ID, TENANT_ID, MODE, ts),
        )
        # 有效会话 s1；孤儿用户会话 s2；孤儿智能体会话 s3
        for sid, uid, aid in (("s1", "alice", "agent_a"), ("s2", "ghost", "agent_a"), ("s3", "alice", "ghost_agent")):
            self.conn.execute(
                "INSERT INTO sessions (env_id, tenant_id, data_mode, session_id, user_id, agent_id, app_id, messages, started_at, ended_at, status, created_at) "
                "VALUES (?,?,?,?,?,?,'app_x',3,'2026-01-02 09:00:00','2026-01-02 09:10:00','done',?)",
                (ENV_ID, TENANT_ID, MODE, sid, uid, aid, ts),
            )
        # 任务 t1 绑定 s1；t2 绑定孤儿 s2；t3 绑定不存在的会话
        for tid, sid, toks in (("t1", "s1", 15), ("t2", "s2", 0), ("t3", "ghost_sess", 0)):
            self.conn.execute(
                "INSERT INTO tasks (env_id, tenant_id, data_mode, task_id, session_id, agent_id, user_id, app_id, label, status, success, started_at, finished_at, latency_ms, tokens, created_at) "
                "VALUES (?,?,?,?,?,?,'alice','app_x','任务','done',1,'2026-01-02 09:00:00','2026-01-02 09:05:00',500,?,?)",
                (ENV_ID, TENANT_ID, MODE, tid, sid, "agent_a", toks, ts),
            )
        # 文件 f1 有效（download_count 故意不对）；f2 是孤儿文件
        for fid, tid, dc in (("f1", "t1", 0), ("f2", "ghost_task", 0)):
            self.conn.execute(
                "INSERT INTO files (env_id, tenant_id, data_mode, file_id, task_id, session_id, agent_id, user_id, app_id, name, category, format, size_kb, download_count, downloaded, created_at) "
                "VALUES (?,?,?,?,?,?,'agent_a','alice','app_x','报告','report','pdf',100,?,0,?)",
                (ENV_ID, TENANT_ID, MODE, fid, tid, "s1", dc, ts),
            )
        # 下载 d1 归属 f1；d2 是孤儿下载
        for did, fid in (("d1", "f1"), ("d2", "ghost_file")):
            self.conn.execute(
                "INSERT INTO file_downloads (env_id, tenant_id, data_mode, download_id, file_id, task_id, user_id, agent_id, app_id, downloaded_at, ip, device, created_at) "
                "VALUES (?,?,?,?,?,?,'alice','agent_a','app_x','2026-01-02 09:06:00','127.0.0.1','pc',?)",
                (ENV_ID, TENANT_ID, MODE, did, fid, "t1", ts),
            )
        # token_usage：两日且次日下降，满足波动；且含失败，避免 100% 成功率异常
        for day, tk, calls, suc, fail in (("2026-01-01", 10, 2, 1, 1), ("2026-01-02", 5, 1, 0, 1)):
            self.conn.execute(
                "INSERT INTO token_usage (env_id, tenant_id, data_mode, day, agent_id, app_id, user_id, tokens, calls, success, failed, created_at) "
                "VALUES (?,?,?,?,?,'app_x','alice',?,?,?,?,?)",
                (ENV_ID, TENANT_ID, MODE, day, "agent_a", tk, calls, suc, fail, ts),
            )
        self.conn.commit()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass


class TestIntegrityRepair(IntegrityTestBase):
    def test_repair_cleans_orphans_and_recalcs(self):
        before = ep._integrity_report(ENV_ID, MODE)
        self.assertGreater(before.get("failed", 0), 0, "损坏数据应产生失败项")
        result = ep._repair_integrity(ENV_ID, MODE, run_by="tester")
        self.assertTrue(result.get("ok"))
        after = result["report"]
        for cid in ("session_user_scope", "session_agent_scope", "task_session_scope",
                    "file_task_scope", "file_download_scope", "file_download_consistency",
                    "user_agent_binding"):
            row = next(c for c in after["report"] if c["id"] == cid)
            self.assertEqual(row["status"], "pass", f"{cid} 修复后应通过: {row}")
        # 孤儿数据被移除，下载计数回填
        self.assertEqual(int(self.conn.execute("SELECT COUNT(*) FROM sessions WHERE env_id=? AND data_mode=?", (ENV_ID, MODE)).fetchone()[0]), 1)
        self.assertEqual(int(self.conn.execute("SELECT COUNT(*) FROM tasks WHERE env_id=? AND data_mode=?", (ENV_ID, MODE)).fetchone()[0]), 1)
        self.assertEqual(int(self.conn.execute("SELECT COUNT(*) FROM files WHERE env_id=? AND data_mode=?", (ENV_ID, MODE)).fetchone()[0]), 1)
        self.assertEqual(int(self.conn.execute("SELECT COUNT(*) FROM file_downloads WHERE env_id=? AND data_mode=?", (ENV_ID, MODE)).fetchone()[0]), 1)
        f1 = self.conn.execute("SELECT download_count FROM files WHERE env_id=? AND data_mode=? AND file_id='f1'", (ENV_ID, MODE)).fetchone()
        self.assertEqual(int(f1["download_count"]), 1)
        bob = self.conn.execute("SELECT agent_id FROM org_users WHERE env_id=? AND data_mode=? AND username='bob'", (ENV_ID, MODE)).fetchone()
        self.assertEqual(bob["agent_id"], "agent_a")
        # 修复日志完整
        logs = self.conn.execute("SELECT * FROM integrity_repair_log WHERE env_id=? AND data_mode=? AND run_by='tester'", (ENV_ID, MODE)).fetchall()
        self.assertGreaterEqual(len(logs), 7, "应至少记录 7 项修复动作")
        self.assertTrue(any(r["check_id"] == "file_download_consistency" and r["affected"] == 1 for r in logs))

    def test_repair_zeroes_non_task_business_event_tokens(self):
        ts = ep._now()
        # 构造带 Token 的 session/file/download 事件（旧版双算，应被归零）与 task 事件（应保留）。
        for et, eid, toks in (
            ("session", "be_session", 500),
            ("file", "be_file", 300),
            ("download", "be_download", 200),
            ("task", "be_task", 100),
        ):
            self.conn.execute(
                "INSERT INTO business_events (event_id, env_id, tenant_id, data_mode, day, user_id, agent_id, app_id, event_type, session_id, task_id, file_id, download_id, tokens, success, latency_ms, started_at, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (eid, ENV_ID, TENANT_ID, MODE, "2026-01-02", "alice", "agent_a", "app_x", et,
                 "be_session" if et == "session" else "s1",
                 "t1" if et == "task" else None,
                 "f1" if et == "file" else None,
                 "d1" if et == "download" else None,
                 toks, 1, 100, "2026-01-02 09:00:00", ts),
            )
        self.conn.commit()

        before_non_task = int(self.conn.execute(
            "SELECT COUNT(*) FROM business_events WHERE env_id=? AND data_mode=? AND event_type<>'task' AND tokens<>0",
            (ENV_ID, MODE),
        ).fetchone()[0])
        self.assertEqual(before_non_task, 3)

        result = ep._repair_integrity(ENV_ID, MODE, run_by="tester")
        self.assertTrue(result.get("ok"))
        non_task = int(self.conn.execute(
            "SELECT COUNT(*) FROM business_events WHERE env_id=? AND data_mode=? AND event_type<>'task' AND tokens<>0",
            (ENV_ID, MODE),
        ).fetchone()[0])
        self.assertEqual(non_task, 0, "非任务业务事件 Token 应被归零")
        task_tok = int(self.conn.execute(
            "SELECT tokens FROM business_events WHERE env_id=? AND data_mode=? AND event_id='be_task'",
            (ENV_ID, MODE),
        ).fetchone()[0])
        self.assertEqual(task_tok, 100, "任务业务事件 Token 应保留")
        logs = self.conn.execute(
            "SELECT * FROM integrity_repair_log WHERE env_id=? AND data_mode=? AND check_id='business_event_token_accounting'",
            (ENV_ID, MODE),
        ).fetchall()
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(int(logs[0]["affected"]), 3)

    def test_repair_empty_env(self):
        ep.conn = ep._connect()
        try:
            ep.conn.execute("DELETE FROM enterprise_meta")
            ep.conn.commit()
        finally:
            ep.conn.close()
        result = ep._repair_integrity()
        self.assertEqual(result.get("status"), "empty")


class TestIntegrityDailyReport(IntegrityTestBase):
    def test_daily_report_idempotent_and_history(self):
        first = ep._daily_integrity_report(ENV_ID, MODE)
        self.assertEqual(first.get("persist"), "inserted")
        self.assertEqual(first.get("report_day"), ep._today())
        second = ep._daily_integrity_report(ENV_ID, MODE)
        self.assertEqual(second.get("persist"), "updated")
        hist = ep._integrity_history(ENV_ID, MODE, limit=30)
        self.assertEqual(hist["count"], 1)
        self.assertTrue(any(r["report_day"] == ep._today() for r in hist["rows"]))
        # 历史快照应包含报告摘要
        row = hist["rows"][0]
        self.assertEqual(int(row["total"]), int(second["total"]))


if __name__ == "__main__":
    unittest.main()
