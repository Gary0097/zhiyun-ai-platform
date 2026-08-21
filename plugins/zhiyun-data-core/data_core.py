# -*- coding: utf-8 -*-
"""Workspace-local shared database for AI-OS PawApps."""

from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1
FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
FIELD_TYPES = {"text", "integer", "number", "boolean", "date", "datetime"}
SOURCE_TYPES = {"real", "simulated"}

ORDER_FIELDS = [
    ("order_no", "订单编号", "text", True),
    ("customer_name", "客户名称", "text", True),
    ("product_name", "产品名称", "text", True),
    ("quantity", "数量", "integer", True),
    ("order_date", "下单日期", "date", True),
    ("promised_date", "承诺交期", "date", True),
    ("status", "订单状态", "text", True),
    ("progress", "完成进度", "number", True),
    ("last_logistics_update", "物流更新时间", "date", False),
    ("production_delay_days", "生产延误天数", "integer", False),
]


class DataCoreError(ValueError):
    """Raised when a request violates a Data Core rule."""


class DataCore:
    """Own schema metadata, business records and reversible batches."""

    def __init__(self, database: Path | str) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a transaction with foreign keys and safe row access."""
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS data_core_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS data_schemas (
                    entity TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS schema_fields (
                    entity TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    label TEXT NOT NULL,
                    field_type TEXT NOT NULL,
                    required INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    position INTEGER NOT NULL,
                    built_in INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (entity, field_name),
                    FOREIGN KEY (entity) REFERENCES data_schemas(entity)
                );
                CREATE TABLE IF NOT EXISTS data_batches (
                    batch_id TEXT PRIMARY KEY,
                    entity TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    rolled_back_at TEXT
                );
                CREATE TABLE IF NOT EXISTS data_records (
                    record_id TEXT PRIMARY KEY,
                    entity TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (batch_id) REFERENCES data_batches(batch_id)
                );
                CREATE INDEX IF NOT EXISTS idx_records_entity
                ON data_records(entity, created_at);
                CREATE INDEX IF NOT EXISTS idx_records_batch
                ON data_records(batch_id);
                """
            )
            current = connection.execute(
                "SELECT value FROM data_core_meta WHERE key = 'schema_version'"
            ).fetchone()
            if current and int(current["value"]) > SCHEMA_VERSION:
                raise RuntimeError("Data Core database is newer than this plugin")
            connection.execute(
                "INSERT OR REPLACE INTO data_core_meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO data_schemas(entity, label) VALUES('orders', '客户订单')"
            )
            for position, (name, label, kind, required) in enumerate(ORDER_FIELDS):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO schema_fields
                    (entity, field_name, label, field_type, required, active, position, built_in)
                    VALUES('orders', ?, ?, ?, ?, 1, ?, 1)
                    """,
                    (name, label, kind, int(required), position),
                )

    def list_schema(self, entity: str) -> dict[str, Any]:
        with self.connect() as connection:
            schema = connection.execute(
                "SELECT entity, label, updated_at FROM data_schemas WHERE entity = ?",
                (entity,),
            ).fetchone()
            if not schema:
                raise DataCoreError(f"unknown entity: {entity}")
            fields = connection.execute(
                """
                SELECT field_name, label, field_type, required, active, position, built_in
                FROM schema_fields WHERE entity = ? ORDER BY position, field_name
                """,
                (entity,),
            ).fetchall()
        return {
            "entity": schema["entity"],
            "label": schema["label"],
            "updated_at": schema["updated_at"],
            "fields": [
                {
                    "name": row["field_name"],
                    "label": row["label"],
                    "type": row["field_type"],
                    "required": bool(row["required"]),
                    "active": bool(row["active"]),
                    "built_in": bool(row["built_in"]),
                }
                for row in fields
            ],
        }

    def add_field(
        self,
        entity: str,
        name: str,
        label: str,
        field_type: str = "text",
        required: bool = False,
    ) -> dict[str, Any]:
        if not FIELD_NAME.fullmatch(name):
            raise DataCoreError("field name must use lowercase letters, numbers and underscores")
        if field_type not in FIELD_TYPES:
            raise DataCoreError(f"unsupported field type: {field_type}")
        if not label.strip():
            raise DataCoreError("field label is required")
        with self.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM data_schemas WHERE entity = ?", (entity,)
            ).fetchone()
            if not exists:
                raise DataCoreError(f"unknown entity: {entity}")
            position = connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS value FROM schema_fields WHERE entity = ?",
                (entity,),
            ).fetchone()["value"]
            try:
                connection.execute(
                    """
                    INSERT INTO schema_fields
                    (entity, field_name, label, field_type, required, active, position, built_in)
                    VALUES(?, ?, ?, ?, ?, 1, ?, 0)
                    """,
                    (entity, name, label.strip(), field_type, int(required), position),
                )
            except sqlite3.IntegrityError as exc:
                raise DataCoreError(f"field already exists: {name}") from exc
        return self.list_schema(entity)

    def update_field(
        self,
        entity: str,
        name: str,
        *,
        label: str | None = None,
        active: bool | None = None,
    ) -> dict[str, Any]:
        changes: list[str] = []
        values: list[Any] = []
        if label is not None:
            if not label.strip():
                raise DataCoreError("field label is required")
            changes.append("label = ?")
            values.append(label.strip())
        if active is not None:
            changes.append("active = ?")
            values.append(int(active))
        if not changes:
            return self.list_schema(entity)
        values.extend([entity, name])
        with self.connect() as connection:
            cursor = connection.execute(
                f"UPDATE schema_fields SET {', '.join(changes)} WHERE entity = ? AND field_name = ?",
                values,
            )
            if cursor.rowcount != 1:
                raise DataCoreError(f"unknown field: {name}")
            connection.execute(
                "UPDATE data_schemas SET updated_at = CURRENT_TIMESTAMP WHERE entity = ?",
                (entity,),
            )
        return self.list_schema(entity)

    def preview_import(
        self,
        entity: str,
        rows: list[dict[str, Any]],
        mapping: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not rows:
            raise DataCoreError("import rows cannot be empty")
        schema = self.list_schema(entity)
        active_fields = {field["name"]: field for field in schema["fields"] if field["active"]}
        field_mapping = mapping or {key: key for key in rows[0]}
        unknown_targets = sorted(set(field_mapping.values()) - set(active_fields))
        if unknown_targets:
            raise DataCoreError(f"unknown target fields: {', '.join(unknown_targets)}")
        normalized: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for row_number, source in enumerate(rows, start=2):
            target = {target_name: source.get(source_name) for source_name, target_name in field_mapping.items()}
            row_errors = self._validate_row(target, active_fields)
            if row_errors:
                errors.append({"row": row_number, "errors": row_errors})
            normalized.append(target)
        return {
            "entity": entity,
            "mapping": field_mapping,
            "row_count": len(rows),
            "valid_count": len(rows) - len(errors),
            "error_count": len(errors),
            "errors": errors[:100],
            "preview": normalized[:20],
        }

    def import_rows(
        self,
        entity: str,
        rows: list[dict[str, Any]],
        *,
        mapping: dict[str, str] | None = None,
        source_name: str = "manual-import",
    ) -> dict[str, Any]:
        preview = self.preview_import(entity, rows, mapping)
        if preview["error_count"]:
            raise DataCoreError("import validation failed; fix preview errors before commit")
        batch_id = self._insert_batch(
            entity,
            preview["preview"] if len(rows) <= 20 else [
                {target: source.get(source_key) for source_key, target in preview["mapping"].items()}
                for source in rows
            ],
            source_type="real",
            source_name=source_name,
        )
        return {"batch_id": batch_id, "entity": entity, "row_count": len(rows), "source_type": "real"}

    def generate_orders(self, count: int = 50, seed: int | None = None) -> dict[str, Any]:
        if count < 1 or count > 5000:
            raise DataCoreError("simulation count must be between 1 and 5000")
        generator = random.Random(seed)
        customers = ["海川制造", "星联科技", "远航装备", "东峰工业", "华锐机电"]
        products = ["工业控制柜", "伺服电机", "精密模组", "传动组件", "智能传感器"]
        statuses = ["待排产", "生产中", "待发货", "运输中", "已完成"]
        today = date.today()
        rows: list[dict[str, Any]] = []
        for index in range(count):
            order_day = today - timedelta(days=generator.randint(0, 45))
            promised = order_day + timedelta(days=generator.randint(7, 35))
            status = generator.choice(statuses)
            progress = {"待排产": 5, "生产中": generator.randint(20, 85), "待发货": 95, "运输中": 98, "已完成": 100}[status]
            delay = generator.choices([0, 1, 3, 7, 12], weights=[55, 15, 15, 10, 5])[0]
            rows.append({
                "order_no": f"SIM-{today:%Y%m%d}-{index + 1:05d}",
                "customer_name": generator.choice(customers),
                "product_name": generator.choice(products),
                "quantity": generator.randint(10, 500),
                "order_date": order_day.isoformat(),
                "promised_date": promised.isoformat(),
                "status": status,
                "progress": progress,
                "last_logistics_update": (today - timedelta(days=generator.randint(0, 8))).isoformat(),
                "production_delay_days": delay,
            })
        batch_id = self._insert_batch(
            "orders", rows, source_type="simulated", source_name=f"AI simulated orders (seed={seed})"
        )
        return {"batch_id": batch_id, "entity": "orders", "row_count": count, "source_type": "simulated", "seed": seed}

    def _insert_batch(
        self,
        entity: str,
        rows: list[dict[str, Any]],
        *,
        source_type: str,
        source_name: str,
    ) -> str:
        if source_type not in SOURCE_TYPES:
            raise DataCoreError(f"unsupported source type: {source_type}")
        batch_id = f"batch-{uuid.uuid4()}"
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO data_batches(batch_id, entity, source_type, source_name, row_count)
                VALUES(?, ?, ?, ?, ?)
                """,
                (batch_id, entity, source_type, source_name, len(rows)),
            )
            connection.executemany(
                """
                INSERT INTO data_records(record_id, entity, batch_id, source_type, payload)
                VALUES(?, ?, ?, ?, ?)
                """,
                [
                    (f"record-{uuid.uuid4()}", entity, batch_id, source_type, json.dumps(row, ensure_ascii=False))
                    for row in rows
                ],
            )
        return batch_id

    @staticmethod
    def _validate_row(row: dict[str, Any], fields: dict[str, dict[str, Any]]) -> list[str]:
        errors: list[str] = []
        for name, field in fields.items():
            value = row.get(name)
            if field["required"] and (value is None or value == ""):
                errors.append(f"{name} is required")
                continue
            if value is None or value == "":
                continue
            kind = field["type"]
            try:
                if kind == "integer":
                    int(value)
                elif kind == "number":
                    float(value)
                elif kind == "boolean" and str(value).casefold() not in {"true", "false", "1", "0", "yes", "no"}:
                    raise ValueError
                elif kind == "date":
                    date.fromisoformat(str(value))
            except (TypeError, ValueError):
                errors.append(f"{name} must be {kind}")
        return errors

    def list_records(
        self,
        entity: str,
        *,
        limit: int = 100,
        source_type: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["entity = ?"]
        params: list[Any] = [entity]
        if source_type:
            if source_type not in SOURCE_TYPES:
                raise DataCoreError(f"unsupported source type: {source_type}")
            clauses.append("source_type = ?")
            params.append(source_type)
        params.append(max(1, min(limit, 1000)))
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT record_id, batch_id, source_type, payload, created_at
                FROM data_records WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC, record_id LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            {
                "record_id": row["record_id"],
                "batch_id": row["batch_id"],
                "source_type": row["source_type"],
                "created_at": row["created_at"],
                "data": json.loads(row["payload"]),
            }
            for row in rows
        ]

    def search_records(
        self,
        entity: str,
        *,
        keyword: str = "",
        filters: dict[str, Any] | None = None,
        source_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search active records without exposing raw SQL to callers."""
        schema = self.list_schema(entity)
        active_fields = {field["name"] for field in schema["fields"] if field["active"]}
        safe_filters = {key: value for key, value in (filters or {}).items() if value not in (None, "")}
        unknown = sorted(set(safe_filters) - active_fields)
        if unknown:
            raise DataCoreError(f"unknown filter fields: {', '.join(unknown)}")

        records = self.list_records(entity, limit=1000, source_type=source_type)
        needle = keyword.strip().casefold()
        matched: list[dict[str, Any]] = []
        for record in records:
            payload = record["data"]
            if safe_filters and any(str(payload.get(key, "")).casefold() != str(value).casefold() for key, value in safe_filters.items()):
                continue
            if needle and not any(needle in str(value).casefold() for value in payload.values()):
                continue
            matched.append(record)
            if len(matched) >= max(1, min(limit, 200)):
                break
        return matched

    def list_batches(self, entity: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM data_batches"
        params: tuple[Any, ...] = ()
        if entity:
            query += " WHERE entity = ?"
            params = (entity,)
        query += " ORDER BY created_at DESC, batch_id"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def rollback_batch(self, batch_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            batch = connection.execute(
                "SELECT status, row_count FROM data_batches WHERE batch_id = ?", (batch_id,)
            ).fetchone()
            if not batch:
                raise DataCoreError(f"unknown batch: {batch_id}")
            if batch["status"] == "rolled_back":
                return {"batch_id": batch_id, "deleted_records": 0, "status": "rolled_back"}
            deleted = connection.execute(
                "DELETE FROM data_records WHERE batch_id = ?", (batch_id,)
            ).rowcount
            connection.execute(
                """
                UPDATE data_batches
                SET status = 'rolled_back', rolled_back_at = CURRENT_TIMESTAMP
                WHERE batch_id = ?
                """,
                (batch_id,),
            )
        return {"batch_id": batch_id, "deleted_records": deleted, "status": "rolled_back"}


def default_database() -> Path:
    """Resolve a cross-platform Data Core path with an operator override."""
    override = os.environ.get("ZHIYUN_DATA_CORE_DIR")
    if override:
        return Path(override).expanduser().resolve() / "data-core.sqlite"
    try:
        from qwenpaw.constant import WORKING_DIR

        return WORKING_DIR / "workspace" / "data-core" / "data-core.sqlite"
    except ImportError:
        return Path.home() / ".qwenpaw" / "workspace" / "data-core" / "data-core.sqlite"
