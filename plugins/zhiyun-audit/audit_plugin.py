# -*- coding: utf-8 -*-
"""QwenPaw middleware that audits Tool calls without exposing reasoning."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

from agentscope.middleware import MiddlewareBase
from qwenpaw.plugins.api import PluginApi

try:
    from .audit_store import persist, redact
except ImportError:
    from audit_store import persist, redact


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
        tool_input = redact(getattr(call, "input", {}), "input")
        trace_id = f"tool-{uuid.uuid4()}"
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
        api.register_middleware(_factory, priority=40)


plugin = AuditPlugin()
