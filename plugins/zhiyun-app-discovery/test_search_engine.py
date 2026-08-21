# -*- coding: utf-8 -*-
"""App Discovery acceptance tests."""

import unittest

from search_engine import agent_response, load_catalog, search_apps


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


if __name__ == "__main__":
    unittest.main()
