"""LLM spend analytics router.

Atlas trace:
  DO: DO-4D2BEA1D
  DI: DI-CDF1C4D4
  UN: UN-9828175D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4D2BEA1D")

Extracted from services/api/app/routers/model_configs.py (2026-07 CTO
peer-review item 2: core-api router decomposition -- model_configs.py mixed
ModelConfig/ServiceConfig CRUD with LLM spend/billing analytics, a
cross-cutting concern flagged in the review). Pure move, no behaviour
change, no URL path change.

(2026-07 cost/spend user-need review: the trace header originally carried
over from model_configs.py cited DO-EC41233C/DI-9D0DF618, which do not
exist in Atlas -- corrected here to the real DO/DI created for this
capability. model_configs.py's own header still cites the same phantom
pair for ModelConfig/ServiceConfig CRUD and needs separate investigation.)

Exposes:
  GET /analytics/llm-spend/patient   -- per-patient token + cost history
  GET /analytics/llm-spend/runs      -- pipeline run spend (AuditEvent)
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.neo4j_client import PatientGraphClient
from libs.auth.org_scope import (
    CallerScope,
    get_caller_scope,
    require_patient_in_scope,
)
from libs.cypher.model_config_queries import (
    GET_AUDIT_EVENT_SPEND,
    GET_AUDIT_EVENT_SPEND_TOTALS,
    GET_PATIENT_LLM_SPEND,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["model-configs"])


@router.get("/analytics/llm-spend/patient")
def patient_llm_spend(
    patient_id: str = Query(...),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    scope: CallerScope = Depends(get_caller_scope),
):
    """Return per-encounter LLM usage for a patient.

    Tenant scoping: non-admin callers may only query patients whose
    registered GP is within their org hierarchy. The check raises 404
    (deliberately indistinguishable from a non-existent patient) when
    the caller is out of scope, so the endpoint cannot be used to
    enumerate patient ids belonging to other tenants.
    """
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
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
            "candidateId": row.get("candidateId", ""),
            "encounterId": row.get("encounterId", ""),
            "updatedAt": str(row.get("updatedAt") or ""),
            "modelName": row.get("modelName", ""),
            "inputTokens": int(usage.get("input_tokens", 0)),
            "outputTokens": int(usage.get("output_tokens", 0)),
            "cachedTokens": int(usage.get("cached_input_tokens", 0)),
            "costUsd": float(usage.get("cost_usd") or 0),
            "source": row.get("source") or "coding_extraction",
        }
        encounters.append(enc)
        total_input += enc["inputTokens"]
        total_output += enc["outputTokens"]
        total_cached += enc["cachedTokens"]
        total_cost += enc["costUsd"]

    return {
        "patientId": patient_id,
        "encounters": encounters,
        "totals": {
            "inputTokens": total_input,
            "outputTokens": total_output,
            "cachedTokens": total_cached,
            "costUsd": round(total_cost, 6),
            "cacheHitRate": (
                round(total_cached / total_input, 4) if total_input > 0 else 0
            ),
        },
    }


@router.get("/analytics/llm-spend/runs")
def run_llm_spend(
    patient_id: str | None = Query(None),
    org_id: str | None = Query(None),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    limit: int = Query(100, le=500),
    scope: CallerScope = Depends(get_caller_scope),
):
    """Return per-pipeline-run LLM token spend from AuditEvent nodes.

    Totals are computed from the full date range (no limit) so they are
    never under-counted when the run list is capped. Org scoping restricts
    results to patients in the caller's org hierarchy.
    """
    is_admin = scope.is_admin
    org_ids = scope.org_ids or []
    selected_org_id = (org_id or "").strip() or None

    if selected_org_id and (not is_admin) and (selected_org_id not in org_ids):
        raise HTTPException(status_code=403, detail="org_id is outside your scope")

    shared_params: dict = {
        "patient_id": patient_id,
        "selected_org_id": selected_org_id,
        "from_date": from_date,
        "to_date": to_date,
        "is_admin": is_admin,
        "org_ids": org_ids,
    }

    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                GET_AUDIT_EVENT_SPEND,
                **shared_params,
                limit=limit,
            ).data()
            agg_rows = session.run(
                GET_AUDIT_EVENT_SPEND_TOTALS,
                **shared_params,
            ).data()
    finally:
        client.close()

    runs = [
        {
            "runId": row.get("runId", ""),
            "patientId": row.get("patientId", ""),
            "encounterId": row.get("encounterId", ""),
            "status": row.get("status", ""),
            "durationMs": int(row.get("durationMs") or 0),
            "inputTokens": int(row.get("inputTokens") or 0),
            "outputTokens": int(row.get("outputTokens") or 0),
            "cachedTokens": int(row.get("cachedTokens") or 0),
            "costUsd": float(row.get("costUsd") or 0),
            "createdAt": str(row.get("createdAt") or ""),
        }
        for row in rows
    ]

    agg = agg_rows[0] if agg_rows else {}
    total_input = int(agg.get("inputTokens") or 0)
    total_output = int(agg.get("outputTokens") or 0)
    total_cached = int(agg.get("cachedTokens") or 0)
    total_cost = float(agg.get("costUsd") or 0)
    run_count = int(agg.get("runCount") or 0)

    return {
        "runs": runs,
        "totals": {
            "runCount": run_count,
            "inputTokens": total_input,
            "outputTokens": total_output,
            "cachedTokens": total_cached,
            "costUsd": round(total_cost, 6),
            "cacheHitRate": (
                round(total_cached / total_input, 4) if total_input > 0 else 0
            ),
        },
    }
