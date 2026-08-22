import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_store import list_events, persist


class AuditStoreTest(unittest.TestCase):
    def test_persists_redacted_jsonl_and_sqlite_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            persist(root, {"trace_id": "t-1", "session_id": "s-1", "agent_id": "default", "tool_name": "web_search", "tool_input": {"token": "secret-value"}, "status": "success", "duration_ms": 12, "error_type": None})
            runtime = json.loads((root / "logs/runtime.jsonl").read_text(encoding="utf-8"))
            audit = json.loads((root / "logs/audit.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(runtime["tool_input"]["token"], "[REDACTED]")
            self.assertEqual(audit["trace_id"], "t-1")
            database = sqlite3.connect(root / "data/ai-os.sqlite")
            try:
                row = database.execute("SELECT tool_name,status FROM audit_tool_call WHERE trace_id='t-1'").fetchone()
            finally:
                # sqlite3.Connection's context manager does not close the handle.
                # Explicit close is required before TemporaryDirectory cleanup on Windows.
                database.close()
            self.assertEqual(row, ("web_search", "success"))

    def test_lists_bounded_filtered_metadata_without_tool_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            persist(root, {"trace_id": "t-1", "tool_name": "web_search", "tool_input": {"password": "hidden"}, "status": "success", "duration_ms": 12})
            persist(root, {"trace_id": "t-2", "tool_name": "shell", "tool_input": {"command": "echo ok"}, "status": "blocked", "duration_ms": 0, "error_type": "HighRiskOperationBlocked"})

            events = list_events(root, status="blocked", tool_name="shell", limit=1000)

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["trace_id"], "t-2")
            self.assertNotIn("tool_input", events[0])

    def test_empty_workspace_has_no_audit_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(list_events(root), [])

    def test_rejects_unknown_audit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "unsupported audit status"):
                list_events(Path(directory), status="unknown")


if __name__ == "__main__":
    unittest.main()
