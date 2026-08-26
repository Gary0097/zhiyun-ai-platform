# -*- coding: utf-8 -*-
"""QwenPaw middleware that audits Tool calls without exposing reasoning.

Also exposes a real streaming agent-chat endpoint that proxies to the QwenPaw
console chat runtime so the in-app AgentDock in the Audit Center is backed by the
real model / tool loop instead of a front-end simulation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any, AsyncGenerator, Callable
from uuid import uuid4

import httpx
from agentscope.middleware import MiddlewareBase
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from qwenpaw.plugins.api import PluginApi

try:
    from qwenpaw.constant import WORKING_DIR as _HOST_WORKING_DIR
except ImportError:  # pragma: no cover - 单测/无宿主时
    _HOST_WORKING_DIR = None

WORKING_DIR = (
    Path(_HOST_WORKING_DIR)
    if _HOST_WORKING_DIR
    else Path(os.environ.get("QWENPAW_WORKING_DIR", Path.cwd()))
)

try:
    from .audit_store import list_events, persist, redact, verify_integrity
    from .risk_policy import assess
except ImportError:
    from audit_store import list_events, persist, redact, verify_integrity
    from risk_policy import assess


class HighRiskOperationBlocked(RuntimeError):
    """Raised when an Agent attempts a catastrophic irreversible operation."""


router = APIRouter()

CONSOLE_CHAT_URL = "http://127.0.0.1:8088/api/console/chat"
CHAT_TIMEOUT_SECONDS = 300

# ---------------------------------------------------------------------------
# 本地复制的企业环境常量与鉴权 helper。
# 刻意不 import zhiyun-enterprise-seeder，避免插件之间形成依赖循环；
# 这些常量/函数与 enterprise_plugin 保持同源，用于按账号解析企业环境。
# ---------------------------------------------------------------------------
ENTERPRISE_DIR = Path(os.environ.get("ZHIYUN_ENTERPRISE_DIR", WORKING_DIR / "enterprise"))
ENTERPRISE_DB = ENTERPRISE_DIR / "enterprise.db"
AUTH_USERS_FILE = WORKING_DIR / "auth" / "users.json"
AUTH_SECRET_FILE = WORKING_DIR / "auth" / "token_secret.txt"
CONFIG_FILE = WORKING_DIR / "config.json"

APP_CONTEXT = (
    "你是「制造云 AI OS」安全审计中心的智能体助手。"
    "你可以调用 `query_audit_events` 工具检索真实的脱敏审计记录，"
    "以及调用 `verify_audit_integrity` 工具验证审计链完整性。"
    "当用户询问失败/被阻断的操作、审计链状态、某个 Tool 或 Agent 的执行记录时，"
    "请先调用这些真实工具，再基于返回结果回答；不要凭空编造审计记录或结论。"
    "审计记录仅包含脱敏元数据，不包含原始输入、密钥或模型推理。"
)


class AgentChatRequest(BaseModel):
    """Client payload for the streaming in-app agent chat."""

    text: str = Field(min_length=1, max_length=4000, description="User message")
    session_id: str | None = Field(default=None, description="Persistent conversation id")
    user_id: str | None = Field(default="default", description="Calling user id")
    app_id: str | None = Field(default="zhiyun-audit")
    # 系统上下文与多轮历史必须受到长度约束，避免 API 调用方注入超大上下文/
    # 海量轮次导致后端模型上下文溢出或过度消耗 Token（与 UI 的 12 轮上限保持兼容）。
    context: str | None = Field(default=None, max_length=8000, description="Optional system context")
    history: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=24,
        description="Prior turns [{role, text}] for multi-turn context",
    )


@router.get("/integrity")
async def integrity() -> dict[str, Any]:
    return verify_integrity(_workspace())


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


# ---------------------------------------------------------------------------
# 企业环境读取工具（与 zhiyun-enterprise-seeder 同源）
# ---------------------------------------------------------------------------


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return date.today().isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return default


def _connect() -> sqlite3.Connection:
    ENTERPRISE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ENTERPRISE_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _bearer_token(authorization: str) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    return ""


def _token_secret() -> str:
    try:
        if AUTH_SECRET_FILE.is_file():
            val = AUTH_SECRET_FILE.read_text(encoding="utf-8").strip()
            if val:
                return val
    except OSError:
        pass
    secret = secrets.token_hex(32)
    AUTH_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret


def _read_auth_users() -> list[dict[str, Any]]:
    data = _read_json(AUTH_USERS_FILE, [])
    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict):
        return list(data.get("users") or [])
    return []


def _find_user(username: str) -> dict[str, Any] | None:
    for user in _read_auth_users():
        if user.get("username") == username:
            return user
    return None


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


def _normalize_mode(data_mode: str) -> str:
    if data_mode == "live":
        return "production"
    if data_mode in ("demo", "production"):
        return data_mode
    return ""


def _user_env(user: dict[str, Any]) -> tuple[str, str]:
    """返回 (env_id, data_mode)；无法解析时返回 ("", "") 交由调用方回退。"""
    env_id = str(user.get("env_id") or "")
    data_mode = str(user.get("data_mode") or "")
    if env_id and data_mode:
        return env_id, data_mode
    enterprise = str(user.get("enterprise") or "")
    is_admin = str(user.get("role") or "") == "admin"
    try:
        conn = _connect()
        try:
            if not env_id or not data_mode:
                row = conn.execute(
                    "SELECT env_id, data_mode FROM enterprise_meta WHERE enterprise = ? ORDER BY id DESC LIMIT 1",
                    (enterprise,),
                ).fetchone()
                if row:
                    if not env_id:
                        env_id = row["env_id"]
                    if not data_mode:
                        data_mode = row["data_mode"]
            # 管理员账号允许回退到最新企业环境（演示/生产环境），
            # 否则保持严格隔离并返回空交由调用方拒绝。
            if (not env_id or not data_mode) and is_admin:
                row = conn.execute(
                    "SELECT env_id, data_mode FROM enterprise_meta ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if row:
                    if not env_id:
                        env_id = row["env_id"]
                    if not data_mode:
                        data_mode = row["data_mode"]
        finally:
            conn.close()
    except Exception:
        pass
    return env_id, data_mode


def _lookup_app_agent(app_id: str, env_id: str, data_mode: str) -> str | None:
    """查询某应用在其企业环境里启用的默认 agent_id。"""
    if not app_id or not env_id or not data_mode:
        return None
    try:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT agent_id FROM apps "
                "WHERE app_id = ? AND env_id = ? AND data_mode = ? AND enabled = 1 "
                "ORDER BY id DESC LIMIT 1",
                (app_id, env_id, data_mode),
            ).fetchone()
            return row["agent_id"] if row else None
        finally:
            conn.close()
    except Exception:
        return None


def _user_agent_id(username: str, env_id: str = "") -> str:
    """查询账号在其企业环境里绑定的默认 agent_id（来自 org_users）。"""
    if not username or not env_id:
        return ""
    try:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT agent_id FROM org_users WHERE username = ? AND env_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (username, env_id),
            ).fetchone()
            return row["agent_id"] if row and row["agent_id"] else ""
        finally:
            conn.close()
    except Exception:
        return ""


def _require_app_access(user: dict[str, Any], env_id: str, data_mode: str, app_id: str) -> None:
    """非管理员必须拥有该应用的 agent_app_access 授权，否则返回 403。"""
    if str(user.get("role") or "") == "admin":
        return
    agent_id = _user_agent_id(str(user.get("username") or ""), env_id)
    if not agent_id:
        raise HTTPException(status_code=403, detail="无权访问该应用")
    try:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM agent_app_access "
                "WHERE env_id = ? AND data_mode = ? AND app_id = ? AND agent_id = ? "
                "AND enabled = 1 LIMIT 1",
                (env_id, data_mode, app_id, agent_id),
            ).fetchone()
            exists = row is not None
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception:
        exists = False
    if not exists:
        raise HTTPException(status_code=403, detail="无权访问该应用")


def _runtime_agent_profile(enterprise_agent_id: str) -> str:
    """把企业 agent_id 映射为合法的运行时 agent profile key。

    QwenPaw 运行时只会根据 config.json 中 ``agents.profiles`` 里 enabled 的 profile
    来切换 agent。企业侧 agent_id（如 business_analyst）通常不是 runtime profile
    key，此时返回空串，调用方不发送 X-Agent-Id，运行时回退到 default。
    """
    if not enterprise_agent_id:
        return ""
    try:
        config = _read_json(CONFIG_FILE, {}) or {}
        profiles = (config.get("agents") or {}).get("profiles") or {}
        profile = profiles.get(enterprise_agent_id)
        if profile and profile.get("enabled"):
            return enterprise_agent_id
    except Exception:
        pass
    return ""


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
        text = text[:4000]
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


def query_audit_events(
    status: str | None = None,
    tool_name: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return redacted audit metadata for the active agent workspace."""
    try:
        records = list_events(
            _workspace(),
            status=status,
            tool_name=tool_name,
            limit=max(1, min(int(limit or 100), 500)),
        )
    except (ValueError, TypeError):
        records = list_events(_workspace(), limit=100)
    return {"count": len(records), "events": records}


def verify_audit_integrity() -> dict[str, Any]:
    """Verify the audit chain integrity for the active agent workspace."""
    return verify_integrity(_workspace())


@router.post("/agent/chat")
async def agent_chat(body: AgentChatRequest, request: Request) -> StreamingResponse:
    """Proxy a user message to the real console chat and stream its SSE reply.

    The console chat already emits ``data: {...}`` SSE events.  We forward them
    verbatim (re-wrapped with the original newline framing) so the front-end can
    render token-by-token.  ``session_id`` is preserved so the same conversation
    continues across turns.

    调用方必须携带有效 zhiyun Bearer token。我们据此解析账号所属企业环境，
    并对非管理员校验该应用在 ``agent_app_access`` 中的授权；然后查询该应用
    在该企业环境下绑定的默认智能体，仅当企业 agent_id 合法映射到运行时 agent
    profile 时才发送 X-Agent-Id，否则运行时回退 default。data_mode 一律使用
    账号真实环境（demo / production），不再兜底 ``real``。
    """
    session_id = body.session_id or f"zhiyun-audit-{uuid4().hex}"

    # 1. 硬鉴权：必须携带有效 zhiyun Bearer token，禁止信任调用方 body.user_id
    authorization = request.headers.get("authorization", "")
    username = _verify_token(_bearer_token(authorization))
    if not username:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    user = _find_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="账号不存在")
    user_id = username

    # 2. 解析账号所属企业环境；无法解析则拒绝
    env_id, data_mode = _user_env(user)
    data_mode = _normalize_mode(data_mode)
    if not env_id or not data_mode:
        raise HTTPException(status_code=403, detail="无法确定当前账号所属企业环境")

    # 3. 应用访问授权：非管理员必须拥有该应用的 agent_app_access 记录
    app_id = body.app_id or "zhiyun-audit"
    if user.get("role") != "admin":
        _require_app_access(user, env_id, data_mode, app_id)

    # 4. 应用对应的企业默认智能体（绑定 AuditDock 到种子默认智能体）
    enterprise_agent_id = _lookup_app_agent(app_id, env_id, data_mode) or ""
    runtime_profile = _runtime_agent_profile(enterprise_agent_id)

    payload = {
        "input": _build_input(body),
        "session_id": session_id,
        "user_id": user_id,
        "stream": True,
        "metadata": {
            "app_id": app_id,
            "source_kind": "agent_dock",
            "data_mode": data_mode,
            "enterprise_agent_id": enterprise_agent_id,
        },
    }

    headers: dict[str, str] = {}
    if runtime_profile:
        headers["X-Agent-Id"] = runtime_profile

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async with httpx.AsyncClient(timeout=CHAT_TIMEOUT_SECONDS) as client:
                async with client.stream(
                    "POST",
                    CONSOLE_CHAT_URL,
                    json=payload,
                    headers=headers,
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


class AuditPlugin:
    def register(self, api: PluginApi) -> None:
        api.register_http_router(router, prefix="/zhiyun-audit", tags=["zhiyun-audit"])
        api.register_middleware(_factory, priority=40)
        api.register_tool(
            tool_name="query_audit_events",
            tool_func=query_audit_events,
            description=(
                "Search real redacted audit records for the active workspace. "
                "Filters by status (success/failed/blocked) or tool name. "
                "Use when the user asks about failed or blocked operations, "
                "an Agent's executions, or a specific Tool's audit trail."
            ),
            icon="🛡️",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="verify_audit_integrity",
            tool_func=verify_audit_integrity,
            description=(
                "Verify the audit chain integrity of the active workspace. "
                "Use when the user asks whether the audit log has been tampered "
                "with or to confirm the audit chain is valid."
            ),
            icon="🔒",
            tool_type="internal",
        )


plugin = AuditPlugin()