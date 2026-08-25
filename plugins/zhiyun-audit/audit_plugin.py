# -*- coding: utf-8 -*-
"""QwenPaw middleware that audits Tool calls without exposing reasoning."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

try:
    from agentscope.middleware import MiddlewareBase
except ImportError:  # pragma: no cover - 系统 Python 无宿主依赖时提供桩实现
    class MiddlewareBase:
        pass

try:
    from fastapi import APIRouter, Header, HTTPException, Query
except ImportError:  # pragma: no cover - 系统 Python 无宿主依赖时提供桩实现
    class APIRouter:
        def get(self, path): return lambda fn: fn
        def post(self, path): return lambda fn: fn
        def put(self, path): return lambda fn: fn
        def patch(self, path): return lambda fn: fn
        def delete(self, path): return lambda fn: fn
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = ""):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)
    def Header(default=None): return default
    def Query(default=None, **kwargs): return default

try:
    from qwenpaw.plugins.api import PluginApi
except ImportError:  # pragma: no cover - 单元测试时可能没有宿主
    PluginApi = object  # type: ignore[assignment, misc]

try:
    from .audit_store import list_events, persist, redact, verify_integrity
    from .risk_policy import assess
except ImportError:
    from audit_store import list_events, persist, redact, verify_integrity
    from risk_policy import assess


def _working_dir() -> Path:
    try:
        from qwenpaw.constant import WORKING_DIR

        return Path(WORKING_DIR)
    except ImportError:
        return Path(os.environ.get("QWENPAW_WORKING_DIR", Path.home() / ".qwenpaw"))


WORKING_DIR = _working_dir()
AUTH_DIR = WORKING_DIR / "auth"
USERS_FILE = AUTH_DIR / "users.json"
SECRET_FILE = AUTH_DIR / "token_secret.txt"


class HighRiskOperationBlocked(RuntimeError):
    """Raised when an Agent attempts a catastrophic irreversible operation."""


router = APIRouter()


# ---------------------------------------------------------------------------
# 登录鉴权（与 zhiyun-auth 共用同一 token secret 与用户文件）
# ---------------------------------------------------------------------------


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return default


def _find_user(username: str) -> dict[str, Any] | None:
    data = _read_json(USERS_FILE, [])
    if isinstance(data, list):
        users = data
    elif isinstance(data, dict):
        users = data.get("users") or []
    else:
        users = []
    for user in users:
        if user.get("username") == username:
            return user
    return None


def _token_secret() -> str:
    try:
        if SECRET_FILE.is_file():
            val = SECRET_FILE.read_text(encoding="utf-8").strip()
            if val:
                return val
    except OSError:
        pass
    secret = secrets.token_hex(32)
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret


def _bearer_token(authorization: str) -> str:
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return ""


def _verify_token(token: str) -> str | None:
    try:
        b64, sig = token.split(".", 1)
        secret = _token_secret()
        if not secret:
            return None
        expected = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(b64.encode("ascii")))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        username = str(payload.get("sub") or "")
        user = _find_user(username)
        if not user or not user.get("active", True):
            return None
        return username
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _require_auth(authorization: str) -> str:
    username = _verify_token(_bearer_token(authorization))
    if not username:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return username


@router.get("/integrity")
async def integrity() -> dict[str, Any]:
    return verify_integrity(_workspace())


@router.get("/events")
async def events(
    status: str | None = Query(default=None),
    tool_name: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    """Return redacted audit metadata without Tool inputs or model reasoning."""
    _require_auth(authorization)
    try:
        records = list_events(_workspace(), status=status, tool_name=tool_name, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"count": len(records), "events": records}


def _workspace() -> Path:
    """Locate the directory that actually owns per-agent audit events.

    The audit middleware is built from ``ctx.workspace_dir``, which QwenPaw
    resolves to a per-agent workspace such as
    ``<working>/workspace/workspaces/<agent>``.  It persists events there.
    The system audit page is served by a stateless HTTP router without agent
    context, so it must discover that same directory instead of assuming a
    shared ``<working>/workspace`` root that the middleware never writes to.
    """
    try:
        from qwenpaw.constant import WORKING_DIR

        base = Path(WORKING_DIR)
    except ImportError:
        base = Path.home() / ".qwenpaw"

    # Per-agent workspaces live under <working>/workspace/workspaces/<agent>.
    # When several exist, prefer the one whose audit trail was touched most
    # recently so the page follows the active agent's writes.
    agents_root = base / "workspaces"
    candidates: list[tuple[float, Path]] = []
    if agents_root.is_dir():
        for child in agents_root.iterdir():
            audit = child / "logs" / "audit.jsonl"
            if not audit.is_file():
                continue
            try:
                mtime = audit.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, child))
    if candidates:
        candidates.sort(key=lambda entry: entry[0], reverse=True)
        return candidates[0][1]

    # No per-agent audit yet: fall back to the conventional shared workspace
    # root used by Data Core (<working>/workspace) so the page stays usable.
    return base / "workspace"


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
