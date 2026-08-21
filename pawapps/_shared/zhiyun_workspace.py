"""Shared Workspace persistence for Zhiyun PawApps.

Business state lives under the active QwenPaw Agent Workspace, never under
the plugin installation directory or process current working directory.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1
SENSITIVE_KEYS = {"authorization", "cookie", "password", "secret", "token", "api_key"}


def _active_workspace() -> Path | None:
    try:
        from qwenpaw.config.context import get_current_workspace_dir

        value = get_current_workspace_dir()
        return Path(value) if value else None
    except ImportError:
        return None


def resolve_workspace_dir(explicit: str | Path | None = None) -> Path:
    """Resolve a real Workspace from explicit input, QwenPaw context or env."""
    candidate = explicit or _active_workspace() or os.getenv("QWENPAW_WORKSPACE_DIR")
    if not candidate:
        raise RuntimeError("No active QwenPaw Workspace; refusing to use the process directory")
    root = Path(candidate).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    data: Path
    logs: Path
    files: Path
    knowledge: Path
    artifacts: Path
    database: Path
    runtime_log: Path
    audit_log: Path


def ensure_workspace(explicit: str | Path | None = None) -> WorkspacePaths:
    root = resolve_workspace_dir(explicit)
    paths = WorkspacePaths(
        root=root,
        data=root / "data",
        logs=root / "logs",
        files=root / "files",
        knowledge=root / "knowledge",
        artifacts=root / "artifacts",
        database=root / "data" / "ai-os.sqlite",
        runtime_log=root / "logs" / "runtime.jsonl",
        audit_log=root / "logs" / "audit.jsonl",
    )
    for directory in (paths.data, paths.logs, paths.files, paths.knowledge, paths.artifacts):
        directory.mkdir(parents=True, exist_ok=True)
    with connect(paths) as database:
        _migrate(database)
    return paths


@contextmanager
def connect(paths: WorkspacePaths) -> Iterator[sqlite3.Connection]:
    database = sqlite3.connect(paths.database)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA journal_mode=WAL")
    database.execute("PRAGMA foreign_keys=ON")
    try:
        yield database
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()


def _migrate(database: sqlite3.Connection) -> None:
    database.executescript(
        """
        CREATE TABLE IF NOT EXISTS os_schema_version (
          version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS os_app_execution (
          execution_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, app_id TEXT NOT NULL,
          session_id TEXT, status TEXT NOT NULL, input_json TEXT, output_json TEXT,
          error_code TEXT, started_at TEXT NOT NULL, finished_at TEXT, duration_ms INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_os_execution_trace ON os_app_execution(trace_id);
        CREATE TABLE IF NOT EXISTS os_tool_execution (
          id INTEGER PRIMARY KEY, trace_id TEXT NOT NULL, app_id TEXT NOT NULL,
          tool_name TEXT NOT NULL, status TEXT NOT NULL, input_json TEXT, output_json TEXT,
          error_code TEXT, started_at TEXT NOT NULL, finished_at TEXT, duration_ms INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_os_tool_trace ON os_tool_execution(trace_id);
        CREATE TABLE IF NOT EXISTS os_artifact (
          artifact_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, app_id TEXT NOT NULL,
          relative_path TEXT NOT NULL, media_type TEXT, sha256 TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS os_audit_event (
          id INTEGER PRIMARY KEY, trace_id TEXT NOT NULL, app_id TEXT NOT NULL,
          action TEXT NOT NULL, actor TEXT, before_json TEXT, after_json TEXT,
          created_at TEXT NOT NULL
        );
        """
    )
    database.execute(
        "INSERT OR IGNORE INTO os_schema_version(version, applied_at) VALUES (?, ?)",
        (SCHEMA_VERSION, _timestamp()),
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(value: Any, key: str = "") -> Any:
    if key.lower() in SENSITIVE_KEYS or any(part in key.lower() for part in ("password", "secret", "token")):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def append_event(paths: WorkspacePaths, event: dict[str, Any], *, audit: bool = False) -> None:
    """Append one durable, redacted JSON event to the selected Workspace log."""
    payload = {"timestamp": _timestamp(), **_redact(event)}
    target = paths.audit_log if audit else paths.runtime_log
    line = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    descriptor = os.open(target, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, line)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
