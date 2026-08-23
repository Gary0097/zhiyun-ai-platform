import unittest

from risk_policy import assess


class RiskPolicyTest(unittest.TestCase):
    def test_blocks_unix_root_recursive_delete(self):
        decision = assess("shell", {"cmd": "sudo rm -rf /"})
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.rule_id, "shell.catastrophic-delete")

    def test_blocks_windows_system_drive_delete(self):
        decision = assess("powershell", {"command": "Remove-Item -Recurse -Force C:\\"})
        self.assertTrue(decision.blocked)

    def test_blocks_destructive_database_ddl(self):
        decision = assess("execute_sql", {"sql": "DROP TABLE orders"})
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.rule_id, "database.destructive-ddl")

    def test_blocks_destructive_git_rewrite(self):
        self.assertTrue(assess("shell", {"cmd": "git reset --hard"}).blocked)

    def test_blocks_root_path_delete_tool(self):
        self.assertTrue(assess("delete_directory", {"path": "C:\\"}).blocked)

    def test_allows_scoped_cleanup(self):
        self.assertFalse(assess("shell", {"cmd": "rm -rf /tmp/zhiyun-build"}).blocked)
        self.assertFalse(assess("delete_file", {"path": "/tmp/report.csv"}).blocked)
        self.assertFalse(assess("execute_sql", {"sql": "DELETE FROM orders WHERE batch_id = ?"}).blocked)

    def test_external_write_requires_explicit_confirmation(self):
        blocked = assess("send_customer_email", {"to": "customer@example.com"})
        self.assertTrue(blocked.blocked)
        self.assertEqual(blocked.rule_id, "external-write.confirmation-required")
        self.assertFalse(assess("send_customer_email", {"to": "customer@example.com", "confirmed": True}).blocked)


if __name__ == "__main__":
    unittest.main()
