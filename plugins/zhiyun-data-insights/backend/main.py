# -*- coding: utf-8 -*-
"""智能分析驾驶舱 — 前端壳插件。

分析计算与数据由 zhiyun-enterprise-seeder 的 /analytics/insights 提供；
本插件只负责以独立应用形态挂载驾驶舱页面（单插件单路由，规避
console 多路由注册不生效的问题）。
"""
from __future__ import annotations

from fastapi import APIRouter
from qwenpaw.pawapp import PawApp

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "available", "app": "zhiyun-data-insights"}


app = PawApp(name="智能分析驾驶舱", app_id="zhiyun-data-insights")
app.include_router(router)

plugin = app
