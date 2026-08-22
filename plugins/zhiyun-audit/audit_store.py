"""Durable, redacted Workspace audit persistence."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_SECRET_PARTS = ("authorization", "cookie", "password", "secret", "token", "api_key")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: Any, key: str = "") -> Any:
    if any(part in key.lower() for part in _SECRET_PARTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "…"
    return value


def persist(workspace: Path, event: dict[str, Any]) -> None:
    root = workspace.expanduser().resolve()
    logs = root / "logs"
    data = root / "data"
    logs.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": _now(), **redact(event)}
    encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    with _LOCK:
        for filename in ("runtime.jsonl", "audit.jsonl"):
            descriptor = os.open(logs / filename, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.write(descriptor, encoded)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        database = sqlite3.connect(data / "ai-os.sqlite", timeout=10)
        try:
            database.execute("PRAGMA journal_mode=WAL")
            database.execute(
                """CREATE TABLE IF NOT EXISTS audit_tool_call (
                id INTEGER PRIMARY KEY, trace_id TEXT NOT NULL, session_id TEXT,
                agent_id TEXT, tool_name TEXT NOT NULL, status TEXT NOT NULL,
                duration_ms INTEGER NOT NULL, error_type TEXT, created_at TEXT NOT NULL)"""
            )
            database.execute("CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit_tool_call(trace_id)")
            database.execute(
                "INSERT INTO audit_tool_call(trace_id,session_id,agent_id,tool_name,status,duration_ms,error_type,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (payload["trace_id"], payload.get("session_id"), payload.get("agent_id"), payload["tool_name"], payload["status"], payload["duration_ms"], payload.get("error_type"), payload["timestamp"]),
            )
            database.commit()
        finally:
            database.close()
