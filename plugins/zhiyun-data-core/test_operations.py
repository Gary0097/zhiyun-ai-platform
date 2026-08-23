import base64
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from data_core import DataCore, SCHEMA_VERSION
from operations import DataCoreOperations, DataOperationError


class DataCoreOperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.core = DataCore(self.root / "data-core.sqlite")
        self.ops = DataCoreOperations(self.core.database, self.root / "backups")

    def tearDown(self):
        os.environ.pop("TEST_BACKUP_KEY", None)
        self.temp.cleanup()

    def test_migration_journal_reaches_current_version_idempotently(self):
        DataCore(self.core.database)
        history = self.core.migration_history()
        self.assertEqual(history[-1]["version"], SCHEMA_VERSION)
        self.assertEqual(len({item["version"] for item in history}), len(history))

    def test_plain_backup_restore_and_safety_backup(self):
        batch = self.core.generate_orders(2, seed=7)
        backup = self.ops.create_backup()
        self.core.rollback_batch(batch["batch_id"])
        restored = self.ops.restore_backup(backup["name"], confirmed=True)
        self.assertEqual(restored["integrity"], "ok")
        self.assertEqual(len(self.core.list_records("orders")), 2)
        self.assertTrue(restored["safety_backup"].endswith(".zdb"))

    def test_encrypted_backup_requires_correct_key(self):
        os.environ["TEST_BACKUP_KEY"] = base64.urlsafe_b64encode(b"k" * 32).decode()
        backup = self.ops.create_backup(key_env="TEST_BACKUP_KEY")
        self.assertTrue(backup["encrypted"])
        os.environ["TEST_BACKUP_KEY"] = base64.urlsafe_b64encode(b"x" * 32).decode()
        with self.assertRaises(DataOperationError):
            self.ops.restore_backup(backup["name"], confirmed=True, key_env="TEST_BACKUP_KEY")

    def test_restore_requires_confirmation_and_checksum(self):
        backup = self.ops.create_backup()
        with self.assertRaises(DataOperationError):
            self.ops.restore_backup(backup["name"], confirmed=False)
        path = self.root / "backups" / backup["name"]
        path.write_bytes(path.read_bytes() + b"tampered")
        with self.assertRaises(DataOperationError):
            self.ops.restore_backup(backup["name"], confirmed=True)

    def test_health_reports_integrity_and_space(self):
        health = self.ops.health()
        self.assertEqual(health["status"], "available")
        self.assertEqual(health["schema_version"], SCHEMA_VERSION)
        self.assertGreater(health["free_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
