# -*- coding: utf-8 -*-
"""Small, isolated header-logo plugin for QwenPaw 2.1.0.

Serves the configured branding logo and lets the UI upload / reset it.
Keeps writing to ``branding/logo.json`` so it stays compatible with the
runtime ``set-logo.mjs`` maintenance script.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from qwenpaw.constant import WORKING_DIR
from qwenpaw.plugins.api import PluginApi

PLUGIN_DIR = Path(__file__).resolve().parent
DEFAULT_LOGO = PLUGIN_DIR / "assets" / "default-logo.png"
BRANDING_DIR = WORKING_DIR / "branding"
CONFIG_FILE = BRANDING_DIR / "logo.json"
ALLOWED_MIME = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}
MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}
MAX_BYTES = 2 * 1024 * 1024
_DATA_URL_RE = re.compile(r"^data:([^;]+);base64,(.*)$", re.DOTALL)


def _selected_logo() -> tuple[Path, str]:
    """Return the currently configured logo path/mime or the packaged default."""
    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        path = Path(str(config.get("path", ""))).expanduser().resolve()
        mime = str(config.get("mime", ""))
        branding = BRANDING_DIR.resolve()
        if path.is_file() and path.parent == branding and mime in ALLOWED_MIME:
            return path, mime
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return DEFAULT_LOGO, "image/png"


def _decode_data_url(value: str) -> tuple[bytes, str]:
    """Decode ``data:<mime>;base64,<payload>`` into raw bytes and mime type."""
    match = _DATA_URL_RE.match(value or "")
    if not match:
        raise HTTPException(status_code=422, detail="Logo 必须是 data:image/...;base64,...")
    mime = match.group(1).lower().strip()
    if mime not in ALLOWED_MIME:
        raise HTTPException(status_code=422, detail="不支持的 Logo 格式，仅支持 PNG/JPEG/SVG/WebP")
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="Logo base64 编码无效") from None
    if not raw:
        raise HTTPException(status_code=422, detail="Logo 内容为空")
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=422, detail="Logo 文件不能超过 2 MB")
    return raw, mime


class LogoUpdateRequest(BaseModel):
    """Client payload carrying a data-URL encoded logo."""

    logo: str = Field(min_length=1, max_length=4_000_000, description="data:image/...;base64,...")


router = APIRouter()


@router.get("/config")
async def logo_config() -> dict[str, Any]:
    path, mime = _selected_logo()
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"logo": f"data:{mime};base64,{encoded}", "source": path.name}


@router.put("/config")
async def update_logo(body: LogoUpdateRequest) -> dict[str, Any]:
    """Persist a new logo to branding/ and rewrite branding/logo.json."""
    raw, mime = _decode_data_url(body.logo)
    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    ext = MIME_EXT[mime]
    target = BRANDING_DIR / f"ai-os-logo{ext}"
    target.write_bytes(raw)
    config = {"path": str(target), "mime": mime}
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return {"logo": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}", "source": target.name}


@router.post("/reset")
async def reset_logo() -> dict[str, Any]:
    """Remove the branding logo config and fall back to the packaged default."""
    try:
        CONFIG_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    return {"source": DEFAULT_LOGO.name, "reset": True}


class LogoPlugin:
    def register(self, api: PluginApi) -> None:
        api.register_http_router(router, prefix="/zhiyun-logo", tags=["zhiyun-logo"])


plugin = LogoPlugin()
