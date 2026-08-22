# -*- coding: utf-8 -*-
"""QwenPaw HTTP facade for the unified Data Core."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from qwenpaw.plugins.api import PluginApi

try:
    from .data_core import DataCore, DataCoreError, default_database
    from .agent_tools import build_agent_tools
    from .table_parser import parse_table
except ImportError:
    from data_core import DataCore, DataCoreError, default_database
    from agent_tools import build_agent_tools
    from table_parser import parse_table

core = DataCore(default_database())
router = APIRouter()
MAX_UPLOAD = 20 * 1024 * 1024


class FieldCreate(BaseModel):
    name: str
    label: str
    field_type: str = "text"
    required: bool = False


class FieldPatch(BaseModel):
    label: str | None = None
    active: bool | None = None


class SchemaFieldCreate(BaseModel):
    name: str
    label: str
    field_type: str = "text"
    required: bool = False


class SchemaCreate(BaseModel):
    entity: str
    label: str
    fields: list[SchemaFieldCreate] = Field(min_length=1, max_length=100)


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


@router.get("/entities")
async def entities() -> dict[str, Any]:
    return {"entities": core.list_entities()}


@router.post("/parse")
async def parse_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="文件不能超过20MB")
    try:
        return parse_table(file.filename or "upload", content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/schemas")
async def create_schema(request: SchemaCreate) -> dict[str, Any]:
    return _handle(
        lambda: core.create_schema(
            request.entity,
            request.label,
            [field.model_dump() for field in request.fields],
        )
    )


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


@router.post("/simulate/production")
async def simulate_production(request: SimulationCreate) -> dict[str, Any]:
    return _handle(lambda: core.generate_production(request.count, request.seed))


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


@router.get("/orders")
async def orders(
    keyword: str = Query(default="", max_length=200),
    order_no: str = Query(default="", max_length=200),
    customer_name: str = Query(default="", max_length=200),
    status: str = Query(default="", max_length=200),
    source_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    """Expose the bounded order query contract used by business PawApps."""
    filters = {
        key: value
        for key, value in {
            "order_no": order_no,
            "customer_name": customer_name,
            "status": status,
        }.items()
        if value
    }
    def query() -> dict[str, Any]:
        records = core.search_records(
            "orders",
            keyword=keyword,
            filters=filters,
            source_type=source_type,
            limit=limit,
        )
        return {
            "entity": "orders",
            "count": len(records),
            "keyword": keyword,
            "filters": filters,
            "source_type": source_type,
            "records": records,
        }
    return _handle(query)


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
        query_orders, simulate_orders_tool = build_agent_tools(core)
        api.register_tool(
            tool_name="query_enterprise_orders",
            tool_func=query_orders,
            description="查询统一数据库中的企业订单、客户、状态和交付进度；回答订单问题时优先调用。",
            icon="🔎",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="generate_simulated_production",
            tool_func=lambda count=60, seed=None: core.generate_production(count, seed),
            description="按用户明确要求生成可撤销的模拟生产日报，用于测试部门人效、成本和损耗指标。",
            icon="🏭",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="generate_simulated_orders",
            tool_func=simulate_orders_tool,
            description="按用户明确要求生成可撤销的模拟订单数据，并返回批次 ID。",
            icon="🧪",
            tool_type="internal",
        )


plugin = DataCorePlugin()
