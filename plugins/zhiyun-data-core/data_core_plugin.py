# -*- coding: utf-8 -*-
"""QwenPaw HTTP facade for the unified Data Core."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

try:
    from fastapi import APIRouter, File, HTTPException, Header, Query, UploadFile
except ImportError:  # pragma: no cover - 系统 Python 无宿主依赖时提供桩实现
    class APIRouter:
        def get(self, path, **kwargs): return lambda fn: fn
        def post(self, path, **kwargs): return lambda fn: fn
        def put(self, path, **kwargs): return lambda fn: fn
        def patch(self, path, **kwargs): return lambda fn: fn
        def delete(self, path, **kwargs): return lambda fn: fn

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = ""):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    def Header(default=None, **kwargs): return default
    def Query(default=None, **kwargs): return default
    def File(default=None, **kwargs): return default

    class UploadFile:
        pass

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - 系统 Python 无 pydantic 时提供桩实现
    class BaseModel:
        def model_dump(self) -> dict[str, Any]:
            return dict(getattr(self, "__dict__", {}))
    def Field(default=None, **kwargs): return default

try:
    from qwenpaw.plugins.api import PluginApi
except ImportError:  # pragma: no cover - 单元测试时可能没有宿主
    PluginApi = object  # type: ignore[assignment, misc]

try:
    from .data_core import DataCore, DataCoreError, default_database
    from .table_parser import parse_table
    from .operations import DataCoreOperations, DataOperationError
except ImportError:
    from data_core import DataCore, DataCoreError, default_database
    from table_parser import parse_table
    from operations import DataCoreOperations, DataOperationError

try:
    from .agent_tools import build_agent_tools
except ImportError:
    try:
        from agent_tools import build_agent_tools
    except ImportError:  # pragma: no cover - 系统 Python 无 agentscope 时提供桩实现
        def build_agent_tools(core):
            return (lambda *args, **kwargs: None), (lambda *args, **kwargs: None)


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

core = DataCore(default_database())
operations = DataCoreOperations(core.database)
router = APIRouter()
MAX_UPLOAD = 20 * 1024 * 1024


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


@router.get("/backups")
async def backups(authorization: str = Header(default="")) -> dict[str, Any]:
    _require_auth(authorization)
    return {"backups": operations.list_backups()}


@router.post("/backups")
async def create_backup(request: BackupCreate, authorization: str = Header(default="")) -> dict[str, Any]:
    _require_auth(authorization)
    try:
        return operations.create_backup(key_env=request.key_env)
    except DataOperationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/backups/{name}/restore")
async def restore_backup(name: str, request: BackupRestore, authorization: str = Header(default="")) -> dict[str, Any]:
    _require_auth(authorization)
    try:
        return operations.restore_backup(name, confirmed=request.confirmed, key_env=request.key_env)
    except DataOperationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/context")
async def read_context(authorization: str = Header(default="")) -> dict[str, Any]:
    _require_auth(authorization)
    return {"context": core.get_context()}


@router.put("/context")
async def write_context(request: ContextSet, authorization: str = Header(default="")) -> dict[str, Any]:
    _require_auth(authorization)
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


@router.get("/entities")
async def entities(
    data_mode: str | None = Query(default=None, max_length=20),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    _require_auth(authorization)
    return {"entities": core.list_entities(data_mode=_mode_q(data_mode))}


@router.post("/parse")
async def parse_upload(
    file: UploadFile = File(...),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    _require_auth(authorization)
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="文件不能超过20MB")
    try:
        return parse_table(file.filename or "upload", content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/schemas")
async def create_schema(request: SchemaCreate, authorization: str = Header(default="")) -> dict[str, Any]:
    _require_auth(authorization)
    return _handle(
        lambda: core.create_schema(
            request.entity,
            request.label,
            [field.model_dump() for field in request.fields],
        )
    )


@router.get("/schemas/{entity}")
async def schema(entity: str, authorization: str = Header(default="")) -> dict[str, Any]:
    _require_auth(authorization)
    return _handle(lambda: core.list_schema(entity))


@router.post("/schemas/{entity}/fields")
async def add_field(
    entity: str,
    request: FieldCreate,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    _require_auth(authorization)
    return _handle(
        lambda: core.add_field(entity, request.name, request.label, request.field_type, request.required)
    )


@router.patch("/schemas/{entity}/fields/{field_name}")
async def update_field(
    entity: str,
    field_name: str,
    request: FieldPatch,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    _require_auth(authorization)
    return _handle(
        lambda: core.update_field(entity, field_name, label=request.label, active=request.active)
    )


@router.post("/imports/{entity}/preview")
async def preview_import(
    entity: str,
    request: ImportPreview,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    _require_auth(authorization)
    return _handle(lambda: core.preview_import(entity, request.rows, request.mapping))


@router.post("/imports/{entity}/commit")
async def commit_import(
    entity: str,
    request: ImportPreview,
    data_mode: str | None = Query(default=None, max_length=20),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    _require_auth(authorization)
    return _handle(
        lambda: core.import_rows(
            entity,
            request.rows,
            mapping=request.mapping,
            source_name=request.source_name,
            data_mode=_mode_required(data_mode),
        )
    )


@router.post("/simulate/orders")
async def simulate_orders(
    request: SimulationCreate,
    data_mode: str | None = Query(default=None, max_length=20),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    _require_auth(authorization)
    return _handle(lambda: core.generate_orders(request.count, request.seed, data_mode=_mode_required(data_mode)))


@router.post("/simulate/production")
async def simulate_production(
    request: SimulationCreate,
    data_mode: str | None = Query(default=None, max_length=20),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    _require_auth(authorization)
    return _handle(lambda: core.generate_production(request.count, request.seed, data_mode=_mode_required(data_mode)))


@router.get("/records/{entity}")
async def records(
    entity: str,
    limit: int = Query(default=100, ge=1, le=1000),
    source_type: str | None = None,
    data_mode: str | None = Query(default=None, max_length=20),
    start_date: str | None = Query(default=None, max_length=16),
    end_date: str | None = Query(default=None, max_length=16),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    _require_auth(authorization)
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


@router.get("/orders")
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
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    """Expose the bounded order query contract used by business PawApps."""
    _require_auth(authorization)
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


@router.get("/batches")
async def batches(
    entity: str | None = None,
    data_mode: str | None = Query(default=None, max_length=20),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    _require_auth(authorization)
    return {"batches": core.list_batches(entity, data_mode=_mode_q(data_mode))}


@router.post("/batches/{batch_id}/rollback")
async def rollback(batch_id: str, authorization: str = Header(default="")) -> dict[str, Any]:
    _require_auth(authorization)
    return _handle(lambda: core.rollback_batch(batch_id))


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
