"""Durable, redacted Workspace audit persistence."""

from __future__ import annotations

import json
import hashlib
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_SECRET_PARTS = ("authorization", "cookie", "password", "secret", "token", "api_key")
_INLINE_SECRETS = (
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[REDACTED_PHONE]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: Any, key: str = "") -> Any:
    if any(part in key.lower() for part in _SECRET_PARTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        for pattern, replacement in _INLINE_SECRETS:
            value = pattern.sub(replacement, value)
        if len(value) > 500:
            return value[:500] + "…"
    return value


def persist(workspace: Path, event: dict[str, Any]) -> None:
    root = workspace.expanduser().resolve()
    logs = root / "logs"
    data = root / "data"
    logs.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        audit_path = logs / "audit.jsonl"
        previous_hash = "0" * 64
        if audit_path.exists():
            try:
                last = audit_path.read_bytes().splitlines()[-1]
                previous_hash = json.loads(last)["event_hash"]
            except (OSError, IndexError, KeyError, json.JSONDecodeError):
                previous_hash = "0" * 64
        payload = {"timestamp": _now(), **redact(event), "previous_hash": previous_hash}
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload["event_hash"] = hashlib.sha256(canonical).hexdigest()
        encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
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
                """CREATE TABLE IF NOT EXISTS audit_event_integrity (
                event_hash TEXT PRIMARY KEY, previous_hash TEXT NOT NULL,
                trace_id TEXT NOT NULL, created_at TEXT NOT NULL)"""
            )
            database.execute(
                "INSERT INTO audit_tool_call(trace_id,session_id,agent_id,tool_name,status,duration_ms,error_type,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (payload["trace_id"], payload.get("session_id"), payload.get("agent_id"), payload["tool_name"], payload["status"], payload["duration_ms"], payload.get("error_type"), payload["timestamp"]),
            )
            database.execute(
                "INSERT INTO audit_event_integrity(event_hash,previous_hash,trace_id,created_at) VALUES(?,?,?,?)",
                (payload["event_hash"], payload["previous_hash"], payload["trace_id"], payload["timestamp"]),
            )
            database.commit()
        finally:
            database.close()


def list_events(
    workspace: Path,
    *,
    status: str | None = None,
    tool_name: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Read a bounded metadata-only audit feed for the system audit page."""
    if status not in {None, "success", "failed", "blocked"}:
        raise ValueError(f"unsupported audit status: {status}")
    bounded_limit = max(1, min(int(limit), 500))
    clauses: list[str] = []
    parameters: list[Any] = []
    if status:
        clauses.append("status = ?")
        parameters.append(status)
    if tool_name:
        clauses.append("tool_name = ?")
        parameters.append(tool_name)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    database_path = workspace.expanduser().resolve() / "data" / "ai-os.sqlite"
    if not database_path.exists():
        return []
    database = sqlite3.connect(database_path, timeout=10)
    database.row_factory = sqlite3.Row
    try:
        exists = database.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_tool_call'"
        ).fetchone()
        if not exists:
            return []
        rows = database.execute(
            f"""SELECT trace_id, session_id, agent_id, tool_name, status,
                       duration_ms, error_type, created_at
                FROM audit_tool_call {where}
                ORDER BY created_at DESC, id DESC LIMIT ?""",
            [*parameters, bounded_limit],
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        database.close()


def verify_integrity(workspace: Path) -> dict[str, Any]:
    """Verify the append-only JSONL hash chain without exposing event payloads."""
    path = workspace.expanduser().resolve() / "logs" / "audit.jsonl"
    if not path.exists():
        return {"status": "available", "events": 0, "integrity": "empty"}
    previous = "0" * 64
    count = 0
    legacy = 0
    try:
        for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            event = json.loads(raw)
            if "event_hash" not in event:
                legacy += 1
                continue
            claimed = event.pop("event_hash")
            if event.get("previous_hash") != previous:
                return {"status": "degraded", "events": count, "integrity": "broken", "line": line_number}
            calculated = hashlib.sha256(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            if claimed != calculated:
                return {"status": "degraded", "events": count, "integrity": "broken", "line": line_number}
            previous, count = claimed, count + 1
    except (OSError, KeyError, json.JSONDecodeError):
        return {"status": "degraded", "events": count, "integrity": "unreadable"}
    return {"status": "available", "events": count, "legacy_events": legacy,
            "integrity": "verified", "head_hash": previous}
