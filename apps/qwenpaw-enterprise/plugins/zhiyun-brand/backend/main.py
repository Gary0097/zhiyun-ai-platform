# -*- coding: utf-8 -*-
"""Embedded Zhiyun brand PawApp; no external enterprise service dependency."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from qwenpaw.pawapp import PawApp

DEFAULT_BRAND = {
    "name": "智造云 AI-OS",
    "subtitle": "企业 AI 操作系统",
    "primaryColor": "#1677ff",
    "logo": "/api/zhiyun-brand/logo",
}

router = APIRouter()


@router.get("/config")
async def brand_config() -> dict[str, Any]:
    return {**DEFAULT_BRAND, "connected": True, "mode": "embedded"}


@router.get("/logo")
async def brand_logo() -> Response:
    logo = Path(__file__).resolve().parents[1] / "ui" / "logo.svg"
    return Response(content=logo.read_bytes(), media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=3600"})


app = PawApp(name="智造云企业品牌", app_id="zhiyun-brand")
app.include_router(router)
