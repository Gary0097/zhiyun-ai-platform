# -*- coding: utf-8 -*-
"""App Discovery acceptance tests."""

import unittest

from search_engine import agent_response, load_catalog, load_progress, progress_summary, search_apps


class SearchEngineTests(unittest.TestCase):
    def test_catalog_has_unique_ids(self) -> None:
        apps = load_catalog()["apps"]
        ids = [app["app_id"] for app in apps]
        self.assertEqual(len(ids), len(set(ids)))

    def test_delivery_risk_prefers_data_studio(self) -> None:
        result = search_apps("哪个应用能分析订单交付风险")
        self.assertEqual(result[0]["app_id"], "zhiyun-data-studio")
        self.assertEqual(result[0]["matched_capability"]["capability_id"], 2)

    def test_contract_difference_prefers_order_studio(self) -> None:
        result = search_apps("处理订单合同不一致")
        self.assertEqual(result[0]["app_id"], "zhiyun-order-studio")
        self.assertEqual(result[0]["matched_capability"]["capability_id"], 10)
        self.assertEqual(result[0]["install_status"], "installed")
        self.assertEqual(result[0]["route"], "/apps/zhiyun-order-studio")
        self.assertEqual(result[0]["repository_url"], "https://github.com/Gary0097/zhiyun-order-studio")

    def test_expense_review_prefers_finance_studio(self) -> None:
        result = search_apps("识别发票并审核报销")
        self.assertEqual(result[0]["app_id"], "zhiyun-finance-studio")

    def test_sales_performance_prefers_sales_studio(self) -> None:
        result = search_apps("分析销售人员业绩")
        self.assertEqual(result[0]["app_id"], "zhiyun-sales-studio")

    def test_knowledge_request_prefers_native_workspace(self) -> None:
        result = search_apps("整理资料并形成企业知识库")
        self.assertEqual(result[0]["app_id"], "qwenpaw-knowledge-base")
        self.assertEqual(result[0]["install_status"], "installed")

    def test_unknown_query_never_invents_app(self) -> None:
        response = agent_response("量子火箭发动机自动装配")
        self.assertFalse(response["found"])
        self.assertEqual(response["results"], [])

    def test_planned_capability_is_not_reported_available(self) -> None:
        response = agent_response("识别发票并审核报销")
        self.assertTrue(response["found"])
        self.assertFalse(response["available"])
        self.assertIn("尚未交付", response["message"])

    def test_installed_app_does_not_make_planned_capability_available(self) -> None:
        response = agent_response("处理延期和投诉复合异常")
        self.assertTrue(response["found"])
        self.assertFalse(response["available"])
        result = response["results"][0]
        self.assertEqual(result["app_id"], "zhiyun-order-studio")
        self.assertEqual(result["matched_capability"]["delivery_status"], "planned")
        self.assertFalse(result["available"])

    def test_installed_catalog_is_truthful(self) -> None:
        apps = {app["app_id"]: app for app in load_catalog()["apps"]}
        self.assertEqual(apps["zhiyun-data-studio"]["version"], "0.7.2")
        self.assertEqual(apps["zhiyun-data-studio"]["install_status"], "installed")
        self.assertEqual(apps["zhiyun-order-studio"]["version"], "0.5.2")
        self.assertEqual(apps["zhiyun-order-studio"]["health"], "available")
        self.assertEqual(apps["zhiyun-data-core"]["version"], "0.5.0")
        self.assertEqual(apps["zhiyun-audit"]["version"], "1.1.1")

    def test_progress_covers_all_31_prd_features(self) -> None:
        ledger = load_progress()
        self.assertEqual([item["id"] for item in ledger["features"]], list(range(1, 32)))
        summary = progress_summary(ledger)
        self.assertEqual(summary["total"], 31)
        self.assertEqual(summary["testing"], 6)
        self.assertEqual(summary["in_progress"], 7)
        self.assertEqual(summary["completed"], 0)
        self.assertEqual(summary["overall_progress"], 24)


if __name__ == "__main__":
    unittest.main()
