import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_store import persist


class AuditStoreTest(unittest.TestCase):
    def test_persists_redacted_jsonl_and_sqlite_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            persist(root, {"trace_id": "t-1", "session_id": "s-1", "agent_id": "default", "tool_name": "web_search", "tool_input": {"token": "secret-value"}, "status": "success", "duration_ms": 12, "error_type": None})
            runtime = json.loads((root / "logs/runtime.jsonl").read_text(encoding="utf-8"))
            audit = json.loads((root / "logs/audit.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(runtime["tool_input"]["token"], "[REDACTED]")
            self.assertEqual(audit["trace_id"], "t-1")
            with sqlite3.connect(root / "data/ai-os.sqlite") as database:
                row = database.execute("SELECT tool_name,status FROM audit_tool_call WHERE trace_id='t-1'").fetchone()
            self.assertEqual(row, ("web_search", "success"))


if __name__ == "__main__":
    unittest.main()
