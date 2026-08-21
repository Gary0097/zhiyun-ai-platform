# -*- coding: utf-8 -*-
"""QwenPaw HTTP facade for the unified Data Core."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from qwenpaw.plugins.api import PluginApi

try:
    from .data_core import DataCore, DataCoreError, default_database
except ImportError:
    from data_core import DataCore, DataCoreError, default_database

core = DataCore(default_database())
router = APIRouter()


class FieldCreate(BaseModel):
    name: str
    label: str
    field_type: str = "text"
    required: bool = False


class FieldPatch(BaseModel):
    label: str | None = None
    active: bool | None = None


class ImportPreview(BaseModel):
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=10000)
    mapping: dict[str, str] | None = None
    source_name: str = "manual-import"


class SimulationCreate(BaseModel):
    count: int = Field(default=50, ge=1, le=5000)
    seed: int | None = None


def _handle(action):
    try:
        return action()
    except DataCoreError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "available", "database": str(core.database), "schema_version": 1}


@router.get("/schemas/{entity}")
async def schema(entity: str) -> dict[str, Any]:
    return _handle(lambda: core.list_schema(entity))


@router.post("/schemas/{entity}/fields")
async def add_field(entity: str, request: FieldCreate) -> dict[str, Any]:
    return _handle(
        lambda: core.add_field(entity, request.name, request.label, request.field_type, request.required)
    )


@router.patch("/schemas/{entity}/fields/{field_name}")
async def update_field(entity: str, field_name: str, request: FieldPatch) -> dict[str, Any]:
    return _handle(
        lambda: core.update_field(entity, field_name, label=request.label, active=request.active)
    )


@router.post("/imports/{entity}/preview")
async def preview_import(entity: str, request: ImportPreview) -> dict[str, Any]:
    return _handle(lambda: core.preview_import(entity, request.rows, request.mapping))


@router.post("/imports/{entity}/commit")
async def commit_import(entity: str, request: ImportPreview) -> dict[str, Any]:
    return _handle(
        lambda: core.import_rows(
            entity,
            request.rows,
            mapping=request.mapping,
            source_name=request.source_name,
        )
    )


@router.post("/simulate/orders")
async def simulate_orders(request: SimulationCreate) -> dict[str, Any]:
    return _handle(lambda: core.generate_orders(request.count, request.seed))


@router.get("/records/{entity}")
async def records(
    entity: str,
    limit: int = Query(default=100, ge=1, le=1000),
    source_type: str | None = None,
) -> dict[str, Any]:
    return _handle(
        lambda: {
            "entity": entity,
            "records": core.list_records(entity, limit=limit, source_type=source_type),
        }
    )


@router.get("/batches")
async def batches(entity: str | None = None) -> dict[str, Any]:
    return {"batches": core.list_batches(entity)}


@router.post("/batches/{batch_id}/rollback")
async def rollback(batch_id: str) -> dict[str, Any]:
    return _handle(lambda: core.rollback_batch(batch_id))


class DataCorePlugin:
    """Register a private, same-origin Data Core API without another port."""

    def register(self, api: PluginApi) -> None:
        api.register_http_router(router, prefix="/zhiyun-data-core", tags=["zhiyun-data-core"])


plugin = DataCorePlugin()
