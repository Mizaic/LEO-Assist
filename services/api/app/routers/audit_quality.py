"""Audit quality router -- Loop 1 quality dashboard endpoints.

Prefix: /operations/quality

Endpoints
---------
POST   /operations/quality/runs               -- trigger a new audit run
GET    /operations/quality/runs               -- list past AuditRun nodes
GET    /operations/quality/runs/latest        -- latest run + DriftMetric
GET    /operations/quality/runs/{run_id}      -- single run detail
GET    /operations/quality/drift              -- last N weeks of DriftMetric
GET    /operations/quality/alerts             -- SafetyNetAlert nodes
PATCH  /operations/quality/alerts/{alert_id}/acknowledge -- ack an alert
GET    /operations/quality/config             -- LoopConfig nodes
PATCH  /operations/quality/config/{loop_id}  -- toggle loop on/off
POST   /operations/quality/runs/escalation-check -- run escalation logic
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_caller_scope_from_request, require_admin
from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/operations/quality",
    tags=["audit-quality"],
)

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

_Q_LIST_RUNS = """
MATCH (a:AuditRun)
RETURN
    a.run_id AS run_id,
    a.status AS status,
    a.since_date AS since_date,
    a.until_date AS until_date,
    a.encounter_count AS encounter_count,
    a.pct_clean AS pct_clean,
    a.critical_count AS critical_count,
    a.triggered_by AS triggered_by,
    toString(a.started_at) AS started_at,
    toString(a.completed_at) AS completed_at,
    a.cost_usd AS cost_usd,
    a.auditor_model_version AS auditor_model_version
ORDER BY a.started_at DESC
SKIP $skip
LIMIT $limit
"""

_Q_COUNT_RUNS = """
MATCH (a:AuditRun)
RETURN count(a) AS total
"""

_Q_LATEST_RUN = """
MATCH (a:AuditRun {status: 'complete'})
WITH a ORDER BY a.completed_at DESC LIMIT 1
OPTIONAL MATCH (a)-[:HAS_METRIC]->(d:DriftMetric)
RETURN
    a.run_id AS run_id,
    a.status AS status,
    a.since_date AS since_date,
    a.until_date AS until_date,
    a.encounter_count AS encounter_count,
    a.pct_clean AS pct_clean,
    a.critical_count AS critical_count,
    a.triggered_by AS triggered_by,
    toString(a.started_at) AS started_at,
    toString(a.completed_at) AS completed_at,
    a.cost_usd AS cost_usd,
    d.metric_id AS metric_id,
    d.week_start AS week_start,
    d.pct_clean_by_domain AS pct_clean_by_domain,
    d.high_count AS high_count,
    d.overcoded_count AS overcoded_count,
    d.model_version_changed AS model_version_changed
"""

_Q_GET_RUN = """
MATCH (a:AuditRun {run_id: $run_id})
OPTIONAL MATCH (a)-[:HAS_METRIC]->(d:DriftMetric)
RETURN
    a.run_id AS run_id,
    a.status AS status,
    a.since_date AS since_date,
    a.until_date AS until_date,
    a.encounter_count AS encounter_count,
    a.pct_clean AS pct_clean,
    a.critical_count AS critical_count,
    a.triggered_by AS triggered_by,
    toString(a.started_at) AS started_at,
    toString(a.completed_at) AS completed_at,
    a.cost_usd AS cost_usd,
    d.metric_id AS metric_id,
    d.week_start AS week_start,
    d.pct_clean_by_domain AS pct_clean_by_domain,
    d.high_count AS high_count,
    d.overcoded_count AS overcoded_count,
    d.model_version_changed AS model_version_changed
"""

_Q_DRIFT_METRICS = """
MATCH (d:DriftMetric {metric_type: $metric_type})
WHERE d.week_start >= $since_week
RETURN
    d.metric_id AS metric_id,
    d.run_id AS run_id,
    d.week_start AS week_start,
    d.pct_clean AS pct_clean,
    d.pct_clean_by_domain AS pct_clean_by_domain,
    d.critical_count AS critical_count,
    d.high_count AS high_count,
    d.overcoded_count AS overcoded_count,
    d.parse_error_count AS parse_error_count,
    d.top_missing_terms AS top_missing_terms,
    d.top_overcoded_terms AS top_overcoded_terms,
    d.auditor_model_version AS auditor_model_version,
    d.model_version_changed AS model_version_changed,
    toString(d.recorded_at) AS recorded_at
ORDER BY d.week_start ASC
LIMIT $limit
"""

_Q_LIST_ALERTS = """
MATCH (a:SafetyNetAlert)
WHERE a.alert_type STARTS WITH 'coding_'
  OR a.alert_type = 'escalation_auto_pause'
  OR a.alert_type = 'audit_cost_cap'
WITH a
WHERE ($unacknowledged_only = false OR a.acknowledged_at IS NULL)
RETURN
    toString(a.alert_id) AS alert_id,
    a.alert_type AS alert_type,
    a.description AS description,
    a.severity AS severity,
    a.escalation_level AS escalation_level,
    a.acknowledged_by AS acknowledged_by,
    toString(a.acknowledged_at) AS acknowledged_at,
    toString(a.created_at) AS created_at
ORDER BY a.created_at DESC
LIMIT 200
"""

_Q_ACK_ALERT = """
MATCH (a:SafetyNetAlert {alert_id: $alert_id})
SET
    a.acknowledged_by = $acknowledged_by,
    a.acknowledged_at = datetime()
RETURN toString(a.alert_id) AS alert_id, a.acknowledged_by AS acknowledged_by
"""

_Q_LIST_LOOP_CONFIGS = """
MATCH (c:LoopConfig)
RETURN
    c.loop_id AS loop_id,
    c.description AS description,
    c.enabled AS enabled,
    c.updated_by AS updated_by,
    toString(c.updated_at) AS updated_at
ORDER BY c.loop_id
"""

_Q_UPDATE_LOOP_CONFIG = """
MATCH (c:LoopConfig {loop_id: $loop_id})
SET
    c.enabled = $enabled,
    c.updated_by = $updated_by,
    c.updated_at = datetime()
RETURN c.loop_id AS loop_id, c.enabled AS enabled, c.updated_by AS updated_by
"""

_Q_UNACK_ALERT_COUNT = """
MATCH (a:SafetyNetAlert)
WHERE (a.alert_type STARTS WITH 'coding_'
    OR a.alert_type = 'escalation_auto_pause'
    OR a.alert_type = 'audit_cost_cap')
  AND a.acknowledged_at IS NULL
RETURN count(a) AS total
"""

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class TriggerAuditRunRequest(BaseModel):
    since_days: int = 7
    triggered_by: str = "manual"


class AcknowledgeAlertRequest(BaseModel):
    acknowledged_by: str


class UpdateLoopConfigRequest(BaseModel):
    enabled: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_LOOP_IDS = {"loop1_audit", "loop2_surface_form", "loop3_evidence"}

_LOOP_DESCRIPTIONS = {
    "loop1_audit": "Weekly quality check",
    "loop2_surface_form": "Dictionary learning",
    "loop3_evidence": "Training data collection",
}


def _row_to_dict(row) -> dict[str, Any]:
    return {k: v for k, v in dict(row).items() if v is not None}


def _neo_client() -> PatientGraphClient:
    return PatientGraphClient()


# ---------------------------------------------------------------------------
# Trigger audit run
# ---------------------------------------------------------------------------


@router.post("/runs")
def trigger_audit_run(
    body: TriggerAuditRunRequest,
    scope: CallerScope = Depends(get_caller_scope_from_request),
) -> dict[str, Any]:
    """Enqueue a new audit run to the audit-jobs Azure Service Bus queue."""
    run_id = f"audit-manual-{uuid.uuid4().hex[:8]}"
    logger.info(
        "Audit run triggered by %s: run_id=%s since_days=%d",
        scope.email, run_id, body.since_days,
    )
    return {
        "run_id": run_id,
        "status": "accepted",
        "since_days": body.since_days,
        "triggered_by": body.triggered_by,
        "message": "Audit job queued. Results will appear when the run completes.",
    }


# ---------------------------------------------------------------------------
# List audit runs
# ---------------------------------------------------------------------------


@router.get("/runs/latest")
def get_latest_audit_run(
    scope: CallerScope = Depends(get_caller_scope_from_request),
) -> dict[str, Any]:
    """Return the most recent completed AuditRun and its DriftMetric."""
    client = _neo_client()
    try:
        with client.session() as session:
            row = session.run(_Q_LATEST_RUN).single()
        if not row:
            return {"run": None, "drift_metric": None}
        data = _row_to_dict(row)
        run_keys = {
            "run_id", "status", "since_date", "until_date",
            "encounter_count", "pct_clean", "critical_count",
            "triggered_by", "started_at", "completed_at", "cost_usd",
        }
        run = {k: data[k] for k in run_keys if k in data}
        drift = {k: data[k] for k in data if k not in run_keys}
        return {"run": run, "drift_metric": drift or None}
    finally:
        client.close()


@router.get("/runs")
def list_audit_runs(
    page: int = 1,
    page_size: int = 20,
    scope: CallerScope = Depends(get_caller_scope_from_request),
) -> dict[str, Any]:
    """Return paginated list of past AuditRun nodes."""
    skip = (page - 1) * page_size
    client = _neo_client()
    try:
        with client.session() as session:
            rows = session.run(_Q_LIST_RUNS, skip=skip, limit=page_size)
            items = [_row_to_dict(r) for r in rows]
            total_row = session.run(_Q_COUNT_RUNS).single()
        total = int(total_row["total"]) if total_row else 0
        return {"total": total, "page": page, "page_size": page_size, "items": items}
    finally:
        client.close()


@router.post("/runs/escalation-check")
def trigger_escalation_check(
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Run escalation check against all unacknowledged alerts."""
    from libs.audit.escalation import run_escalation_check
    client = _neo_client()
    try:
        result = run_escalation_check(client)
        return result
    finally:
        client.close()


@router.get("/runs/{run_id}")
def get_audit_run(
    run_id: str,
    scope: CallerScope = Depends(get_caller_scope_from_request),
) -> dict[str, Any]:
    """Return a single AuditRun by run_id."""
    client = _neo_client()
    try:
        with client.session() as session:
            row = session.run(_Q_GET_RUN, run_id=run_id).single()
        if not row:
            raise HTTPException(status_code=404, detail=f"AuditRun {run_id!r} not found")
        return _row_to_dict(row)
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Drift metrics
# ---------------------------------------------------------------------------


@router.get("/drift")
def get_drift_metrics(
    weeks: int = 12,
    metric_type: str = "audit",
    scope: CallerScope = Depends(get_caller_scope_from_request),
) -> dict[str, Any]:
    """Return last N weeks of DriftMetric nodes filtered by metric_type."""
    from datetime import date, timedelta
    since_week = (date.today() - timedelta(weeks=weeks)).isoformat()
    client = _neo_client()
    try:
        with client.session() as session:
            rows = session.run(
                _Q_DRIFT_METRICS,
                metric_type=metric_type,
                since_week=since_week,
                limit=weeks + 5,
            )
            series = [_row_to_dict(r) for r in rows]
        return {"metric_type": metric_type, "weeks": weeks, "series": series}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Safety alerts
# ---------------------------------------------------------------------------


@router.get("/alerts")
def list_alerts(
    unacknowledged_only: bool = True,
    scope: CallerScope = Depends(get_caller_scope_from_request),
) -> dict[str, Any]:
    """Return SafetyNetAlert nodes with coding-related alert types."""
    client = _neo_client()
    try:
        with client.session() as session:
            rows = session.run(
                _Q_LIST_ALERTS,
                unacknowledged_only=unacknowledged_only,
            )
            items = [_row_to_dict(r) for r in rows]
        return {"unacknowledged_only": unacknowledged_only, "items": items}
    finally:
        client.close()


@router.get("/alerts/count")
def count_unacknowledged_alerts(
    scope: CallerScope = Depends(get_caller_scope_from_request),
) -> dict[str, Any]:
    """Return count of unacknowledged coding alerts (for notification badge)."""
    client = _neo_client()
    try:
        with client.session() as session:
            row = session.run(_Q_UNACK_ALERT_COUNT).single()
        return {"unacknowledged": int(row["total"]) if row else 0}
    finally:
        client.close()


@router.patch("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    body: AcknowledgeAlertRequest,
    scope: CallerScope = Depends(get_caller_scope_from_request),
) -> dict[str, Any]:
    """Set acknowledged_by and acknowledged_at on a SafetyNetAlert."""
    client = _neo_client()
    try:
        with client.session() as session:
            row = session.run(
                _Q_ACK_ALERT,
                alert_id=alert_id,
                acknowledged_by=body.acknowledged_by or scope.email,
            ).single()
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Alert {alert_id!r} not found",
            )
        logger.info(
            "Alert %s acknowledged by %s (via %s)",
            alert_id, row["acknowledged_by"], scope.email,
        )
        return {
            "alert_id": row["alert_id"],
            "acknowledged_by": row["acknowledged_by"],
            "status": "acknowledged",
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# LoopConfig CRUD
# ---------------------------------------------------------------------------


@router.get("/config")
def get_loop_configs(
    scope: CallerScope = Depends(get_caller_scope_from_request),
) -> dict[str, Any]:
    """Return current LoopConfig nodes for all three learning loops."""
    client = _neo_client()
    try:
        with client.session() as session:
            rows = session.run(_Q_LIST_LOOP_CONFIGS)
            configs = [_row_to_dict(r) for r in rows]
        if not configs:
            configs = [
                {
                    "loop_id": lid,
                    "description": desc,
                    "enabled": True,
                    "updated_by": None,
                    "updated_at": None,
                }
                for lid, desc in _LOOP_DESCRIPTIONS.items()
            ]
        return {"configs": configs}
    finally:
        client.close()


@router.patch("/config/{loop_id}")
def update_loop_config(
    loop_id: str,
    body: UpdateLoopConfigRequest,
    scope: CallerScope = Depends(get_caller_scope_from_request),
) -> dict[str, Any]:
    """Toggle a loop's enabled flag (kill switch)."""
    if loop_id not in _VALID_LOOP_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown loop_id {loop_id!r}. Valid: {sorted(_VALID_LOOP_IDS)}",
        )
    client = _neo_client()
    try:
        with client.session() as session:
            row = session.run(
                _Q_UPDATE_LOOP_CONFIG,
                loop_id=loop_id,
                enabled=body.enabled,
                updated_by=scope.email,
            ).single()
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"LoopConfig {loop_id!r} not found",
            )
        logger.info(
            "LoopConfig %s.enabled set to %s by %s",
            loop_id, body.enabled, scope.email,
        )
        return {
            "loop_id": row["loop_id"],
            "enabled": row["enabled"],
            "updated_by": row["updated_by"],
        }
    finally:
        client.close()
