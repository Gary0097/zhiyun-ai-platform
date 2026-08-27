# -*- coding: utf-8 -*-
"""QwenPaw HTTP facade for the unified Data Core."""

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
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from qwenpaw.plugins.api import PluginApi

try:
    from qwenpaw.constant import WORKING_DIR as _HOST_WORKING_DIR
except ImportError:  # pragma: no cover - 单测/无宿主时
    _HOST_WORKING_DIR = None

try:
    from .data_core import DataCore, DataCoreError, default_database
    from .agent_tools import build_agent_tools
    from .table_parser import parse_table
    from .operations import DataCoreOperations, DataOperationError
except ImportError:
    from data_core import DataCore, DataCoreError, default_database
    from agent_tools import build_agent_tools
    from table_parser import parse_table
    from operations import DataCoreOperations, DataOperationError

WORKING_DIR = (
    Path(_HOST_WORKING_DIR)
    if _HOST_WORKING_DIR
    else Path(os.environ.get("QWENPAW_WORKING_DIR", Path.cwd()))
)

core = DataCore(default_database())
operations = DataCoreOperations(core.database)
def _resolve_auth_user(authorization: str) -> dict[str, Any]:
    """从 Authorization 头解析并校验登录账号；失败抛 401。"""
    username = _verify_token(_bearer_token(authorization))
    if not username:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    user = _find_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="账号不存在")
    return user


def require_auth(authorization: str = Header(default="")) -> None:
    """读接口：任何有效登录账号可用。"""
    _resolve_auth_user(authorization)


def require_admin(authorization: str = Header(default="")) -> None:
    """破坏性/运维接口：回滚、备份恢复、模拟生成等仅管理员。"""
    user = _resolve_auth_user(authorization)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")


router = APIRouter()
MAX_UPLOAD = 20 * 1024 * 1024

# ---------------------------------------------------------------------------
# 企业环境常量与鉴权 helper（与 zhiyun-app-discovery / zhiyun-enterprise-seeder 同源）。
# 刻意不 import zhiyun-enterprise-seeder，避免插件之间形成依赖循环；
# 这些常量/函数用于按账号解析企业环境，并查询应用绑定的默认智能体。
# ---------------------------------------------------------------------------
CONSOLE_CHAT_URL = "http://127.0.0.1:8088/api/console/chat"
CHAT_TIMEOUT_SECONDS = 300

ENTERPRISE_DIR = Path(os.environ.get("ZHIYUN_ENTERPRISE_DIR", WORKING_DIR / "enterprise"))
ENTERPRISE_DB = ENTERPRISE_DIR / "enterprise.db"
AUTH_USERS_FILE = WORKING_DIR / "auth" / "users.json"
AUTH_SECRET_FILE = WORKING_DIR / "auth" / "token_secret.txt"
CONFIG_FILE = WORKING_DIR / "config.json"

# 面向数据中心的默认系统上下文：注入一次，让模型知晓可调用 query_enterprise_orders。
APP_CONTEXT = (
    "你是「制造云 AI OS」统一数据中心的智能体助手。"
    "你可以调用 `query_enterprise_orders` 工具查询企业订单、客户、状态和交付进度；"
    "当用户询问订单数据、生产进度或数据概览时，请先调用该工具再回答；"
    "不要凭空编造业务数据。如果问题与本数据中心无关，请如实说明。"
)

class FieldCreate(BaseModel):
    name: str
    label: str
    field_type: str = "text"
    required: bool = False


class FieldPatch(BaseModel):
    label: str | None = None
    active: bool | None = None


class SchemaFieldCreate(BaseModel):
    name: str
    label: str
    field_type: str = "text"
    required: bool = False


class SchemaCreate(BaseModel):
    entity: str
    label: str
    fields: list[SchemaFieldCreate] = Field(min_length=1, max_length=100)


class ImportPreview(BaseModel):
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=10000)
    mapping: dict[str, str] | None = None
    source_name: str = "manual-import"


class SimulationCreate(BaseModel):
    count: int = Field(default=50, ge=1, le=5000)
    seed: int | None = None


class BackupCreate(BaseModel):
    key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,100}$")


class BackupRestore(BaseModel):
    confirmed: bool = False
    key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,100}$")


class ContextSet(BaseModel):
    env_id: str | None = None
    data_mode: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class AgentChatRequest(BaseModel):
    """Client payload for the streaming in-app agent chat."""

    text: str = Field(min_length=1, max_length=4000, description="User message")
    session_id: str | None = Field(default=None, description="Persistent conversation id")
    user_id: str | None = Field(default="default", description="Calling user id")
    app_id: str | None = Field(default="zhiyun-data-core")
    # 系统上下文与多轮历史必须受到长度约束，避免 API 调用方注入超大上下文/
    # 海量轮次导致后端模型上下文溢出或过度消耗 Token（与 UI 的 12 轮上限保持兼容）。
    context: str | None = Field(default=None, max_length=8000, description="Optional system context")
    history: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=24,
        description="Prior turns [{role, text}] for multi-turn context",
    )


def _mode_q(value: str | None) -> str | None:
    """Map an optional data environment query param; empty means 'all'."""
    if value is None or value == "":
        return None
    return value


def _mode_required(value: str | None) -> str:
    """Normalize a data environment query for writes, defaulting to demo."""
    if value is None or value == "":
        return "demo"
    return value


def _handle(action):
    try:
        return action()
    except DataCoreError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/health")
async def health() -> dict[str, Any]:
    return {**operations.health(), "version": "0.8.0", "database": str(core.database),
            "migrations": core.migration_history()}


@router.get("/backups", dependencies=[Depends(require_admin)])
async def backups() -> dict[str, Any]:
    return {"backups": operations.list_backups()}


@router.post("/backups", dependencies=[Depends(require_admin)])
async def create_backup(request: BackupCreate) -> dict[str, Any]:
    try:
        return operations.create_backup(key_env=request.key_env)
    except DataOperationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/backups/{name}/restore", dependencies=[Depends(require_admin)])
async def restore_backup(name: str, request: BackupRestore) -> dict[str, Any]:
    try:
        return operations.restore_backup(name, confirmed=request.confirmed, key_env=request.key_env)
    except DataOperationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/context", dependencies=[Depends(require_auth)])
async def read_context() -> dict[str, Any]:
    return {"context": core.get_context()}


@router.put("/context", dependencies=[Depends(require_auth)])
async def write_context(request: ContextSet) -> dict[str, Any]:
    return _handle(
        lambda: {
            "context": core.set_context(
                env_id=request.env_id or "",
                data_mode=request.data_mode or "",
                start_date=request.start_date or "",
                end_date=request.end_date or "",
            )
        }
    )

@router.get("/entities", dependencies=[Depends(require_auth)])
async def entities(data_mode: str | None = Query(default=None, max_length=20)) -> dict[str, Any]:
    return {"entities": core.list_entities(data_mode=_mode_q(data_mode))}


@router.post("/parse", dependencies=[Depends(require_auth)])
async def parse_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="文件不能超过20MB")
    try:
        return parse_table(file.filename or "upload", content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/schemas", dependencies=[Depends(require_auth)])
async def create_schema(request: SchemaCreate) -> dict[str, Any]:
    return _handle(
        lambda: core.create_schema(
            request.entity,
            request.label,
            [field.model_dump() for field in request.fields],
        )
    )


@router.get("/schemas/{entity}", dependencies=[Depends(require_auth)])
async def schema(entity: str) -> dict[str, Any]:
    return _handle(lambda: core.list_schema(entity))


@router.post("/schemas/{entity}/fields", dependencies=[Depends(require_auth)])
async def add_field(entity: str, request: FieldCreate) -> dict[str, Any]:
    return _handle(
        lambda: core.add_field(entity, request.name, request.label, request.field_type, request.required)
    )


@router.patch("/schemas/{entity}/fields/{field_name}")
async def update_field(entity: str, field_name: str, request: FieldPatch) -> dict[str, Any]:
    return _handle(
        lambda: core.update_field(entity, field_name, label=request.label, active=request.active)
    )


@router.post("/imports/{entity}/preview", dependencies=[Depends(require_auth)])
async def preview_import(entity: str, request: ImportPreview) -> dict[str, Any]:
    return _handle(lambda: core.preview_import(entity, request.rows, request.mapping))


@router.post("/imports/{entity}/commit", dependencies=[Depends(require_auth)])
async def commit_import(
    entity: str, request: ImportPreview, data_mode: str | None = Query(default=None, max_length=20)
) -> dict[str, Any]:
    return _handle(
        lambda: core.import_rows(
            entity,
            request.rows,
            mapping=request.mapping,
            source_name=request.source_name,
            data_mode=_mode_required(data_mode),
        )
    )


@router.post("/simulate/orders", dependencies=[Depends(require_admin)])
async def simulate_orders(
    request: SimulationCreate, data_mode: str | None = Query(default=None, max_length=20)
) -> dict[str, Any]:
    return _handle(lambda: core.generate_orders(request.count, request.seed, data_mode=_mode_required(data_mode)))


@router.post("/simulate/production", dependencies=[Depends(require_admin)])
async def simulate_production(
    request: SimulationCreate, data_mode: str | None = Query(default=None, max_length=20)
) -> dict[str, Any]:
    return _handle(lambda: core.generate_production(request.count, request.seed, data_mode=_mode_required(data_mode)))


@router.get("/records/{entity}", dependencies=[Depends(require_auth)])
async def records(
    entity: str,
    limit: int = Query(default=100, ge=1, le=1000),
    source_type: str | None = None,
    data_mode: str | None = Query(default=None, max_length=20),
    start_date: str | None = Query(default=None, max_length=16),
    end_date: str | None = Query(default=None, max_length=16),
) -> dict[str, Any]:
    return _handle(
        lambda: {
            "entity": entity,
            "records": core.list_records(
                entity,
                limit=limit,
                source_type=source_type,
                data_mode=_mode_q(data_mode),
                start_date=start_date,
                end_date=end_date,
            ),
        }
    )

@router.get("/orders", dependencies=[Depends(require_auth)])
async def orders(
    keyword: str = Query(default="", max_length=200),
    order_no: str = Query(default="", max_length=200),
    customer_name: str = Query(default="", max_length=200),
    status: str = Query(default="", max_length=200),
    source_type: str | None = Query(default=None),
    data_mode: str | None = Query(default=None, max_length=20),
    start_date: str | None = Query(default=None, max_length=16),
    end_date: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    """Expose the bounded order query contract used by business PawApps."""
    filters = {
        key: value
        for key, value in {
            "order_no": order_no,
            "customer_name": customer_name,
            "status": status,
        }.items()
        if value
    }
    def query() -> dict[str, Any]:
        records = core.search_records(
            "orders",
            keyword=keyword,
            filters=filters,
            source_type=source_type,
            data_mode=_mode_q(data_mode),
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        return {
            "entity": "orders",
            "count": len(records),
            "keyword": keyword,
            "filters": filters,
            "source_type": source_type,
            "data_mode": data_mode,
            "start_date": start_date,
            "end_date": end_date,
            "records": records,
        }
    return _handle(query)

@router.get("/batches", dependencies=[Depends(require_auth)])
async def batches(
    entity: str | None = None, data_mode: str | None = Query(default=None, max_length=20)
) -> dict[str, Any]:
    return {"batches": core.list_batches(entity, data_mode=_mode_q(data_mode))}


@router.post("/batches/{batch_id}/rollback", dependencies=[Depends(require_admin)])
async def rollback(batch_id: str) -> dict[str, Any]:
    return _handle(lambda: core.rollback_batch(batch_id))


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
    is_admin = str(user.get("role") or "") == "admin"
    if not env_id or not data_mode:
        enterprise = str(user.get("enterprise") or "")
        try:
            conn = _connect()
            try:
                row = conn.execute(
                    "SELECT env_id, data_mode FROM enterprise_meta WHERE enterprise = ? ORDER BY id DESC LIMIT 1",
                    (enterprise,),
                ).fetchone()
                if row:
                    if not env_id:
                        env_id = row["env_id"]
                    if not data_mode:
                        data_mode = row["data_mode"]
                # 系统管理员可能早于企业初始化创建，因此账号记录中没有
                # 固定 env_id。管理员可使用当前最新企业环境；普通账号仍
                # 必须精确匹配自身企业，避免跨企业读取。
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
    session_id = body.session_id or f"zhiyun-data-core-{uuid4().hex}"

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
    app_id = body.app_id or "zhiyun-data-core"
    if user.get("role") != "admin":
        _require_app_access(user, env_id, data_mode, app_id)

    # 4. 应用对应的企业默认智能体（绑定数据中心到种子默认智能体）
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


class DataCorePlugin:
    """Register a private, same-origin Data Core API without another port."""

    def register(self, api: PluginApi) -> None:
        api.register_http_router(router, prefix="/zhiyun-data-core", tags=["zhiyun-data-core"])
        query_orders, simulate_orders_tool = build_agent_tools(core)
        api.register_tool(
            tool_name="query_enterprise_orders",
            tool_func=query_orders,
            description="查询统一数据库中的企业订单、客户、状态和交付进度；回答订单问题时优先调用。",
            icon="🔎",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="generate_simulated_production",
            tool_func=lambda count=60, seed=None: core.generate_production(count, seed),
            description="按用户明确要求生成可撤销的演示生产日报，用于测试部门人效、成本和损耗指标。",
            icon="🏭",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="generate_simulated_orders",
            tool_func=simulate_orders_tool,
            description="按用户明确要求生成可撤销的演示订单数据，并返回批次 ID。",
            icon="🧪",
            tool_type="internal",
        )


plugin = DataCorePlugin()
