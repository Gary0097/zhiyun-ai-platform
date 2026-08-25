# -*- coding: utf-8 -*-
"""企业初始化记录数真实性单元测试（对应 PR review 修复）。

验证知识库/工作区类应用在全新初始化环境中不得伪造虚构记录数：
``data_sources.records`` 必须为 0（无真实导入文档），而业务类应用仍按
企业体量生成真实记录数，从而避免演示数据与底层记录不一致。

注意：本插件依赖 fastapi/pydantic 与宿主 qwenpaw 运行时，发布门禁的全局
Python（缺少 anyio）无法导入，请使用 QwenPaw venv Python 运行。
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import enterprise_plugin as ep  # noqa: E402


class SeedRecordsTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_base = Path(tempfile.mkdtemp(prefix="zi_seed_records_"))

    def setUp(self):
        # 每个用例独立临时目录与数据库，避免跨用例污染
        self.tmp = Path(tempfile.mkdtemp(prefix="zi_seed_records_db_"))
        ep.DB = self.tmp / "enterprise.db"
        ep.ENTERPRISE_DIR = self.tmp
        ep.AUTH_USERS_FILE = self.tmp / "users.json"
        ep.AUTH_SECRET_FILE = self.tmp / "token_secret.txt"
        ep._schema_lock = False
        ep._ensure_schema()

    def tearDown(self):
        ep._schema_lock = False

    def _seed(self) -> str:
        """生成一个小型演示企业，返回 env_id。"""
        result = ep._generate_enterprise({
            "enterprise": "智云智造测试",
            "start_date": "2026-01-02",
            "end_date": "2026-01-02",
            "scale": 5,
            "departments": 3,
            "agents": 3,
            "seed": 123,
            "data_mode": "demo",
        })
        self.assertEqual(result["data_mode"], "demo")
        return result["env_id"], result

    def _data_sources(self, env_id: str) -> dict[str, int]:
        conn = ep._connect()
        try:
            rows = conn.execute(
                "SELECT app_id, records FROM data_sources WHERE env_id=? AND data_mode='demo'",
                (env_id,),
            ).fetchall()
            return {r["app_id"]: r["records"] for r in rows}
        finally:
            conn.close()


class TestKnowledgeBaseZeroRecords(SeedRecordsTestBase):
    def test_knowledge_base_has_zero_records_in_fresh_env(self):
        env_id, summary = self._seed()
        sources = self._data_sources(env_id)
        self.assertIn("qwenpaw-knowledge-base", sources, "知识库应用应生成 data_source 行")
        self.assertEqual(
            sources["qwenpaw-knowledge-base"], 0,
            "未导入真实文档的知识库应用不得伪造记录数（应为 0）",
        )

    def test_business_app_has_real_records(self):
        env_id, _ = self._seed()
        sources = self._data_sources(env_id)
        # 业务类应用应生成真实记录数（800..5200 区间）
        for app_id in ("zhiyun-order-studio", "zhiyun-data-core", "zhiyun-app-discovery"):
            self.assertIn(app_id, sources, f"{app_id} 应生成 data_source 行")
            self.assertGreater(
                sources[app_id], 0,
                f"业务/系统类应用 {app_id} 应生成真实记录数（{app_id}={sources[app_id]}）",
            )

    def test_all_apps_have_data_source_row(self):
        env_id, summary = self._seed()
        sources = self._data_sources(env_id)
        # 初始化应覆盖全部 APP_TEMPLATES，且每个都有 records 值
        template_ids = {a["id"] for a in ep.APP_TEMPLATES}
        self.assertEqual(set(sources.keys()), template_ids, "data_sources 应覆盖全部已登记应用")
        self.assertEqual(summary["data_sources"], len(ep.APP_TEMPLATES))


if __name__ == "__main__":
    unittest.main()
