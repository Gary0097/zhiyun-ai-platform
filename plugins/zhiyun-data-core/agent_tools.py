# -*- coding: utf-8 -*-
"""Agent-callable Data Core tools with bounded, auditable access."""

from __future__ import annotations

import json

from agentscope.message import TextBlock, ToolResultState
from agentscope.tool import ToolChunk

try:
    from .data_core import DataCore, DataCoreError
except ImportError:
    from data_core import DataCore, DataCoreError


def build_agent_tools(core: DataCore):
    """Bind tools to the same Data Core instance used by the HTTP API."""

    def query_enterprise_orders(
        keyword: str = "",
        order_no: str = "",
        customer_name: str = "",
        status: str = "",
        source_type: str = "",
        limit: int = 50,
    ) -> ToolChunk:
        """Query enterprise orders from the unified database.

        Use this tool whenever the user asks about orders, customers, order
        status, delivery progress, or imported/simulated order data. Filters
        are optional and results are capped at 200 records.
        """
        filters = {
            "order_no": order_no,
            "customer_name": customer_name,
            "status": status,
        }
        try:
            records = core.search_records(
                "orders",
                keyword=keyword,
                filters=filters,
                source_type=source_type or None,
                limit=limit,
            )
            payload = {
                "entity": "orders",
                "count": len(records),
                "filters": {key: value for key, value in filters.items() if value},
                "keyword": keyword,
                "records": records,
            }
            return ToolChunk(
                state=ToolResultState.SUCCESS,
                content=[TextBlock(type="text", text=json.dumps(payload, ensure_ascii=False))],
            )
        except DataCoreError as exc:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[TextBlock(type="text", text=f"Data Core 查询失败：{exc}")],
            )

    def generate_simulated_orders(count: int = 50, seed: int | None = None) -> ToolChunk:
        """Generate reversible simulated orders in the unified database.

        Only use this when the user explicitly asks to create test or demo
        order data. The result contains a batch ID that can be rolled back.
        """
        try:
            result = core.generate_orders(count=count, seed=seed)
            return ToolChunk(
                state=ToolResultState.SUCCESS,
                content=[TextBlock(type="text", text=json.dumps(result, ensure_ascii=False))],
            )
        except DataCoreError as exc:
            return ToolChunk(
                state=ToolResultState.ERROR,
                content=[TextBlock(type="text", text=f"模拟数据生成失败：{exc}")],
            )

    return query_enterprise_orders, generate_simulated_orders
