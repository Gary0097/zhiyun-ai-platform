# -*- coding: utf-8 -*-
"""Small, isolated header-logo plugin for QwenPaw 2.1.0."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from qwenpaw.constant import WORKING_DIR
from qwenpaw.plugins.api import PluginApi

PLUGIN_DIR = Path(__file__).resolve().parent
DEFAULT_LOGO = PLUGIN_DIR / "assets" / "default-logo.png"
CONFIG_FILE = WORKING_DIR / "branding" / "logo.json"
ALLOWED_MIME = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}


def _selected_logo() -> tuple[Path, str]:
    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        path = Path(str(config.get("path", ""))).expanduser().resolve()
        mime = str(config.get("mime", ""))
        branding = (WORKING_DIR / "branding").resolve()
        if path.is_file() and path.parent == branding and mime in ALLOWED_MIME:
            return path, mime
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return DEFAULT_LOGO, "image/png"


router = APIRouter()


@router.get("/config")
async def logo_config() -> dict[str, Any]:
    path, mime = _selected_logo()
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"logo": f"data:{mime};base64,{encoded}", "source": path.name}


class LogoPlugin:
    def register(self, api: PluginApi) -> None:
        api.register_http_router(router, prefix="/zhiyun-logo", tags=["zhiyun-logo"])


plugin = LogoPlugin()
