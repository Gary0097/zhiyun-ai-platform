# -*- coding: utf-8 -*-
"""Orders and delivery-risk PawApp backed by the active Agent Workspace."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from qwenpaw.pawapp import PawApp, get_ctx

try:
    from .workspace_store import append_runtime, connect, current_workspace, ensure
except ImportError:  # QwenPaw loads plugin backends as standalone modules.
    from workspace_store import append_runtime, connect, current_workspace, ensure

router = APIRouter()


def _trace() -> str:
    return f"orders-{uuid.uuid4()}"


def _query(root: Path, order_no: str = "", status: str = "", risk_level: str = "") -> dict[str, Any]:
    started = time.monotonic()
    trace_id = _trace()
    database, logs = ensure(root)
    sql = "SELECT order_no,customer,product,quantity,amount,due_date,status,current_node,progress,delay_hours,risk_level,risk_reason,updated_at,data_origin FROM orders_order WHERE 1=1"
    params: list[Any] = []
    if order_no:
        sql += " AND order_no = ?"; params.append(order_no)
    if status:
        sql += " AND status = ?"; params.append(status)
    if risk_level:
        sql += " AND risk_level = ?"; params.append(risk_level)
    sql += " ORDER BY CASE risk_level WHEN '红色' THEN 1 WHEN '黄色' THEN 2 ELSE 3 END, due_date"
    with connect(database) as db:
        orders = [dict(row) for row in db.execute(sql, params).fetchall()]
    summary = {
        "total": len(orders),
        "red": sum(row["risk_level"] == "红色" for row in orders),
        "yellow": sum(row["risk_level"] == "黄色" for row in orders),
        "green": sum(row["risk_level"] == "绿色" for row in orders),
    }
    result = {"traceId": trace_id, "summary": summary, "orders": orders}
    append_runtime(logs, {"trace_id": trace_id, "app_id": "zhiyun-orders", "event": "orders.query", "status": "success", "duration_ms": round((time.monotonic() - started) * 1000), "result_count": len(orders)})
    return result


async def _route_root(ctx: Any) -> Path:
    workspace = await ctx._get_workspace()  # QwenPaw 2.1 PawApp context contract
    if workspace is None or not getattr(workspace, "workspace_dir", None):
        raise HTTPException(status_code=503, detail="当前 Agent Workspace 不可用")
    return Path(workspace.workspace_dir)


@router.get("/orders")
async def list_orders(
    order_no: str = Query(default="", max_length=64),
    status: str = Query(default="", max_length=32),
    risk_level: str = Query(default="", max_length=8),
    ctx=Depends(get_ctx),
) -> dict[str, Any]:
    return _query(await _route_root(ctx), order_no, status, risk_level)


@router.get("/summary")
async def summary(ctx=Depends(get_ctx)) -> dict[str, Any]:
    return _query(await _route_root(ctx))["summary"]


app = PawApp(name="订单与交付风险", app_id="zhiyun-orders")
app.include_router(router)


@app.tool("orders_query", description="查询当前企业 Workspace 的真实订单；可按订单号、状态和风险等级筛选，返回 Trace ID。", icon="📦")
async def orders_query(order_no: str = "", status: str = "", risk_level: str = "") -> dict[str, Any]:
    return _query(current_workspace(), order_no, status, risk_level)


@app.tool("orders_delivery_risk", description="分析当前企业 Workspace 的订单交付风险，返回红黄绿订单、风险原因和 Trace ID。", icon="⚠️")
async def orders_delivery_risk() -> dict[str, Any]:
    result = _query(current_workspace())
    risky = [row for row in result["orders"] if row["risk_level"] in ("红色", "黄色")]
    return {"traceId": result["traceId"], "summary": result["summary"], "riskOrders": risky, "conclusion": f"发现 {len(risky)} 个需关注订单，其中红色 {result['summary']['red']} 个、黄色 {result['summary']['yellow']} 个。"}
