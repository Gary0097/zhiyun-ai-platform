# -*- coding: utf-8 -*-
"""Verified, optionally encrypted Data Core backup and recovery."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"ZHIYUN-AESGCM-1\n"


class DataOperationError(ValueError):
    pass


def _key(env_name: str | None) -> bytes | None:
    if not env_name:
        return None
    encoded = os.environ.get(env_name)
    if not encoded:
        raise DataOperationError(f"缺少备份密钥环境变量 {env_name}")
    try:
        key = base64.urlsafe_b64decode(encoded)
    except Exception as exc:
        raise DataOperationError("备份密钥必须是URL-safe Base64") from exc
    if len(key) != 32:
        raise DataOperationError("备份密钥解码后必须为32字节")
    return key


class DataCoreOperations:
    def __init__(self, database: str | Path, backup_root: str | Path | None = None):
        self.database = Path(database).resolve()
        self.backup_root = Path(backup_root or self.database.parent / "backups").resolve()
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, name: str) -> Path:
        if not name or Path(name).name != name or not name.endswith(".zdb"):
            raise DataOperationError("备份名称必须是不含路径的 .zdb 文件名")
        target = (self.backup_root / name).resolve()
        if target.parent != self.backup_root:
            raise DataOperationError("备份路径越界")
        return target

    def create_backup(self, *, key_env: str | None = None) -> dict[str, Any]:
        if not self.database.is_file():
            raise DataOperationError("Data Core 数据库不存在")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = f"data-core-{stamp}-{uuid.uuid4().hex[:8]}.zdb"
        target = self._safe_path(name)
        with tempfile.TemporaryDirectory(dir=self.backup_root) as directory:
            snapshot = Path(directory) / "snapshot.sqlite"
            with closing(sqlite3.connect(self.database)) as source, closing(sqlite3.connect(snapshot)) as destination:
                source.backup(destination)
            raw = snapshot.read_bytes()
        key = _key(key_env)
        encrypted = key is not None
        if key:
            nonce = os.urandom(12)
            content = MAGIC + nonce + AESGCM(key).encrypt(nonce, raw, MAGIC)
        else:
            content = raw
        target.write_bytes(content)
        manifest = {"name": name, "created_at": datetime.now(timezone.utc).isoformat(),
                    "encrypted": encrypted, "sha256": hashlib.sha256(content).hexdigest(),
                    "source_bytes": len(raw), "backup_bytes": len(content)}
        target.with_suffix(".json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def list_backups(self) -> list[dict[str, Any]]:
        result = []
        for manifest in sorted(self.backup_root.glob("data-core-*.json"), reverse=True):
            try:
                value = json.loads(manifest.read_text(encoding="utf-8"))
                backup = self._safe_path(value["name"])
                value["verified"] = backup.is_file() and hashlib.sha256(backup.read_bytes()).hexdigest() == value["sha256"]
                result.append(value)
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return result

    def restore_backup(self, name: str, *, confirmed: bool, key_env: str | None = None) -> dict[str, Any]:
        if not confirmed:
            raise DataOperationError("恢复会覆盖当前数据库，必须明确确认")
        backup = self._safe_path(name)
        manifest_path = backup.with_suffix(".json")
        if not backup.is_file() or not manifest_path.is_file():
            raise DataOperationError("备份或清单不存在")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        content = backup.read_bytes()
        if hashlib.sha256(content).hexdigest() != manifest.get("sha256"):
            raise DataOperationError("备份校验和不匹配，拒绝恢复")
        if content.startswith(MAGIC):
            key = _key(key_env)
            if not key:
                raise DataOperationError("加密备份需要密钥环境变量")
            nonce, ciphertext = content[len(MAGIC):len(MAGIC)+12], content[len(MAGIC)+12:]
            try:
                raw = AESGCM(key).decrypt(nonce, ciphertext, MAGIC)
            except Exception as exc:
                raise DataOperationError("备份密钥错误或密文损坏") from exc
        else:
            raw = content
        safety = self.create_backup(key_env=key_env if manifest.get("encrypted") else None)
        with tempfile.TemporaryDirectory(dir=self.backup_root) as directory:
            snapshot = Path(directory) / "restore.sqlite"
            snapshot.write_bytes(raw)
            with closing(sqlite3.connect(f"file:{snapshot.as_posix()}?mode=ro", uri=True)) as source:
                if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise DataOperationError("备份数据库完整性检查失败")
                with closing(sqlite3.connect(self.database)) as destination:
                    source.backup(destination)
        return {"restored": name, "safety_backup": safety["name"], "integrity": "ok"}

    def health(self) -> dict[str, Any]:
        try:
            with closing(sqlite3.connect(self.database)) as db:
                integrity = db.execute("PRAGMA quick_check").fetchone()[0]
                version = db.execute("SELECT value FROM data_core_meta WHERE key='schema_version'").fetchone()[0]
            free = __import__("shutil").disk_usage(self.database.parent).free
            status = "available" if integrity == "ok" else "degraded"
            return {"status": status, "integrity": integrity, "schema_version": int(version),
                    "database_bytes": self.database.stat().st_size, "free_bytes": free,
                    "backup_count": len(self.list_backups())}
        except (OSError, sqlite3.Error, TypeError) as exc:
            return {"status": "degraded", "impact": "数据读写与同步已阻止", "reason": str(exc)}
