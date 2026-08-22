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

    def test_default_production_template_exists(self) -> None:
        schema = self.core.list_schema("production")
        self.assertEqual(schema["label"], "生产日报")
        self.assertEqual([field["name"] for field in schema["fields"]], ["record_date", "department", "output", "labor_hours", "employee_count", "cost", "loss"])

    def test_entity_overview_reflects_real_and_simulated_records(self) -> None:
        row = {"order_no": "REAL-1", "customer_name": "客户", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50}
        self.core.import_rows("orders", [row])
        self.core.generate_orders(3, seed=9)
        overview = self.core.list_entities()[0]
        self.assertEqual(overview["entity"], "orders")
        self.assertEqual(overview["record_count"], 4)
        self.assertEqual(overview["real_count"], 1)
        self.assertEqual(overview["simulated_count"], 3)

    def test_user_can_add_rename_and_disable_field(self) -> None:
        self.core.add_field("orders", "sales_region", "销售区域")
        schema = self.core.update_field("orders", "sales_region", label="所属区域", active=False)
        field = next(item for item in schema["fields"] if item["name"] == "sales_region")
        self.assertEqual(field["label"], "所属区域")
        self.assertFalse(field["active"])

    def test_user_can_create_department_dataset_and_import_rows(self) -> None:
        schema = self.core.create_schema("work_logs", "车间工时", [
            {"name": "work_date", "label": "日期", "field_type": "date", "required": True},
            {"name": "department", "label": "部门", "field_type": "text", "required": True},
            {"name": "output", "label": "产量", "field_type": "number"},
            {"name": "labor_hours", "label": "工时", "field_type": "number"},
        ])
        self.assertEqual(schema["entity"], "work_logs")
        self.core.import_rows("work_logs", [{"work_date": "2026-08-22", "department": "一车间", "output": 120, "labor_hours": 24}])
        self.assertEqual(self.core.list_records("work_logs")[0]["data"]["output"], 120)

    def test_duplicate_or_unsafe_dataset_is_rejected(self) -> None:
        with self.assertRaises(DataCoreError):
            self.core.create_schema("DROP TABLE", "危险", [{"name": "value", "label": "值"}])
        self.core.create_schema("finance", "财务", [{"name": "amount", "label": "金额", "field_type": "number"}])
        with self.assertRaisesRegex(DataCoreError, "already exists"):
            self.core.create_schema("finance", "财务", [{"name": "amount", "label": "金额"}])

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

    def test_production_simulation_is_reversible(self) -> None:
        batch = self.core.generate_production(12, seed=17)
        records = self.core.list_records("production", source_type="simulated")
        self.assertEqual(len(records), 12)
        self.assertIn(records[0]["data"]["department"], ["机加工一部", "装配一部", "表面处理", "质量检验"])
        self.core.rollback_batch(batch["batch_id"])
        self.assertEqual(self.core.list_records("production"), [])

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

    def test_order_dashboard_query_can_filter_real_records(self) -> None:
        rows = [
            {"order_no": "REAL-OPEN", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "生产中", "progress": 50},
            {"order_no": "REAL-DONE", "customer_name": "海川制造", "product_name": "电机", "quantity": 10, "order_date": "2026-08-01", "promised_date": "2026-08-20", "status": "已完成", "progress": 100},
        ]
        self.core.import_rows("orders", rows)
        self.core.generate_orders(2, seed=12)

        result = self.core.search_records(
            "orders",
            keyword="海川",
            filters={"status": "生产中"},
            source_type="real",
            limit=200,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_type"], "real")
        self.assertEqual(result[0]["data"]["order_no"], "REAL-OPEN")
        self.assertEqual(result[0]["data"]["progress"], 50)

    def test_order_dashboard_query_has_a_hard_result_limit(self) -> None:
        self.core.generate_orders(220, seed=31)
        result = self.core.search_records("orders", limit=1000)
        self.assertEqual(len(result), 200)


if __name__ == "__main__":
    unittest.main()
