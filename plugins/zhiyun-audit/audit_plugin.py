# -*- coding: utf-8 -*-
"""QwenPaw middleware that audits Tool calls without exposing reasoning."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

from agentscope.middleware import MiddlewareBase
from fastapi import APIRouter, HTTPException, Query
from qwenpaw.plugins.api import PluginApi

try:
    from .audit_store import list_events, persist, redact
    from .risk_policy import assess
except ImportError:
    from audit_store import list_events, persist, redact
    from risk_policy import assess


class HighRiskOperationBlocked(RuntimeError):
    """Raised when an Agent attempts a catastrophic irreversible operation."""


router = APIRouter()


@router.get("/events")
async def events(
    status: str | None = Query(default=None),
    tool_name: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Return redacted audit metadata without Tool inputs or model reasoning."""
    try:
        records = list_events(_workspace(), status=status, tool_name=tool_name, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"count": len(records), "events": records}


def _workspace() -> Path:
    try:
        from qwenpaw.constant import WORKING_DIR

        return Path(WORKING_DIR) / "workspace"
    except ImportError:
        return Path.home() / ".qwenpaw" / "workspace"


class AuditMiddleware(MiddlewareBase):
    def __init__(self, workspace: Path, session_id: str, agent_id: str) -> None:
        self.workspace = workspace
        self.session_id = session_id
        self.agent_id = agent_id

    async def on_acting(
        self,
        agent: Any,
        input_kwargs: dict[str, Any],
        next_handler: Callable[..., AsyncGenerator[Any, None]],
    ) -> AsyncGenerator[Any, None]:
        del agent
        call = input_kwargs.get("tool_call")
        tool_name = str(getattr(call, "name", "unknown"))
        raw_input = getattr(call, "input", {})
        tool_input = redact(raw_input, "input")
        trace_id = f"tool-{uuid.uuid4()}"
        decision = assess(tool_name, raw_input)
        if decision.blocked:
            persist(self.workspace, {
                "trace_id": trace_id,
                "event": "tool.blocked",
                "session_id": self.session_id,
                "agent_id": self.agent_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "status": "blocked",
                "duration_ms": 0,
                "error_type": "HighRiskOperationBlocked",
                "risk_rule": decision.rule_id,
                "risk_reason": decision.reason,
            })
            raise HighRiskOperationBlocked(f"高风险操作已阻断：{decision.reason}（{decision.rule_id}）")
        started = time.perf_counter()
        status = "success"
        error_type = None
        try:
            async for item in next_handler():
                yield item
        except Exception as exc:
            status = "failed"
            error_type = type(exc).__name__
            raise
        finally:
            persist(self.workspace, {
                "trace_id": trace_id,
                "event": "tool.completed",
                "session_id": self.session_id,
                "agent_id": self.agent_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "error_type": error_type,
            })


def _factory(ctx: Any, agent_config: Any) -> AuditMiddleware | None:
    workspace = getattr(ctx, "workspace_dir", None)
    if workspace is None:
        return None
    return AuditMiddleware(
        Path(workspace),
        str(getattr(ctx, "session_id", "")),
        str(getattr(ctx, "agent_id", getattr(agent_config, "id", "default"))),
    )


class AuditPlugin:
    def register(self, api: PluginApi) -> None:
        api.register_http_router(router, prefix="/zhiyun-audit", tags=["zhiyun-audit"])
        api.register_middleware(_factory, priority=40)


plugin = AuditPlugin()
