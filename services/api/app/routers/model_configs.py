"""ModelConfig + ServiceConfig CRUD router.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")

Exposes:
  GET    /model-configs                 — list all ModelConfig nodes
  POST   /model-configs                 — create a new ModelConfig node
  PUT    /model-configs/{key}           — update rates (marks source='user')
  DELETE /model-configs/{key}           — remove a ModelConfig node
  GET/PUT /service-configs[/{key}]      — service configuration CRUD

LLM spend analytics (GET /analytics/llm-spend/patient, /runs) moved to
app/routers/llm_usage.py (2026-07 CTO peer-review item 2: core-api router
decomposition -- billing/observability is a distinct concern from
provider/pricing config CRUD). No URL path changed.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.neo4j_client import CodingGraphClient
from app.deps import require_admin
from libs.auth.org_scope import (
    CallerScope,
    get_caller_scope,
)
from libs.cypher.model_config_queries import (
    CREATE_MODEL_CONFIG,
    DELETE_MODEL_CONFIG,
    GET_MODEL_CONFIG,
    LIST_MODEL_CONFIGS,
    UPDATE_MODEL_CONFIG,
)
from libs.cypher.service_config_queries import (
    GET_SERVICE_CONFIG,
    LIST_SERVICE_CONFIGS,
    UPSERT_SERVICE_CONFIG,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["model-configs"])


# ── Pydantic models ───────────────────────────────────────────────────────────


class ModelConfigCreate(BaseModel):
    key: str  # e.g. "aws:small" or "custom:my-model"
    provider: str  # e.g. "aws" | "azure" | "custom"
    tier: str  # e.g. "small" | "big" | "max"
    displayName: str
    modelId: str
    costPer1mInput: float = 0.0
    costPer1mCachedInput: float = 0.0
    costPer1mOutput: float = 0.0
    isActive: bool = True


class ModelConfigUpdate(BaseModel):
    displayName: str
    modelId: str
    costPer1mInput: float
    costPer1mCachedInput: float
    costPer1mOutput: float
    isActive: bool = True


class ServiceConfigUpdate(BaseModel):
    category: str
    displayName: str
    description: str = ""
    config: dict[str, Any]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _row_to_dict(row: dict) -> dict[str, Any]:
    return {
        "key": row.get("key", ""),
        "provider": row.get("provider", ""),
        "tier": row.get("tier", ""),
        "displayName": row.get("displayName", ""),
        "modelId": row.get("modelId", ""),
        "costPer1mInput": float(row.get("costPer1mInput") or 0),
        "costPer1mCachedInput": float(row.get("costPer1mCachedInput") or 0),
        "costPer1mOutput": float(row.get("costPer1mOutput") or 0),
        "isActive": bool(row.get("isActive", True)),
        "source": row.get("source", "seed"),
        "updatedAt": str(row.get("updatedAt") or ""),
    }


def _service_row_to_dict(row: dict) -> dict[str, Any]:
    raw_config = row.get("configJson") or "{}"
    try:
        config = (
            json.loads(raw_config)
            if isinstance(raw_config, str)
            else dict(raw_config or {})
        )
    except Exception:
        config = {}
    return {
        "key": row.get("key", ""),
        "category": row.get("category", ""),
        "displayName": row.get("displayName", ""),
        "description": row.get("description", ""),
        "config": config,
        "source": row.get("source", "seed"),
        "updatedAt": str(row.get("updatedAt") or ""),
    }


# ── ModelConfig CRUD ──────────────────────────────────────────────────────────


@router.get("/model-configs")
def list_model_configs(scope: CallerScope = Depends(get_caller_scope)):
    client = CodingGraphClient()
    try:
        with client.session() as session:
            rows = session.run(LIST_MODEL_CONFIGS).data()
        return {"modelConfigs": [_row_to_dict(r) for r in rows]}
    finally:
        client.close()


@router.post("/model-configs", status_code=201)
def create_model_config(
    body: ModelConfigCreate,
    scope: CallerScope = Depends(require_admin),
):
    client = CodingGraphClient()
    try:
        with client.session() as session:
            existing = session.run(GET_MODEL_CONFIG, id=body.key).single()
            if existing:
                raise HTTPException(409, f"ModelConfig {body.key!r} already exists")
            session.run(
                CREATE_MODEL_CONFIG,
                key=body.key,
                provider=body.provider,
                tier=body.tier,
                display_name=body.displayName,
                model_id=body.modelId,
                cost_per_1m_input=body.costPer1mInput,
                cost_per_1m_cached=body.costPer1mCachedInput,
                cost_per_1m_output=body.costPer1mOutput,
                is_active=body.isActive,
            )
        logger.info("ModelConfig %r created by user", body.key)
        return {"key": body.key, "status": "created"}
    finally:
        client.close()


@router.delete("/model-configs/{key:path}", status_code=200)
def delete_model_config(
    key: str,
    scope: CallerScope = Depends(require_admin),
):
    client = CodingGraphClient()
    try:
        with client.session() as session:
            result = session.run(DELETE_MODEL_CONFIG, key=key).single()
        if not result or result["deleted"] == 0:
            raise HTTPException(404, f"ModelConfig {key!r} not found")
        logger.info("ModelConfig %r deleted", key)
        return {"key": key, "status": "deleted"}
    finally:
        client.close()


@router.put("/model-configs/{key:path}")
def update_model_config(
    key: str,
    body: ModelConfigUpdate,
    scope: CallerScope = Depends(require_admin),
):
    client = CodingGraphClient()
    try:
        with client.session() as session:
            result = session.run(
                UPDATE_MODEL_CONFIG,
                key=key,
                display_name=body.displayName,
                model_id=body.modelId,
                cost_per_1m_input=body.costPer1mInput,
                cost_per_1m_cached=body.costPer1mCachedInput,
                cost_per_1m_output=body.costPer1mOutput,
                is_active=body.isActive,
            ).single()
        if not result:
            raise HTTPException(404, f"ModelConfig {key!r} not found")
        return {"key": key, "status": "updated"}
    finally:
        client.close()


@router.get("/service-configs")
def list_service_configs(scope: CallerScope = Depends(get_caller_scope)):
    client = CodingGraphClient()
    try:
        with client.session() as session:
            rows = session.run(LIST_SERVICE_CONFIGS).data()
        return {"serviceConfigs": [_service_row_to_dict(r) for r in rows]}
    finally:
        client.close()


@router.get("/service-configs/{key:path}")
def get_service_config(
    key: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    client = CodingGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_SERVICE_CONFIG, key=key).single()
        if not row:
            raise HTTPException(404, f"ServiceConfig {key!r} not found")
        return _service_row_to_dict(dict(row))
    finally:
        client.close()


@router.put("/service-configs/{key:path}")
def upsert_service_config(
    key: str,
    body: ServiceConfigUpdate,
    scope: CallerScope = Depends(require_admin),
):
    client = CodingGraphClient()
    try:
        with client.session() as session:
            session.run(
                UPSERT_SERVICE_CONFIG,
                key=key,
                category=body.category,
                display_name=body.displayName,
                description=body.description,
                config_json=json.dumps(body.config, sort_keys=True),
                source="user",
            )
        logger.info("ServiceConfig %r upserted", key)
        return {"key": key, "status": "updated"}
    finally:
        client.close()
