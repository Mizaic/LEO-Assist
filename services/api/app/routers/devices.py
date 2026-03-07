"""Devices API — FHIR-aligned AI model catalog stored in the Knowledge Graph.

Routes
------
GET  /devices                     List all Device nodes
GET  /devices/pipeline-config     Active pipeline routing config
GET  /devices/{device_id}         Single device detail
PATCH /devices/{device_id}/status Enable or disable a device
PUT  /devices/pipeline-config     Update active provider / tier / backend
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.neo4j_client import CodingGraphClient
from libs.cypher.device_queries import (
    GET_DEVICE,
    GET_PIPELINE_CONFIG,
    LIST_DEVICES,
    SET_DEVICE_STATUS,
    UPSERT_PIPELINE_CONFIG,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])

_VALID_STATUSES = {"active", "inactive"}
_VALID_PROVIDERS = {"aws", "azure"}
_VALID_TIERS = {"small", "big", "max"}
_VALID_BACKENDS = {"llm", "model", "auto"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_model_id(env_var: str | None, default_model_id: str) -> str:
    """Return the actual model ID from env var, with default fallback.
    Secrets stay in Key Vault — we only show whether they are configured."""
    if not env_var:
        return default_model_id or ""
    val = os.getenv(env_var, "")
    return val if val else default_model_id


def _enrich(row: dict[str, Any]) -> dict[str, Any]:
    """Add resolved_model_id and env_var_set fields to a device row."""
    env_var: str | None = row.get("env_var") or None
    default_model_id: str = row.get("default_model_id") or ""
    resolved = _resolve_model_id(env_var, default_model_id)
    return {
        **row,
        "env_var": env_var or "",
        "default_model_id": default_model_id,
        "resolved_model_id": resolved,
        "env_var_set": bool(env_var and os.getenv(env_var, "")),
    }


# ---------------------------------------------------------------------------
# GET /devices
# ---------------------------------------------------------------------------

@router.get("")
def list_devices() -> dict[str, Any]:
    client = CodingGraphClient()
    try:
        with client.session() as session:
            rows = [_enrich(dict(r)) for r in session.run(LIST_DEVICES)]
        return {"devices": rows, "count": len(rows)}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# GET /devices/pipeline-config
# ---------------------------------------------------------------------------

@router.get("/pipeline-config")
def get_pipeline_config() -> dict[str, Any]:
    client = CodingGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_PIPELINE_CONFIG).single()
        if not row:
            # Return env-var defaults if no config node exists yet
            return {
                "provider": os.getenv("PIPELINE_MODEL_PROVIDER", "aws"),
                "tier": os.getenv("PIPELINE_MODEL_TIER", "small"),
                "extractor_backend": os.getenv("CODING_EXTRACTOR_BACKEND", "llm"),
                "strict": os.getenv("CODING_EXTRACTOR_STRICT", "false").lower() == "true",
                "consensus_mode": os.getenv("PIPELINE_CONSENSUS_MODE", "true").lower() == "true",
                "source": "env",
            }
        return {**dict(row), "source": "neo4j"}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# GET /devices/{device_id}
# ---------------------------------------------------------------------------

@router.get("/{device_id}")
def get_device(device_id: str) -> dict[str, Any]:
    client = CodingGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_DEVICE, device_id=device_id).single()
        if not row:
            raise HTTPException(status_code=404, detail=f"Device {device_id!r} not found")
        return _enrich(dict(row))
    finally:
        client.close()


# ---------------------------------------------------------------------------
# PATCH /devices/{device_id}/status
# ---------------------------------------------------------------------------

class StatusRequest(BaseModel):
    status: str  # "active" | "inactive"


@router.patch("/{device_id}/status")
def set_device_status(device_id: str, body: StatusRequest) -> dict[str, Any]:
    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {_VALID_STATUSES}")
    client = CodingGraphClient()
    try:
        with client.session() as session:
            row = session.run(SET_DEVICE_STATUS, device_id=device_id, status=body.status).single()
        if not row:
            raise HTTPException(status_code=404, detail=f"Device {device_id!r} not found")
        return {"device_id": row["device_id"], "status": row["status"]}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# PUT /devices/pipeline-config
# ---------------------------------------------------------------------------

class PipelineConfigRequest(BaseModel):
    provider: str          # "aws" | "azure"
    tier: str              # "small" | "big" | "max"
    extractor_backend: str # "llm" | "model" | "auto"
    strict: bool = False
    consensus_mode: bool = True  # dual-model parallel consensus with big-model arbitration


@router.put("/pipeline-config")
def update_pipeline_config(body: PipelineConfigRequest) -> dict[str, Any]:
    if body.provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"provider must be one of {_VALID_PROVIDERS}")
    if body.tier not in _VALID_TIERS:
        raise HTTPException(status_code=400, detail=f"tier must be one of {_VALID_TIERS}")
    if body.extractor_backend not in _VALID_BACKENDS:
        raise HTTPException(status_code=400, detail=f"extractor_backend must be one of {_VALID_BACKENDS}")

    client = CodingGraphClient()
    try:
        with client.session() as session:
            session.run(
                UPSERT_PIPELINE_CONFIG,
                provider=body.provider,
                tier=body.tier,
                extractor_backend=body.extractor_backend,
                strict=body.strict,
                consensus_mode=body.consensus_mode,
            )
        logger.info(
            "PipelineConfig updated: provider=%s tier=%s backend=%s strict=%s consensus=%s",
            body.provider, body.tier, body.extractor_backend, body.strict, body.consensus_mode,
        )
        return {
            "updated": True,
            "provider": body.provider,
            "tier": body.tier,
            "extractor_backend": body.extractor_backend,
            "strict": body.strict,
            "consensus_mode": body.consensus_mode,
        }
    finally:
        client.close()
