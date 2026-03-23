"""ModelConfig CRUD + LLM spend analytics router.

Exposes:
  GET    /model-configs                 — list all ModelConfig nodes
  POST   /model-configs                 — create a new ModelConfig node
  PUT    /model-configs/{key}           — update rates (marks source='user')
  DELETE /model-configs/{key}           — remove a ModelConfig node
  GET  /analytics/llm-spend/patient   — per-patient token + cost history
  GET  /analytics/llm-spend/org       — org-level aggregate spend
  GET  /analytics/llm-spend/runs      — pipeline run spend (AuditEvent)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.db.neo4j_client import CodingGraphClient, PatientGraphClient
from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.cypher.model_config_queries import (
    CREATE_MODEL_CONFIG,
    DELETE_MODEL_CONFIG,
    GET_MODEL_CONFIG,
    GET_AUDIT_EVENT_SPEND,
    GET_PATIENT_LLM_SPEND,
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
    key: str            # e.g. "aws:small" or "custom:my-model"
    provider: str       # e.g. "aws" | "azure" | "custom"
    tier: str           # e.g. "small" | "big" | "max"
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
        "key":                row.get("key", ""),
        "provider":           row.get("provider", ""),
        "tier":               row.get("tier", ""),
        "displayName":        row.get("displayName", ""),
        "modelId":            row.get("modelId", ""),
        "costPer1mInput":     float(row.get("costPer1mInput") or 0),
        "costPer1mCachedInput": float(row.get("costPer1mCachedInput") or 0),
        "costPer1mOutput":    float(row.get("costPer1mOutput") or 0),
        "isActive":           bool(row.get("isActive", True)),
        "source":             row.get("source", "seed"),
        "updatedAt":          str(row.get("updatedAt") or ""),
    }


def _service_row_to_dict(row: dict) -> dict[str, Any]:
    raw_config = row.get("configJson") or "{}"
    try:
        config = json.loads(raw_config) if isinstance(raw_config, str) else dict(raw_config or {})
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
    scope: CallerScope = Depends(get_caller_scope),
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
    scope: CallerScope = Depends(get_caller_scope),
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
    scope: CallerScope = Depends(get_caller_scope),
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
    scope: CallerScope = Depends(get_caller_scope),
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


# ── LLM spend analytics ───────────────────────────────────────────────────────

@router.get("/analytics/llm-spend/patient")
def patient_llm_spend(
    patient_id: str = Query(...),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    scope: CallerScope = Depends(get_caller_scope),
):
    """Return per-encounter LLM usage for a patient."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                GET_PATIENT_LLM_SPEND,
                patient_id=patient_id,
                from_date=from_date,
                to_date=to_date,
            ).data()
    finally:
        client.close()

    encounters = []
    total_input = total_output = total_cached = total_cost = 0
    for row in rows:
        usage: dict = {}
        raw = row.get("llmUsageJson")
        if raw:
            try:
                usage = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                usage = {}
        enc = {
            "candidateId":  row.get("candidateId", ""),
            "encounterId":  row.get("encounterId", ""),
            "updatedAt":    str(row.get("updatedAt") or ""),
            "modelName":    row.get("modelName", ""),
            "inputTokens":  int(usage.get("input_tokens", 0)),
            "outputTokens": int(usage.get("output_tokens", 0)),
            "cachedTokens": int(usage.get("cached_input_tokens", 0)),
            "costUsd":      float(usage.get("cost_usd") or 0),
        }
        encounters.append(enc)
        total_input   += enc["inputTokens"]
        total_output  += enc["outputTokens"]
        total_cached  += enc["cachedTokens"]
        total_cost    += enc["costUsd"]

    return {
        "patientId":    patient_id,
        "encounters":   encounters,
        "totals": {
            "inputTokens":  total_input,
            "outputTokens": total_output,
            "cachedTokens": total_cached,
            "costUsd":      round(total_cost, 6),
            "cacheHitRate": round(total_cached / total_input, 4) if total_input > 0 else 0,
        },
    }


@router.get("/analytics/llm-spend/runs")
def run_llm_spend(
    patient_id: str | None = Query(None),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    limit: int = Query(100, le=500),
    scope: CallerScope = Depends(get_caller_scope),
):
    """Return per-pipeline-run LLM token spend from AuditEvent nodes."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                GET_AUDIT_EVENT_SPEND,
                patient_id=patient_id,
                from_date=from_date,
                to_date=to_date,
                limit=limit,
            ).data()
    finally:
        client.close()

    runs = []
    total_input = total_output = total_cached = total_cost = 0
    for row in rows:
        run = {
            "runId":        row.get("runId", ""),
            "patientId":    row.get("patientId", ""),
            "encounterId":  row.get("encounterId", ""),
            "status":       row.get("status", ""),
            "durationMs":   int(row.get("durationMs") or 0),
            "inputTokens":  int(row.get("inputTokens") or 0),
            "outputTokens": int(row.get("outputTokens") or 0),
            "cachedTokens": int(row.get("cachedTokens") or 0),
            "costUsd":      float(row.get("costUsd") or 0),
            "createdAt":    str(row.get("createdAt") or ""),
        }
        runs.append(run)
        total_input   += run["inputTokens"]
        total_output  += run["outputTokens"]
        total_cached  += run["cachedTokens"]
        total_cost    += run["costUsd"]

    return {
        "runs": runs,
        "totals": {
            "runCount":     len(runs),
            "inputTokens":  total_input,
            "outputTokens": total_output,
            "cachedTokens": total_cached,
            "costUsd":      round(total_cost, 6),
            "cacheHitRate": round(total_cached / total_input, 4) if total_input > 0 else 0,
        },
    }
