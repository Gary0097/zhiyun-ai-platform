# -*- coding: utf-8 -*-
"""QwenPaw enterprise brand bridge.

Reads non-sensitive brand and health data from the enterprise control plane.
No tenant or credential is accepted from the browser in this Q1 bridge.
"""

from __future__ import annotations

import asyncio
import json
import os
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
