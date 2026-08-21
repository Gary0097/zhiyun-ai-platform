# -*- coding: utf-8 -*-
"""Data Core behavioral tests with an isolated SQLite database."""

import tempfile
import unittest
from pathlib import Path

from data_core import DataCore, DataCoreError


class DataCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.core = DataCore(Path(self.temp.name) / "data-core.sqlite")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_default_order_schema_exists(self) -> None:
        schema = self.core.list_schema("orders")
        self.assertIn("order_no", [field["name"] for field in schema["fields"]])

    def test_user_can_add_rename_and_disable_field(self) -> None:
        self.core.add_field("orders", "sales_region", "销售区域")
        schema = self.core.update_field("orders", "sales_region", label="所属区域", active=False)
        field = next(item for item in schema["fields"] if item["name"] == "sales_region")
        self.assertEqual(field["label"], "所属区域")
        self.assertFalse(field["active"])

    def test_invalid_field_identifier_is_rejected(self) -> None:
        with self.assertRaises(DataCoreError):
            self.core.add_field("orders", "DROP TABLE", "危险字段")

    def test_import_preview_reports_row_errors(self) -> None:
        preview = self.core.preview_import(
            "orders",
            [{"order_no": "A-1", "customer_name": "客户", "product_name": "电机", "quantity": "abc", "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50}],
        )
        self.assertEqual(preview["error_count"], 1)
        self.assertIn("quantity must be integer", preview["errors"][0]["errors"])

    def test_real_import_is_traceable_and_reversible(self) -> None:
        row = {"order_no": "A-1", "customer_name": "客户", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50}
        batch = self.core.import_rows("orders", [row], source_name="orders.xlsx")
        records = self.core.list_records("orders")
        self.assertEqual(records[0]["source_type"], "real")
        self.assertEqual(records[0]["batch_id"], batch["batch_id"])
        rollback = self.core.rollback_batch(batch["batch_id"])
        self.assertEqual(rollback["deleted_records"], 1)
        self.assertEqual(self.core.list_records("orders"), [])

    def test_simulation_is_deterministic_and_does_not_touch_real_data(self) -> None:
        real = {"order_no": "REAL-1", "customer_name": "客户", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50}
        self.core.import_rows("orders", [real])
        simulated = self.core.generate_orders(4, seed=7)
        self.assertEqual(len(self.core.list_records("orders", source_type="simulated")), 4)
        self.core.rollback_batch(simulated["batch_id"])
        remaining = self.core.list_records("orders")
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["data"]["order_no"], "REAL-1")

    def test_agent_search_filters_orders_without_sql(self) -> None:
        rows = [
            {"order_no": "A-1", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50},
            {"order_no": "B-1", "customer_name": "星联科技", "product_name": "传感器", "quantity": 20, "order_date": "2026-08-02", "promised_date": "2026-08-22", "status": "已完成", "progress": 100},
        ]
        self.core.import_rows("orders", rows)
        result = self.core.search_records("orders", keyword="海川", filters={"status": "生产中"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["data"]["order_no"], "A-1")

    def test_agent_search_rejects_unknown_filter(self) -> None:
        with self.assertRaisesRegex(DataCoreError, "unknown filter fields"):
            self.core.search_records("orders", filters={"sql": "DROP TABLE"})


if __name__ == "__main__":
    unittest.main()
