# -*- coding: utf-8 -*-
"""QwenPaw enterprise brand bridge.

Reads non-sensitive brand and health data from the enterprise control plane.
No tenant or credential is accepted from the browser in this Q1 bridge.
"""

from __future__ import annotations

import asyncio
import json
import os
import hashlib
import hmac
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from qwenpaw.pawapp import PawApp

ENTERPRISE_BASE_URL = os.getenv(
    "ZHIYUN_ENTERPRISE_URL",
    "http://127.0.0.1:8390",
).rstrip("/")
TIMEOUT_SECONDS = 3
DEFAULT_BRAND = {
    "name": "智造云 AI-OS",
    "subtitle": "企业 AI 操作系统",
    "primaryColor": "#1677ff",
    "logo": "",
}


def _gateway_request(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    secret = os.getenv("ZHIYUN_GATEWAY_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("ZHIYUN_GATEWAY_SECRET is not configured")
    path = "/api/integrations/qwenpaw/tools/read"
    body = json.dumps({"tool": tool, "args": args}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4())
    identity = os.getenv("ZHIYUN_QWENPAW_IDENTITY", "local-admin")
    body_hash = hashlib.sha256(body).hexdigest()
    payload = "\n".join(["POST", path, timestamp, nonce, identity, body_hash]).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    req = Request(f"{ENTERPRISE_BASE_URL}{path}", data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json", "X-Zhiyun-Service": "qwenpaw",
        "X-Zhiyun-Timestamp": timestamp, "X-Zhiyun-Nonce": nonce, "X-Zhiyun-Identity": identity,
        "X-Zhiyun-Signature": signature,
    })
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as res:  # nosec B310
            return json.loads(res.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"enterprise tool gateway unavailable: {exc}") from exc


def _request(path: str, *, binary: bool = False) -> Any:
    req = Request(
        f"{ENTERPRISE_BASE_URL}{path}",
        headers={"Accept": "*/*" if binary else "application/json"},
    )
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as res:  # nosec B310
            data = res.read()
            if binary:
                return data, res.headers.get("content-type", "image/png")
            return json.loads(data.decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"enterprise service unavailable: {exc}") from exc


router = APIRouter()


@router.get("/config")
async def brand_config() -> dict[str, Any]:
    """Return the current public enterprise brand with a proxied logo URL."""
    try:
        brand = await asyncio.to_thread(_request, "/api/public/brand")
    except RuntimeError:
        return {**DEFAULT_BRAND, "connected": False}
    result = {**DEFAULT_BRAND, **brand, "connected": True}
    if result.get("logo"):
        result["logo"] = "/api/zhiyun-brand/logo"
    return result


@router.get("/logo")
async def brand_logo() -> Response:
    try:
        data, content_type = await asyncio.to_thread(
            _request,
            "/logo.png",
            binary=True,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )


app = PawApp(name="智造云企业品牌", app_id="zhiyun-brand")
app.include_router(router)


@app.tool(
    "enterprise_platform_status",
    description="读取智造云企业服务的连接状态和版本。只读，不读取业务数据。",
    icon="🏢",
)
async def enterprise_platform_status() -> dict[str, Any]:
    """Read the public control-plane health contract."""
    try:
        result = await asyncio.to_thread(_request, "/api/health")
        return {"connected": True, **result}
    except RuntimeError as exc:
        return {
            "connected": False,
            "status": "unavailable",
            "error": str(exc),
            "next_step": "确认企业服务已在 8390 端口启动",
        }


async def _read_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_gateway_request, name, args)
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}


@app.tool("enterprise_query_orders", description="查询当前企业订单、进度与交付风险。只读。", icon="📦")
async def enterprise_query_orders(order_no: str = "") -> dict[str, Any]:
    return await _read_tool("query_order", {"order_no": order_no} if order_no else {})


@app.tool("enterprise_query_inventory", description="查询当前企业库存与低库存物料。只读。", icon="🏭")
async def enterprise_query_inventory(material: str = "") -> dict[str, Any]:
    return await _read_tool("query_inventory", {"material": material} if material else {})


@app.tool("enterprise_query_customers", description="查询当前企业客户档案。只读。", icon="👥")
async def enterprise_query_customers(name: str = "") -> dict[str, Any]:
    return await _read_tool("query_customer", {"name": name} if name else {})


@app.tool("enterprise_search_knowledge", description="检索当前企业知识库。只读。", icon="📚")
async def enterprise_search_knowledge(query: str) -> dict[str, Any]:
    return await _read_tool("knowledge_search", {"query": query})
