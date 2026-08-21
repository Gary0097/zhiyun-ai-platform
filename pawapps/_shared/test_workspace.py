import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from zhiyun_workspace import append_event, ensure_workspace


class WorkspaceCoreTest(unittest.TestCase):
    def test_initializes_database_and_redacted_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = ensure_workspace(directory)
            self.assertTrue(paths.database.exists())
            with sqlite3.connect(paths.database) as database:
                tables = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("os_app_execution", tables)
            self.assertIn("os_tool_execution", tables)
            self.assertIn("os_audit_event", tables)
            append_event(paths, {"trace_id": "trace-1", "event": "test", "token": "must-not-leak"})
            event = json.loads(paths.runtime_log.read_text(encoding="utf-8"))
            self.assertEqual(event["token"], "[REDACTED]")

    def test_refuses_process_directory_fallback(self):
        with self.assertRaises(RuntimeError):
            ensure_workspace(None)


if __name__ == "__main__":
    unittest.main()
