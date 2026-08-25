# -*- coding: utf-8 -*-
"""QwenPaw application discovery API and Agent tool.

Provides a real streaming agent-chat endpoint that proxies to the QwenPaw
console chat runtime.  The front-end ``AgentDock`` calls ``POST
/api/zhiyun-app-discovery/agent/chat`` and renders the SSE stream as the agent
answers, so the in-app agent panel is backed by the real model / tool loop
instead of a front-end simulation.
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator
from uuid import uuid4

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from qwenpaw.plugins.api import PluginApi

try:
    from .search_engine import agent_response, load_catalog, load_progress, progress_summary, search_apps
except ImportError:
    from search_engine import agent_response, load_catalog, load_progress, progress_summary, search_apps

router = APIRouter()

CONSOLE_CHAT_URL = "http://127.0.0.1:8088/api/console/chat"
CHAT_TIMEOUT_SECONDS = 300

# Default app-context description injected once per new session so the model
# knows it is running inside the App Center and that it may call ``find_paw_apps``
# before answering.  Kept in sync with the registered tool below.
APP_CONTEXT = (
    "你是「智云 AI OS」应用与项目中心的智能体助手。"
    "你可以调用 `find_paw_apps` 工具检索真实已登记的本机 PawApp，"
    "当用户询问“用什么应用/谁来完成某业务/某能力在哪”时，请先调用该工具，"
    "再基于返回的真实应用给出明确推荐；不要凭空编造应用名称。"
    "如果问题与本应用中心的能力无关，请如实说明你只能帮助检索应用。"
)


class AgentChatRequest(BaseModel):
    """Client payload for the streaming in-app agent chat."""

    text: str = Field(min_length=1, max_length=4000, description="User message")
    session_id: str | None = Field(default=None, description="Persistent conversation id")
    user_id: str | None = Field(default="default", description="Calling user id")
    app_id: str | None = Field(default="zhiyun-app-discovery")
    context: str | None = Field(default=None, description="Optional system context")
    history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Prior turns [{role, text}] for multi-turn context",
    )


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


def _build_input(body: AgentChatRequest) -> list[dict[str, Any]]:
    """Build the console ``input`` message list from the dock payload.

    A system context is only injected when the caller supplies one, so
    multi-turn sessions do not accumulate duplicate system prompts.
    """
    context = body.context or APP_CONTEXT
    input_messages: list[dict[str, Any]] = []
    if context:
        input_messages.append(
            {"role": "system", "content": [{"type": "text", "text": context}]}
        )
    for turn in body.history:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        text = turn.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        # The dock stores bot messages as "bot"; map to assistant.
        mapped_role = "assistant" if role in ("bot", "assistant") else "user"
        if mapped_role == "user":
            input_messages.append(
                {"role": "user", "content": [{"type": "text", "text": text}]}
            )
        else:
            input_messages.append(
                {"role": "assistant", "content": [{"type": "text", "text": text}]}
            )
    input_messages.append(
        {"role": "user", "content": [{"type": "text", "text": body.text}]}
    )
    return input_messages


@router.post("/agent/chat")
async def agent_chat(body: AgentChatRequest) -> StreamingResponse:
    """Proxy a user message to the real console chat and stream its SSE reply.

    The console chat already emits ``data: {...}`` SSE events.  We forward them
    verbatim (re-wrapped with the original newline framing) so the front-end can
    render token-by-token.  ``session_id`` is preserved so the same conversation
    continues across turns.
    """
    session_id = body.session_id or f"zhiyun-app-discovery-{uuid4().hex}"
    user_id = body.user_id or "default"

    payload = {
        "input": _build_input(body),
        "session_id": session_id,
        "user_id": user_id,
        "stream": True,
        "metadata": {
            "app_id": body.app_id or "zhiyun-app-discovery",
            "source_kind": "agent_dock",
            "data_mode": "real",
        },
    }

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async with httpx.AsyncClient(timeout=CHAT_TIMEOUT_SECONDS) as client:
                async with client.stream(
                    "POST",
                    CONSOLE_CHAT_URL,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        text = err_body.decode("utf-8", errors="replace")
                        yield f"data: {json.dumps({'error': text})}\n\n"
                        return
                    async for line in response.aiter_lines():
                        if line == "":
                            yield "\n"
                        else:
                            yield line + "\n"
        except httpx.TimeoutException:
            yield f"data: {json.dumps({'error': '智能体响应超时，请稍后重试'})}\n\n"
        except Exception as exc:  # pragma: no cover - defensive
            yield f"data: {json.dumps({'error': f'调用智能体失败: {exc}'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
