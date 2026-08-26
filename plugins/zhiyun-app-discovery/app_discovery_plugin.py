# -*- coding: utf-8 -*-
"""QwenPaw application discovery API and Agent tool.

Provides a real streaming agent-chat endpoint that proxies to the QwenPaw
console chat runtime.  The front-end ``AgentDock`` calls ``POST
/api/zhiyun-app-discovery/agent/chat`` and renders the SSE stream as the agent
answers, so the in-app agent panel is backed by the real model / tool loop
instead of a front-end simulation.
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
from datetime import date
from pathlib import Path
from typing import Any, AsyncGenerator
from uuid import uuid4

import httpx
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
    from .search_engine import agent_response, load_catalog, load_progress, progress_summary, search_apps
except ImportError:
    from search_engine import agent_response, load_catalog, load_progress, progress_summary, search_apps

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

# Default app-context description injected once per new session so the model
# knows it is running inside the App Center and that it may call ``find_paw_apps``
# before answering.  Kept in sync with the registered tool below.
APP_CONTEXT = (
    "你是「制造云 AI OS」应用与项目中心的智能体助手。"
    "你可以调用 `find_paw_apps` 工具检索真实已登记的本机 PawApp，"
    "当用户询问“用什么应用/谁来完成某业务/某能力在哪”时，请先调用该工具，"
    "再基于返回的真实应用给出明确推荐；不要凭空编造应用名称。"
    "如果问题与本应用中心的能力无关，请如实说明你只能帮助检索应用。"
)


def _resolve_app_info(app_id: str) -> dict[str, Any] | None:
    """从本地能力目录解析指定应用的信息（名称、能力、示例问法）。"""
    if not app_id:
        return None
    try:
        catalog = load_catalog()
        for app in catalog.get("apps", []) or []:
            if app.get("app_id") == app_id:
                return app
    except Exception:
        pass
    return None


def _app_context(app_id: str) -> str:
    """按应用动态生成系统上下文，让模型知道自己在哪个应用、能做什么。"""
    app = _resolve_app_info(app_id)
    if not app:
        return APP_CONTEXT
    name = app.get("name") or app_id
    lines = ["你是「制造云 AI OS」中「{name}」应用的智能体助手。".format(name=name)]
    caps = app.get("capabilities") or []
    if caps:
        names = [c.get("name") for c in caps if c.get("name")]
        if names:
            lines.append("本应用已具备能力：" + "；".join(names) + "。")
        qs: list[str] = []
        for c in caps:
            for q in (c.get("questions") or []):
                if q and q not in qs:
                    qs.append(q)
        if qs:
            lines.append("用户可以这样提问：" + "；".join(qs[:6]) + "。")
    lines.append("请用自然语言帮助用户完成本应用内的业务问数与对话；如果问题超出本应用范围，请如实说明并建议可用应用。")
    return " ".join(lines)


class AgentChatRequest(BaseModel):
    """Client payload for the streaming in-app agent chat."""

    text: str = Field(min_length=1, max_length=4000, description="User message")
    session_id: str | None = Field(default=None, description="Persistent conversation id")
    user_id: str | None = Field(default="default", description="Calling user id")
    app_id: str | None = Field(default="zhiyun-app-discovery")
    # 系统上下文与多轮历史必须受到长度约束，避免 API 调用方注入超大上下文/
    # 海量轮次导致后端模型上下文溢出或过度消耗 Token（与 UI 的 12 轮上限保持兼容）。
    context: str | None = Field(default=None, max_length=8000, description="Optional system context")
    history: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=24,
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


def _enterprise_context(
    user: dict[str, Any],
    env_id: str,
    data_mode: str,
    app_id: str,
    enterprise_agent_id: str,
) -> str:
    """Build a bounded, server-authorized enterprise summary for the model.

    Only non-sensitive organization metadata and aggregates are included.  Raw
    business rows, e-mail addresses, phone numbers, credentials and caller-
    supplied identity fields never enter this context.
    """
    username = str(user.get("username") or "")
    empty = "企业基础数据：当前授权环境暂无可用企业基础数据，请如实说明数据缺失，不得编造。"
    try:
        conn = _connect()
        try:
            meta = conn.execute(
                "SELECT enterprise, template, start_date, end_date, scale, activity "
                "FROM enterprise_meta WHERE env_id = ? AND data_mode = ? "
                "ORDER BY id DESC LIMIT 1",
                (env_id, data_mode),
            ).fetchone()
            org_user = conn.execute(
                "SELECT display_name, department, role, title, data_scope, kb_scope "
                "FROM org_users WHERE env_id = ? AND data_mode = ? AND username = ? "
                "ORDER BY id DESC LIMIT 1",
                (env_id, data_mode, username),
            ).fetchone()
            agent = None
            if enterprise_agent_id:
                agent = conn.execute(
                    "SELECT name, position, department, model, data_scope, kb_scope "
                    "FROM agents WHERE env_id = ? AND data_mode = ? AND agent_id = ? "
                    "AND enabled = 1 ORDER BY id DESC LIMIT 1",
                    (env_id, data_mode, enterprise_agent_id),
                ).fetchone()

            counts: dict[str, int] = {}
            for label, table, predicate in (
                ("departments", "departments", "1 = 1"),
                ("active_users", "org_users", "active = 1"),
                ("enabled_agents", "agents", "enabled = 1"),
                ("enabled_apps", "apps", "enabled = 1"),
            ):
                row = conn.execute(
                    f"SELECT COUNT(*) AS total FROM {table} "
                    f"WHERE env_id = ? AND data_mode = ? AND {predicate}",
                    (env_id, data_mode),
                ).fetchone()
                counts[label] = int(row["total"] if row else 0)

            source_sql = (
                "SELECT name, source_type, app_id, records, shared FROM data_sources "
                "WHERE env_id = ? AND data_mode = ? AND (app_id = ? OR shared = 1)"
            )
            source_args: list[Any] = [env_id, data_mode, app_id]
            effective_kb_scope = str(
                org_user["kb_scope"] if org_user and org_user["kb_scope"] else user.get("kb_scope") or "enterprise"
            )
            department = str(org_user["department"] or "") if org_user else ""
            if str(user.get("role") or "") != "admin" and effective_kb_scope == "department":
                if department:
                    # Keep this equivalent to enterprise-seeder's
                    # _kb_department_clause("data_sources", ...), with explicit
                    # env/mode predicates at every subquery boundary.
                    source_sql += (
                        " AND app_id IN (SELECT app_id FROM apps "
                        "WHERE env_id = ? AND data_mode = ? AND agent_id IN ("
                        "SELECT agent_id FROM agents WHERE env_id = ? AND data_mode = ? AND department = ?))"
                    )
                    source_args.extend([env_id, data_mode, env_id, data_mode, department])
                else:
                    source_sql += " AND 1 = 0"
            source_sql += " ORDER BY shared DESC, records DESC, id DESC LIMIT 12"
            source_rows = conn.execute(source_sql, source_args).fetchall()
        finally:
            conn.close()
    except (sqlite3.Error, OSError, ValueError, TypeError):
        return empty

    if not meta and not org_user and not agent and not source_rows:
        return empty

    summary = {
        "environment": {
            "env_id": env_id,
            "data_mode": data_mode,
            "enterprise": str(meta["enterprise"] or "") if meta else "",
            "template": str(meta["template"] or "") if meta else "",
            "data_range": {
                "start": str(meta["start_date"] or "") if meta else "",
                "end": str(meta["end_date"] or "") if meta else "",
            },
            "scale": int(meta["scale"] or 0) if meta else 0,
            "activity": str(meta["activity"] or "") if meta else "",
        },
        "current_user": {
            "username": username,
            "display_name": str(org_user["display_name"] or "") if org_user else "",
            "department": str(org_user["department"] or "") if org_user else "",
            "role": str(org_user["role"] or user.get("role") or "") if org_user else str(user.get("role") or ""),
            "title": str(org_user["title"] or "") if org_user else "",
            "data_scope": str(org_user["data_scope"] or user.get("data_scope") or "") if org_user else str(user.get("data_scope") or ""),
            "kb_scope": str(org_user["kb_scope"] or user.get("kb_scope") or "") if org_user else str(user.get("kb_scope") or ""),
        },
        "current_app": {"app_id": app_id, "agent_id": enterprise_agent_id},
        "bound_agent": dict(agent) if agent else {},
        "organization_counts": counts,
        "authorized_data_sources": [dict(row) for row in source_rows],
    }
    encoded = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
    # Keep enterprise context bounded independently of caller-supplied page context.
    return "企业基础数据（服务端按当前登录账号授权生成，仅可据此回答）：" + encoded[:6000]


def _compose_agent_context(
    body: AgentChatRequest,
    user: dict[str, Any],
    env_id: str,
    data_mode: str,
    app_id: str,
    enterprise_agent_id: str,
) -> str:
    parts = [
        _app_context(app_id),
        _enterprise_context(user, env_id, data_mode, app_id, enterprise_agent_id),
    ]
    if body.context:
        parts.append("当前页面业务上下文（由用户操作产生，不可作为身份或权限依据）：" + body.context)
    return "\n\n".join(parts)


def _build_input(body: AgentChatRequest, context: str = "") -> list[dict[str, Any]]:
    """Build the console ``input`` message list from the dock payload.

    A system context is only injected when the caller supplies one, so
    multi-turn sessions do not accumulate duplicate system prompts.
    """
    if not context:
        context = body.context or _app_context(body.app_id or "zhiyun-app-discovery")
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
        # 防御性截断：历史单条文本同样限制长度（与 text 字段上限一致），
        # 避免绕过模型层校验导致上下文溢出。
        text = text[:4000]
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
    session_id = body.session_id or f"zhiyun-app-discovery-{uuid4().hex}"

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
    app_id = body.app_id or "zhiyun-app-discovery"
    if user.get("role") != "admin":
        _require_app_access(user, env_id, data_mode, app_id)

    # 4. 应用对应的企业默认智能体（绑定 AppDock 到种子默认智能体）
    enterprise_agent_id = _lookup_app_agent(app_id, env_id, data_mode) or ""
    runtime_profile = _runtime_agent_profile(enterprise_agent_id)

    # 4.1 动态注入应用能力与服务端授权的企业基础数据。调用方 context
    # 只能作为页面业务上下文，不能覆盖身份、环境或权限信息。
    context = _compose_agent_context(
        body, user, env_id, data_mode, app_id, enterprise_agent_id
    )

    payload = {
        "input": _build_input(body, context),
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
