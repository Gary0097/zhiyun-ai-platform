# -*- coding: utf-8 -*-
"""员工账号登录与权限插件（zhiyun-auth）。

独立于宿主单用户 auth.py：支持多员工账号、可自定义登录背景图与品牌名、
按用户绑定 Agent/数据范围，并写入统一数据中心的隔离上下文。

同一个运行实例视为同一家企业：企业名来自 ``WORKING_DIR/branding/login-config.json``，
一旦该实例用于另一家企业，只需在部署时更换 branding 配置并各自启动即可，
因此“不同企业独立启动系统”本插件无需额外状态。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

try:
    from fastapi import APIRouter, Header, HTTPException
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

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    class BaseModel:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
        def model_dump(self): return dict(self.__dict__)
    def Field(default=None, **kwargs): return default

try:
    from qwenpaw.constant import WORKING_DIR
    from qwenpaw.plugins.api import PluginApi
except ImportError:  # pragma: no cover - 单元测试时可能没有宿主
    WORKING_DIR = Path(os.environ.get("QWENPAW_WORKING_DIR", Path.cwd()))
    PluginApi = object  # type: ignore[assignment, misc]

PLUGIN_VERSION = "1.0.0"
AUTH_DIR = WORKING_DIR / "auth"
USERS_FILE = AUTH_DIR / "users.json"
SECRET_FILE = AUTH_DIR / "token_secret.txt"
BRANDING_DIR = WORKING_DIR / "branding"
LOGIN_CONFIG_FILE = BRANDING_DIR / "login-config.json"
CONFIG_FILE = WORKING_DIR / "config.json"

DEFAULT_ENTERPRISE = "灵泽万川智造云"
DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASSWORD = "ZhizaoYun@2026"
# rebrand 前系统默认管理员口令，仅用于升级后向后兼容轮换。
LEGACY_DEFAULT_ADMIN_PASSWORD = "Zhiyun@2026"
TOKEN_EXPIRY_SECONDS = 7 * 24 * 3600

router = APIRouter()


# ---------------------------------------------------------------------------
# 用户 / 品牌数据读写
# ---------------------------------------------------------------------------


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_users() -> list[dict[str, Any]]:
    data = _read_json(USERS_FILE, [])
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("users", list(data.get("users") or []))
    return []


def _save_users(users: list[dict[str, Any]]) -> None:
    _write_json(USERS_FILE, users)


def _login_config() -> dict[str, Any]:
    return _read_json(LOGIN_CONFIG_FILE, {})


def _brand_name() -> str:
    cfg = _login_config()
    return str(cfg.get("brand_name") or "灵泽万川智造云 AI-OS").strip() or "灵泽万川智造云 AI-OS"


def _enterprise_name() -> str:
    cfg = _login_config()
    return str(cfg.get("enterprise") or DEFAULT_ENTERPRISE).strip() or DEFAULT_ENTERPRISE


def _background_data_url() -> str:
    cfg = _login_config()
    path_value = str(cfg.get("background_image") or "")
    if path_value and Path(path_value).expanduser().is_file():
        path = Path(path_value).expanduser().resolve()
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "webp": "image/webp", "svg": "image/svg+xml"}.get(path.suffix.lstrip(".").lower(), "image/png")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    return cfg.get("background_data_url") or ""


# ---------------------------------------------------------------------------
# 密码与 Token（标准库，无外部依赖）
# ---------------------------------------------------------------------------


PBKDF2_ITERATIONS = 200_000
PBKDF2_PREFIX = "pbkdf2$"


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Return an iterated PBKDF2 hash and the salt used to derive it.

    The returned hash embeds the algorithm, iteration count, salt and digest as
    ``pbkdf2$<iterations>$<salt_hex>$<digest_hex>`` so ``_verify_password`` can
    always re-derive it without relying on the separate stored salt.
    """
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return f"{PBKDF2_PREFIX}{PBKDF2_ITERATIONS}${salt}${digest}", salt


def _verify_pbkdf2(password: str, stored_hash: str) -> bool:
    try:
        _, iterations_text, salt_hex, digest_hex = stored_hash.split("$", 3)
        iterations = int(iterations_text)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    if stored_hash.startswith(PBKDF2_PREFIX):
        return _verify_pbkdf2(password, stored_hash)
    # Legacy single-round SHA256: verify and allow the login path to upgrade it.
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, stored_hash)


def _is_legacy_hash(stored_hash: str) -> bool:
    """A hash that predates PBKDF2 and should be re-hashed after a good login."""
    return bool(stored_hash) and not stored_hash.startswith(PBKDF2_PREFIX)


def _upgrade_password_for_user(username: str, password: str) -> None:
    """Re-hash a legacy SHA256 account to PBKDF2 in place after a successful login."""
    users = _load_users()
    for user in users:
        if user.get("username") == username and _is_legacy_hash(user.get("password_hash", "")):
            pw_hash, salt = _hash_password(password)
            user["password_hash"] = pw_hash
            user["password_salt"] = salt
            _save_users(users)
            return


def _token_secret() -> str:
    """返回稳定、全局唯一的签名 secret（与用户数量无关）。

    存放到独立的 token_secret.txt，避免把 secret 塞进用户列表导致多账号时拼接
    不一致、旧 token 突然失效。
    """
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


def _create_token(username: str) -> str:
    secret = _token_secret()
    payload = json.dumps({
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_EXPIRY_SECONDS,
        "jti": uuid.uuid4().hex,
    }, ensure_ascii=False)
    b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    sig = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def _verify_token(token: str) -> str | None:
    try:
        b64, sig = token.split(".", 1)
        secret = _token_secret()
        expected = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(b64.encode("ascii")))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        username = str(payload.get("sub") or "")
        # 校验账号仍存在且启用
        user = _find_user(username)
        if not user or not user.get("active", True):
            return None
        return username
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _find_user(username: str) -> dict[str, Any] | None:
    for user in _load_users():
        if user.get("username") == username:
            return user
    return None


def _ensure_admin() -> None:
    """启动时保证存在一个默认管理员账号。

    旧版本（rebrand 前）默认口令为 Zhiyun@2026；升级后若管理员账号仍使用该旧
    默认口令，则自动轮换为新默认口令 ZhizaoYun@2026，确保文档 / 登录页展示
    的凭据仍然可用。若管理员已手动改过口令，则不触碰。
    """
    # 先让全局 secret 落盘，保证后续创建用户时签名秘钥稳定。
    _token_secret()
    users = _load_users()
    admin = next((u for u in users if u.get("username") == DEFAULT_ADMIN_USER), None)
    if admin is None:
        pw_hash, salt = _hash_password(DEFAULT_ADMIN_PASSWORD)
        users.append({
            "username": DEFAULT_ADMIN_USER,
            "display_name": "系统管理员",
            "role": "admin",
            "password_hash": pw_hash,
            "password_salt": salt,
            "enterprise": _enterprise_name(),
            "agent_id": "default",
            "data_scope": "enterprise",
            "kb_scope": "enterprise",
            "active": True,
            "created_at": _now(),
        })
        _save_users(users)
        return
    # 向后兼容轮换：仅当管理员仍使用 rebrand 前的默认口令时才更新为新口令，
    # 避免覆盖管理员已自行修改的密码。
    stored = admin.get("password_hash", "")
    salt = admin.get("password_salt", "")
    if stored and salt and _verify_password(LEGACY_DEFAULT_ADMIN_PASSWORD, stored, salt):
        pw_hash, new_salt = _hash_password(DEFAULT_ADMIN_PASSWORD)
        admin["password_hash"] = pw_hash
        admin["password_salt"] = new_salt
        _save_users(users)


def _available_agents() -> list[dict[str, Any]]:
    """读取 config.json 中的 Agent profile，用于登录后展示/绑定。"""
    cfg = _read_json(CONFIG_FILE, {})
    agents_cfg = cfg.get("agents", {}) or {}
    profiles = agents_cfg.get("profiles", {}) or {}
    order = agents_cfg.get("agent_order") or list(profiles.keys())
    active = agents_cfg.get("active_agent") or "default"
    return [{"id": pid, "active": pid == active} for pid in order]


def _set_active_agent(agent_id: str) -> dict[str, Any]:
    cfg = _read_json(CONFIG_FILE, {})
    agents = cfg.setdefault("agents", {})
    profiles = agents.setdefault("profiles", {})
    if agent_id not in profiles:
        raise ValueError("Agent 不存在")
    agents["active_agent"] = agent_id
    order = agents.setdefault("agent_order", list(profiles.keys()) or ["default"])
    if agent_id not in order:
        order.append(agent_id)
    _write_json(CONFIG_FILE, cfg)
    return {"agent_id": agent_id, "agents": [{"id": pid, "active": pid == agent_id} for pid in order]}


# ---------------------------------------------------------------------------
# Pydantic 请求体
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class ActivateAgentRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.\-]+$")


class UserUpsertRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(default="", max_length=200)
    display_name: str = Field(default="", max_length=120)
    role: str = Field(default="member", pattern=r"^(admin|member)$")
    agent_id: str = Field(default="default", max_length=120)
    data_scope: str = Field(default="enterprise", max_length=80)
    kb_scope: str = Field(default="enterprise", max_length=80)
    active: bool = True


class BrandingRequest(BaseModel):
    brand_name: str = Field(default="", max_length=120)
    enterprise: str = Field(default="", max_length=120)
    background_image: str = Field(default="", max_length=512)
    background_data_url: str = Field(default="", max_length=2_000_000)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@router.get("/config")
async def config() -> dict[str, Any]:
    return {
        "version": PLUGIN_VERSION,
        "brand_name": _brand_name(),
        "enterprise": _enterprise_name(),
        "background_data_url": _background_data_url(),
        "default_account_hint": DEFAULT_ADMIN_USER,
        "auth_required": True,
        "agents": _available_agents(),
    }


@router.post("/login")
async def login(request: LoginRequest) -> dict[str, Any]:
    user = _find_user(request.username.strip())
    if not user or not user.get("active", True) or not _verify_password(
            request.password, user.get("password_hash", ""), user.get("password_salt", "")):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    _upgrade_password_for_user(request.username.strip(), request.password)
    token = _create_token(user["username"])
    return {
        "token": token,
        "user": {
            "username": user["username"],
            "display_name": user.get("display_name") or user["username"],
            "role": user.get("role", "member"),
            "enterprise": user.get("enterprise") or _enterprise_name(),
            "agent_id": user.get("agent_id", "default"),
            "data_scope": user.get("data_scope", "enterprise"),
            "kb_scope": user.get("kb_scope", "enterprise"),
        },
        "agents": _available_agents(),
    }


@router.get("/me")
async def me(authorization: str = Header(default="")) -> dict[str, Any]:
    token = _bearer_token(authorization)
    username = _verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    user = _find_user(username)
    return {
        "user": {
            "username": user["username"],
            "display_name": user.get("display_name") or user["username"],
            "role": user.get("role", "member"),
            "enterprise": user.get("enterprise") or _enterprise_name(),
            "agent_id": user.get("agent_id", "default"),
            "data_scope": user.get("data_scope", "enterprise"),
            "kb_scope": user.get("kb_scope", "enterprise"),
        },
        "agents": _available_agents(),
        "brand_name": _brand_name(),
        "enterprise": _enterprise_name(),
    }


@router.post("/agents/activate")
async def activate_agent(request: ActivateAgentRequest, authorization: str = Header(default="")) -> dict[str, Any]:
    token = _bearer_token(authorization)
    username = _verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    user = _find_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="账号不存在")
    allowed = user.get("agent_id") == request.agent_id or user.get("role") == "admin"
    if not allowed:
        raise HTTPException(status_code=403, detail="当前账号无权切换到该 Agent")
    try:
        return _set_active_agent(request.agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/users")
async def list_users(authorization: str = Header(default="")) -> dict[str, Any]:
    username = _require_admin(authorization)
    users = _load_users()
    rows = []
    for user in users:
        rows.append({
            "username": user.get("username"),
            "display_name": user.get("display_name") or user.get("username"),
            "role": user.get("role", "member"),
            "agent_id": user.get("agent_id", "default"),
            "data_scope": user.get("data_scope", "enterprise"),
            "kb_scope": user.get("kb_scope", "enterprise"),
            "active": user.get("active", True),
            "created_at": user.get("created_at", ""),
        })
    return {"users": rows, "current": username}


@router.post("/users")
async def upsert_user(request: UserUpsertRequest, authorization: str = Header(default="")) -> dict[str, Any]:
    _require_admin(authorization)
    users = _load_users()
    existing = next((u for u in users if u.get("username") == request.username), None)
    if existing:
        # 仅管理员可改角色；保留原密码，除非显式传入新密码。
        if (
            existing.get("role") == "admin"
            and request.role != "admin"
            and not any(
                u.get("username") != request.username
                and u.get("role") == "admin"
                and u.get("active", True)
                for u in users
            )
        ):
            raise HTTPException(status_code=400, detail="不能降级最后一个启用中的管理员，请先创建其他管理员")
        if request.password:
            pw_hash, salt = _hash_password(request.password)
            existing["password_hash"] = pw_hash
            existing["password_salt"] = salt
        if request.display_name:
            existing["display_name"] = request.display_name
        existing["role"] = request.role
        existing["agent_id"] = request.agent_id
        existing["data_scope"] = request.data_scope
        existing["kb_scope"] = request.kb_scope
        existing["active"] = request.active
        _save_users(users)
        return {"ok": True, "updated": request.username}
    if len(request.password) < 6:
        raise HTTPException(status_code=422, detail="新账号密码至少 6 位")
    pw_hash, salt = _hash_password(request.password)
    users.append({
        "username": request.username,
        "display_name": request.display_name or request.username,
        "role": request.role,
        "password_hash": pw_hash,
        "password_salt": salt,
        "enterprise": _enterprise_name(),
        "agent_id": request.agent_id,
        "data_scope": request.data_scope,
        "kb_scope": request.kb_scope,
        "active": request.active,
        "created_at": _now(),
    })
    _save_users(users)
    return {"ok": True, "created": request.username}


@router.patch("/branding")
async def update_branding(request: BrandingRequest, authorization: str = Header(default="")) -> dict[str, Any]:
    _require_admin(authorization)
    cfg = _login_config()
    if request.brand_name is not None:
        cfg["brand_name"] = request.brand_name.strip()
    if request.enterprise is not None:
        cfg["enterprise"] = request.enterprise.strip()
    # 空字符串视为“不修改”，避免仅保存名称/Logo 时误清空已有封面；
    # 但上传了新封面数据时必须清掉旧的 background_image 路径，否则旧路径优先级更高
    if request.background_image:
        cfg["background_image"] = request.background_image.strip()
    if request.background_data_url:
        cfg["background_data_url"] = request.background_data_url.strip()
        cfg["background_image"] = ""
    _write_json(LOGIN_CONFIG_FILE, cfg)
    return {"ok": True, "config": {
        "brand_name": _brand_name(),
        "enterprise": _enterprise_name(),
        "background_data_url": _background_data_url(),
    }}


def _bearer_token(authorization: str) -> str:
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return ""


def _require_admin(authorization: str) -> str:
    username = _verify_token(_bearer_token(authorization))
    if not username:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    user = _find_user(username)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return username


def _startup() -> None:
    _ensure_admin()


class AuthPlugin:
    def register(self, api: PluginApi) -> None:
        api.register_http_router(router, prefix="/zhiyun-auth", tags=["zhiyun-auth"])
        api.register_startup_hook(hook_name="zhiyun-auth-init", callback=_startup, priority=0)


plugin = AuthPlugin()
