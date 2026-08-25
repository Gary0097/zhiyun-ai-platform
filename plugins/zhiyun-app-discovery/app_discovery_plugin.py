# -*- coding: utf-8 -*-
"""QwenPaw application discovery API and Agent tool."""

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
    from fastapi import APIRouter, Header, Query
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
    from qwenpaw.constant import WORKING_DIR
    from qwenpaw.plugins.api import PluginApi
except ImportError:  # pragma: no cover - 单元测试时可能没有宿主
    WORKING_DIR = Path(os.environ.get("QWENPAW_WORKING_DIR", Path.cwd()))
    PluginApi = object  # type: ignore[assignment, misc]

try:
    from .search_engine import agent_response, load_catalog, load_progress, progress_summary, search_apps
except ImportError:
    from search_engine import agent_response, load_catalog, load_progress, progress_summary, search_apps

AUTH_DIR = WORKING_DIR / "auth"
USERS_FILE = AUTH_DIR / "users.json"
SECRET_FILE = AUTH_DIR / "token_secret.txt"

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


@router.get("/catalog")
async def catalog() -> dict[str, Any]:
    """Return the packaged capability catalog."""
    return load_catalog()


@router.get("/search")
async def search(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=8, ge=1, le=20),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    """Search application names, aliases, capabilities and scenarios."""
    _require_auth(authorization)
    return {"query": q, "results": search_apps(q, limit=limit)}


@router.get("/progress")
async def progress(authorization: str = Header(default="")) -> dict[str, Any]:
    """Return the auditable 31-item PRD delivery ledger and summary."""
    _require_auth(authorization)
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
