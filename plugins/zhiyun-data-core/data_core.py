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

try:
    from .table_parser import build_export_bytes
except ImportError:  # pragma: no cover
    from table_parser import build_export_bytes

SCHEMA_VERSION = 3
FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
FIELD_TYPES = {"text", "integer", "number", "boolean", "date", "datetime"}
SOURCE_TYPES = {"real", "simulated"}
DATA_MODES = {"demo", "production"}

_UNIQUE_FIELDS = {
    "orders": ["order_no"],
}

CONTEXT_KEY = "active_context"


def _normalize_data_mode(value: str | None) -> str:
    """Normalize a data environment to demo/production, defaulting to demo."""
    if value is None or value == "":
        return "demo"
    if value == "live":
        return "production"
    if value not in DATA_MODES:
        raise DataCoreError("data_mode 只能是 demo 或 production")
    return value

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

PRODUCTION_FIELDS = [
    ("record_date", "日期", "date", True),
    ("department", "部门", "text", True),
    ("output", "产量/产值", "number", True),
    ("labor_hours", "工时", "number", True),
    ("employee_count", "人数", "number", False),
    ("cost", "成本", "number", False),
    ("loss", "损耗", "number", False),
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
                CREATE TABLE IF NOT EXISTS data_core_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    description TEXT NOT NULL
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
                    data_mode TEXT NOT NULL DEFAULT 'demo',
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
                    data_mode TEXT NOT NULL DEFAULT 'demo',
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
            current_version = int(current["value"]) if current else 0
            if current_version < 1:
                connection.execute("INSERT OR IGNORE INTO data_core_migrations(version, description) VALUES(1, 'initial schema registry and reversible batches')")
            if current_version < 2:
                connection.execute("INSERT OR IGNORE INTO data_core_migrations(version, description) VALUES(2, 'backup recovery and migration journal')")
            if current_version < 3:
                try:
                    connection.execute("ALTER TABLE data_batches ADD COLUMN data_mode TEXT NOT NULL DEFAULT 'demo'")
                    connection.execute("ALTER TABLE data_records ADD COLUMN data_mode TEXT NOT NULL DEFAULT 'demo'")
                except sqlite3.OperationalError:
                    # Column already exists (e.g. a fresh schema created this run).
                    pass
                connection.execute("CREATE INDEX IF NOT EXISTS idx_records_mode ON data_records(entity, data_mode, created_at)")
                connection.execute("CREATE INDEX IF NOT EXISTS idx_batches_mode ON data_batches(entity, data_mode, created_at)")
                connection.execute("INSERT OR IGNORE INTO data_core_migrations(version, description) VALUES(3, 'add demo/production data environment isolation')")
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

            connection.execute(
                "INSERT OR IGNORE INTO data_schemas(entity, label) VALUES('production', '生产日报')"
            )
            for position, (name, label, kind, required) in enumerate(PRODUCTION_FIELDS):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO schema_fields
                    (entity, field_name, label, field_type, required, active, position, built_in)
                    VALUES('production', ?, ?, ?, ?, 1, ?, 1)
                    """,
                    (name, label, kind, int(required), position),
                )

    def migration_history(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT version, applied_at, description FROM data_core_migrations ORDER BY version"
            ).fetchall()
        return [dict(row) for row in rows]

    def _empty_context(self) -> dict[str, str]:
        return {"env_id": "", "data_mode": "", "start_date": "", "end_date": ""}

    def get_context(self) -> dict[str, str]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM data_core_meta WHERE key = ?", (CONTEXT_KEY,)
            ).fetchone()
            if not row:
                return self._empty_context()
            try:
                stored = json.loads(row["value"])
            except (TypeError, ValueError):
                return self._empty_context()
            base = self._empty_context()
            base.update({key: str(stored.get(key, "")) for key in base})
            return base

    def set_context(
        self,
        env_id: str = "",
        data_mode: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> dict[str, str]:
        """Record the active enterprise environment for untagged reads."""
        if data_mode:
            if data_mode == "live":
                data_mode = "production"
            elif data_mode not in DATA_MODES:
                raise DataCoreError("data_mode 只能是 demo 或 production")
        for key, value in (("start_date", start_date), ("end_date", end_date)):
            if value:
                try:
                    date.fromisoformat(str(value))
                except ValueError as exc:
                    raise DataCoreError(f"{key} 必须是 YYYY-MM-DD 格式") from exc
        if start_date and end_date and str(start_date) > str(end_date):
            raise DataCoreError("start_date 不能晚于 end_date")
        payload = {
            "env_id": env_id or "",
            "data_mode": data_mode or "",
            "start_date": start_date or "",
            "end_date": end_date or "",
        }
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO data_core_meta(key, value) VALUES(?, ?)",
                (CONTEXT_KEY, json.dumps(payload, ensure_ascii=False)),
            )
        return self.get_context()

    def _date_field_for(self, entity: str) -> str | None:
        schema = self.list_schema(entity)
        for field in schema["fields"]:
            if field["active"] and field["type"] == "date":
                return field["name"]
        return None
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

    def list_entities(self, *, data_mode: str | None = None) -> list[dict[str, Any]]:
        """Return user-facing datasets with live record/source counts."""
        mode = _normalize_data_mode(data_mode) if data_mode else None
        where = "WHERE r.data_mode = ?" if mode else ""
        mode_args = (mode,) if mode else ()
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT s.entity, s.label, s.updated_at,
                       COUNT(r.record_id) AS record_count,
                       SUM(CASE WHEN r.source_type = 'real' THEN 1 ELSE 0 END) AS real_count,
                       SUM(CASE WHEN r.source_type = 'simulated' THEN 1 ELSE 0 END) AS simulated_count,
                       SUM(CASE WHEN r.data_mode = 'demo' THEN 1 ELSE 0 END) AS demo_count,
                       SUM(CASE WHEN r.data_mode = 'production' THEN 1 ELSE 0 END) AS production_count
                FROM data_schemas AS s
                LEFT JOIN data_records AS r ON r.entity = s.entity {where}
                GROUP BY s.entity, s.label, s.updated_at
                ORDER BY s.entity
                """,
                mode_args,
            ).fetchall()
        return [
            {
                "entity": row["entity"],
                "label": row["label"],
                "updated_at": row["updated_at"],
                "record_count": int(row["record_count"] or 0),
                "real_count": int(row["real_count"] or 0),
                "simulated_count": int(row["simulated_count"] or 0),
                "demo_count": int(row["demo_count"] or 0),
                "production_count": int(row["production_count"] or 0),
            }
            for row in rows
        ]

    def create_schema(
        self,
        entity: str,
        label: str,
        fields: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Create a user-defined dataset and its initial field model atomically."""
        if not FIELD_NAME.fullmatch(entity):
            raise DataCoreError("entity name must use lowercase letters, numbers and underscores")
        if not label.strip():
            raise DataCoreError("entity label is required")
        if not fields:
            raise DataCoreError("at least one field is required")
        names = [str(field.get("name", "")) for field in fields]
        if len(names) != len(set(names)):
            raise DataCoreError("field names must be unique")
        for field in fields:
            name = str(field.get("name", ""))
            kind = str(field.get("field_type", "text"))
            if not FIELD_NAME.fullmatch(name):
                raise DataCoreError(f"invalid field name: {name}")
            if kind not in FIELD_TYPES:
                raise DataCoreError(f"unsupported field type: {kind}")
            if not str(field.get("label", "")).strip():
                raise DataCoreError(f"field label is required: {name}")
        with self.connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO data_schemas(entity, label) VALUES(?, ?)",
                    (entity, label.strip()),
                )
                connection.executemany(
                    """
                    INSERT INTO schema_fields
                    (entity, field_name, label, field_type, required, active, position, built_in)
                    VALUES(?, ?, ?, ?, ?, 1, ?, 0)
                    """,
                    [
                        (entity, field["name"], str(field["label"]).strip(), field.get("field_type", "text"), int(bool(field.get("required"))), position)
                        for position, field in enumerate(fields)
                    ],
                )
            except sqlite3.IntegrityError as exc:
                raise DataCoreError(f"entity already exists: {entity}") from exc
        return self.list_schema(entity)

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
        data_mode: str | None = None,
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
        duplicate_info = self.check_duplicates(entity, rows, mapping=field_mapping, data_mode=data_mode)
        return {
            "entity": entity,
            "mapping": field_mapping,
            "row_count": len(rows),
            "valid_count": len(rows) - len(errors),
            "error_count": len(errors),
            "errors": errors[:100],
            "duplicate_count": duplicate_info["duplicate_count"],
            "duplicate_rows": duplicate_info["duplicate_rows"],
            "preview": normalized[:20],
        }

    def check_duplicates(
        self,
        entity: str,
        rows: list[dict[str, Any]],
        mapping: dict[str, str] | None = None,
        unique_fields: list[str] | None = None,
        data_mode: str | None = None,
    ) -> dict[str, Any]:
        """Report rows that duplicate a unique key already in the target environment or within the batch."""
        if not rows:
            raise DataCoreError("import rows cannot be empty")
        schema = self.list_schema(entity)
        active_fields = {field["name"]: field for field in schema["fields"] if field["active"]}
        field_mapping = mapping or {key: key for key in rows[0]}
        unknown_targets = sorted(set(field_mapping.values()) - set(active_fields))
        if unknown_targets:
            raise DataCoreError(f"unknown target fields: {', '.join(unknown_targets)}")
        if unique_fields is None:
            unique_fields = _UNIQUE_FIELDS.get(entity, [])
        unknown_unique = sorted(set(unique_fields) - set(active_fields))
        if unknown_unique:
            raise DataCoreError(f"unknown unique fields: {', '.join(unknown_unique)}")
        existing_keys = self._existing_unique_keys(entity, unique_fields, data_mode)
        seen: dict[tuple[str, ...], int] = {}
        normalized: list[dict[str, Any]] = []
        for source in rows:
            target = {target_name: source.get(source_name) for source_name, target_name in field_mapping.items()}
            normalized.append(target)
            if not unique_fields:
                continue
            key_values = tuple(target.get(field) for field in unique_fields)
            if any(value in (None, "") for value in key_values):
                continue
            key = tuple(str(value) for value in key_values)
            seen[key] = seen.get(key, 0) + 1
        duplicate_rows: list[dict[str, Any]] = []
        duplicate_count = 0
        if unique_fields:
            for target in normalized:
                key_values = tuple(target.get(field) for field in unique_fields)
                if any(value in (None, "") for value in key_values):
                    continue
                key = tuple(str(value) for value in key_values)
                count = seen.get(key, 0)
                if count > 1 or key in existing_keys:
                    duplicate_count += 1
                    duplicate_rows.append({
                        "row": target,
                        "fields": {field: target.get(field) for field in unique_fields},
                        "count": count,
                        "existing": key in existing_keys,
                    })
        return {
            "duplicate_count": duplicate_count,
            "duplicate_rows": duplicate_rows[:50],
        }

    def _existing_unique_keys(
        self,
        entity: str,
        unique_fields: list[str],
        data_mode: str | None,
    ) -> set[tuple[str, ...]]:
        """Return unique keys already stored in the target environment for this entity."""
        keys: set[tuple[str, ...]] = set()
        if not unique_fields:
            return keys
        mode: str | None = None
        if data_mode is not None:
            mode = _normalize_data_mode(data_mode)
        else:
            mode = self.get_context()["data_mode"] or None
        if not mode:
            return keys
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM data_records WHERE entity = ? AND data_mode = ?",
                (entity, mode),
            ).fetchall()
        for row in rows:
            try:
                record = json.loads(row["payload"])
            except (TypeError, ValueError):
                continue
            key_values = tuple(record.get(field) for field in unique_fields)
            if any(value in (None, "") for value in key_values):
                continue
            keys.add(tuple(str(value) for value in key_values))
        return keys

    def import_rows(
        self,
        entity: str,
        rows: list[dict[str, Any]],
        *,
        mapping: dict[str, str] | None = None,
        source_name: str = "manual-import",
        data_mode: str = "production",
    ) -> dict[str, Any]:
        data_mode = _normalize_data_mode(data_mode)
        preview = self.preview_import(entity, rows, mapping, data_mode=data_mode)
        if preview["error_count"]:
            raise DataCoreError("import validation failed; fix preview errors before commit")
        if preview["duplicate_count"]:
            raise DataCoreError("import validation failed; fix duplicate rows before commit")
        batch_id = self._insert_batch(
            entity,
            preview["preview"] if len(rows) <= 20 else [
                {target: source.get(source_key) for source_key, target in preview["mapping"].items()}
                for source in rows
            ],
            source_type="real",
            source_name=source_name,
            data_mode=data_mode,
        )
        return {"batch_id": batch_id, "entity": entity, "row_count": len(rows), "source_type": "real", "data_mode": data_mode}

    def generate_orders(self, count: int = 50, seed: int | None = None, data_mode: str = "demo") -> dict[str, Any]:
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
            "orders", rows, source_type="simulated", source_name=f"AI simulated orders (seed={seed})",
            data_mode=_normalize_data_mode(data_mode),
        )
        return {"batch_id": batch_id, "entity": "orders", "row_count": count, "source_type": "simulated", "seed": seed, "data_mode": _normalize_data_mode(data_mode)}

    def generate_production(self, count: int = 60, seed: int | None = None, data_mode: str = "demo") -> dict[str, Any]:
        """Generate reversible production records for an end-to-end demo."""
        if count < 1 or count > 5000:
            raise DataCoreError("simulation count must be between 1 and 5000")
        generator = random.Random(seed)
        departments = ["机加工一部", "装配一部", "表面处理", "质量检验"]
        today = date.today()
        rows = []
        for _ in range(count):
            department = generator.choice(departments)
            employees = generator.randint(4, 18)
            hours = employees * generator.choice([8, 8, 10])
            output = generator.randint(80, 600)
            rows.append({
                "record_date": (today - timedelta(days=generator.randint(0, 29))).isoformat(),
                "department": department,
                "output": output,
                "labor_hours": hours,
                "employee_count": employees,
                "cost": round(output * generator.uniform(8, 28), 2),
                "loss": round(output * generator.uniform(0.005, 0.08), 2),
            })
        batch_id = self._insert_batch("production", rows, source_type="simulated", source_name=f"AI simulated production (seed={seed})", data_mode=_normalize_data_mode(data_mode))
        return {"batch_id": batch_id, "entity": "production", "row_count": count, "source_type": "simulated", "seed": seed, "data_mode": _normalize_data_mode(data_mode)}

    def _insert_batch(
        self,
        entity: str,
        rows: list[dict[str, Any]],
        *,
        source_type: str,
        source_name: str,
        data_mode: str = "demo",
    ) -> str:
        if source_type not in SOURCE_TYPES:
            raise DataCoreError(f"unsupported source type: {source_type}")
        data_mode = _normalize_data_mode(data_mode)
        batch_id = f"batch-{uuid.uuid4()}"
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO data_batches(batch_id, entity, source_type, data_mode, source_name, row_count)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (batch_id, entity, source_type, data_mode, source_name, len(rows)),
            )
            connection.executemany(
                """
                INSERT INTO data_records(record_id, entity, batch_id, source_type, data_mode, payload)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                [
                    (f"record-{uuid.uuid4()}", entity, batch_id, source_type, data_mode, json.dumps(row, ensure_ascii=False))
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
        data_mode: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        context = None
        if data_mode is None or start_date is None or end_date is None:
            context = self.get_context()
        if data_mode is None:
            data_mode = context["data_mode"] or None
        if start_date is None:
            start_date = context["start_date"] or None
        if end_date is None:
            end_date = context["end_date"] or None
        clauses = ["entity = ?"]
        params: list[Any] = [entity]
        if source_type:
            if source_type not in SOURCE_TYPES:
                raise DataCoreError(f"unsupported source type: {source_type}")
            clauses.append("source_type = ?")
            params.append(source_type)
        if data_mode:
            mode = _normalize_data_mode(data_mode)
            if mode:
                clauses.append("data_mode = ?")
                params.append(mode)
        date_field = None
        if start_date or end_date:
            date_field = self._date_field_for(entity)
            if not date_field:
                raise DataCoreError(f"entity {entity} has no date field for window filtering")
        want_limit = max(1, min(limit, 1000))
        if start_date or end_date:
            sql = (
                "SELECT record_id, batch_id, source_type, data_mode, payload, created_at "
                "FROM data_records WHERE " + " AND ".join(clauses) +
                " ORDER BY created_at DESC, record_id"
            )
            sql_params: list[Any] = list(params)
        else:
            sql = (
                "SELECT record_id, batch_id, source_type, data_mode, payload, created_at "
                "FROM data_records WHERE " + " AND ".join(clauses) +
                " ORDER BY created_at DESC, record_id LIMIT ?"
            )
            sql_params = list(params) + [want_limit]
        with self.connect() as connection:
            rows = connection.execute(sql, sql_params).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            data = json.loads(row["payload"])
            if date_field is not None:
                value = str(data.get(date_field, ""))
                if start_date and value < str(start_date):
                    continue
                if end_date and value > str(end_date):
                    continue
            records.append({
                "record_id": row["record_id"],
                "batch_id": row["batch_id"],
                "source_type": row["source_type"],
                "data_mode": row["data_mode"],
                "created_at": row["created_at"],
                "data": data,
            })
            if date_field is None and len(records) >= want_limit:
                break
        if date_field is not None:
            records = records[:want_limit]
        return records

    def search_records(
        self,
        entity: str,
        *,
        keyword: str = "",
        filters: dict[str, Any] | None = None,
        source_type: str | None = None,
        data_mode: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search active records without exposing raw SQL to callers."""
        schema = self.list_schema(entity)
        active_fields = {field["name"] for field in schema["fields"] if field["active"]}
        safe_filters = {key: value for key, value in (filters or {}).items() if value not in (None, "")}
        unknown = sorted(set(safe_filters) - active_fields)
        if unknown:
            raise DataCoreError(f"unknown filter fields: {', '.join(unknown)}")

        records = self.list_records(
            entity,
            limit=1000,
            source_type=source_type,
            data_mode=data_mode,
            start_date=start_date,
            end_date=end_date,
        )
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
    def export_records(
        self,
        entity: str,
        *,
        format: str = "xlsx",
        data_mode: str | None = None,
        source_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 1000,
    ) -> tuple[bytes, str, str]:
        """Export active fields as CSV or XLSX bytes, respecting data-mode isolation."""
        if format not in {"xlsx", "csv"}:
            raise DataCoreError("export format 只能是 xlsx 或 csv")
        schema = self.list_schema(entity)
        headers = [field["name"] for field in schema["fields"] if field["active"]]
        records = self.list_records(
            entity,
            limit=max(1, min(limit, 1000)),
            source_type=source_type,
            data_mode=data_mode,
            start_date=start_date,
            end_date=end_date,
        )
        rows = [record["data"] for record in records]
        return build_export_bytes(f"{entity}.{format}", headers, rows)

    def list_batches(self, entity: str | None = None, data_mode: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM data_batches"
        params: tuple[Any, ...] = ()
        clauses: list[str] = []
        args: list[Any] = []
        if entity:
            clauses.append("entity = ?")
            args.append(entity)
        if data_mode:
            clauses.append("data_mode = ?")
            args.append(_normalize_data_mode(data_mode))
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
            params = tuple(args)
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
