# -*- coding: utf-8 -*-
"""QwenPaw application discovery API and Agent tool."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from qwenpaw.plugins.api import PluginApi

try:
    from .search_engine import agent_response, load_catalog, load_progress, progress_summary, search_apps
except ImportError:
    from search_engine import agent_response, load_catalog, load_progress, progress_summary, search_apps

router = APIRouter()


@router.get("/catalog")
async def catalog() -> dict[str, Any]:
    """Return the packaged capability catalog."""
    return load_catalog()


@router.get("/search")
async def search(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=8, ge=1, le=20),
) -> dict[str, Any]:
    """Search application names, aliases, capabilities and scenarios."""
    return {"query": q, "results": search_apps(q, limit=limit)}


@router.get("/progress")
async def progress() -> dict[str, Any]:
    """Return the auditable 31-item PRD delivery ledger and summary."""
    ledger = load_progress()
    return {**ledger, "summary": progress_summary(ledger)}


def find_paw_apps(query: str, limit: int = 3) -> dict[str, Any]:
    """Find real PawApps that can complete a requested business task."""
    return agent_response(query, limit=max(1, min(limit, 5)))


class AppDiscoveryPlugin:
    """Register the App Discovery HTTP and Agent interfaces."""

    def register(self, api: PluginApi) -> None:
        api.register_http_router(
            router,
            prefix="/zhiyun-app-discovery",
            tags=["zhiyun-app-discovery"],
        )
        api.register_tool(
            tool_name="find_paw_apps",
            tool_func=find_paw_apps,
            description=(
                "Search the real local PawApp capability index when the user asks "
                "which application can complete a task. Never guess an app name."
            ),
            icon="🔎",
            tool_type="internal",
        )


plugin = AppDiscoveryPlugin()
