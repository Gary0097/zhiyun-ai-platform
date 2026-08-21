import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from workspace_store import append_runtime, ensure  # noqa: E402


class OrdersStoreTest(unittest.TestCase):
    def test_seed_is_idempotent_and_logs_are_workspace_local(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, logs = ensure(root)
            ensure(root)
            with sqlite3.connect(database) as db:
                count = db.execute("SELECT COUNT(*) FROM orders_order").fetchone()[0]
                red = db.execute("SELECT COUNT(*) FROM orders_order WHERE risk_level='红色'").fetchone()[0]
            self.assertEqual(count, 6)
            self.assertEqual(red, 1)
            append_runtime(logs, {"trace_id": "orders-test", "event": "orders.query", "status": "success"})
            event = json.loads((logs / "runtime.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(event["trace_id"], "orders-test")
            self.assertFalse((Path(__file__).parent / "data").exists())


if __name__ == "__main__":
    unittest.main()
