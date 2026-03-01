"""Operations HITL router.

Centralised review queues for:
  - low_confidence_coding: coded candidates below confidence threshold
  - model_disagreement: cross-model disagreements from extractor pipeline
  - exclusion_conflict: conflicting exclusion detector outcomes
  - peer_review: mandatory 10% sampling of approved outputs

Routes
------
GET  /operations/tasks                 — list HITL tasks (filterable by type/status)
GET  /operations/tasks/{task_id}       — get single task detail
POST /operations/tasks/{task_id}/resolve — resolve a task with provenance
GET  /operations/metrics               — aggregate per-stage review metrics
GET  /operations/policy                — retrieve per-stage policy config
"""

from __future__ import annotations

import logging
import os
import random
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, ORG_PATIENT_FILTER, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient
from libs.cypher.exclusion_queries import (
    LIST_HITL_TASKS_BY_TYPE,
    RESOLVE_HITL_TASK,
)
from libs.ner.training_label_writer import upsert_training_label

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/operations", tags=["operations"])

# ------------------------------------------------------------------
# Per-stage policy (overridable via env)
# ------------------------------------------------------------------

_POLICY: dict[str, Any] = {
    "low_confidence_coding": {
        "confidence_threshold": float(
            os.getenv("HITL_LOW_CONFIDENCE_THRESHOLD", "0.5")
        ),
        "auto_route": True,
    },
    "model_disagreement": {
        "route_all": True,
    },
    "exclusion_conflict": {
        "route_all": True,
    },
    "peer_review": {
        "sampling_rate": float(os.getenv("HITL_PEER_REVIEW_RATE", "0.10")),
        "auto_route": True,
    },
}

# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------


class ResolveTaskRequest(BaseModel):
    status: str          # "resolved" | "dismissed" | "escalated"
    resolution: str      # free-text decision/notes
    resolved_by: str = "unknown"


# ------------------------------------------------------------------
# GET /operations/tasks
# ------------------------------------------------------------------


@router.get("/tasks")
async def list_hitl_tasks(
    scope: CallerScope = Depends(get_caller_scope),
    task_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default="pending"),
    limit: int = Query(default=100, le=500),
) -> dict[str, Any]:
    """Return HITL tasks, optionally filtered by type and status.

    Scoped users only see tasks whose patient belongs to their org hierarchy.
    """
    client = PatientGraphClient()
    try:
        if scope.is_admin:
            with client.session() as session:
                rows = session.run(
                    LIST_HITL_TASKS_BY_TYPE,
                    task_type=task_type,
                    status=status,
                    limit=limit,
                )
                tasks = [dict(r) for r in rows]
        else:
            tasks = client.run(
                "MATCH (t:HITLTask) "
                "WHERE ($task_type IS NULL OR t.task_type = $task_type) "
                "  AND ($status IS NULL OR t.status = $status) "
                "  AND EXISTS { "
                "    MATCH (p:Patient) WHERE toString(p.id) = t.patient_id "
                "    MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(_gp) "
                "    WHERE _gp.id IN $scope_org_ids "
                "  } "
                "RETURN t ORDER BY t.created_at DESC LIMIT $limit",
                task_type=task_type,
                status=status,
                limit=limit,
                scope_org_ids=scope.org_ids,
            )
        return {
            "tasks": tasks,
            "total_returned": len(tasks),
            "filters": {"task_type": task_type, "status": status},
        }
    finally:
        client.close()


# ------------------------------------------------------------------
# GET /operations/tasks/{task_id}
# ------------------------------------------------------------------

_GET_TASK_DETAIL = """
MATCH (t:HITLTask {task_id: $task_id})
OPTIONAL MATCH (ep:EpisodeOfCare {episode_id: t.episode_id})
OPTIONAL MATCH (ep)-[:HAS_EXCLUSION_AUDIT]->(a:ExclusionAudit)
RETURN t,
       ep.episode_id      AS episode_id,
       ep.status          AS episode_status,
       collect(a)         AS exclusion_audits
"""


@router.get("/tasks/{task_id}")
async def get_task_detail(
    task_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return full HITL task detail including linked episode and audit records."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            result = session.run(_GET_TASK_DETAIL, task_id=task_id)
            row = result.single()
            if not row:
                raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
            if not scope.is_admin:
                task_data = dict(row["t"])
                pid = task_data.get("patient_id")
                if pid:
                    from libs.auth.org_scope import require_patient_in_scope
                    require_patient_in_scope(client, scope, pid)
            return {
                "task": dict(row["t"]),
                "episode_id": row["episode_id"],
                "episode_status": row["episode_status"],
                "exclusion_audits": [dict(a) for a in (row["exclusion_audits"] or [])],
            }
    finally:
        client.close()


# ------------------------------------------------------------------
# POST /operations/tasks/{task_id}/resolve
# ------------------------------------------------------------------


_FETCH_TASK_FOR_LABEL = """
MATCH (t:HITLTask {task_id: $task_id})
OPTIONAL MATCH (c:EncounterCandidate {candidate_id: t.candidate_id})
RETURN
    t.task_id        AS task_id,
    t.encounter_id   AS encounter_id,
    t.patient_id     AS patient_id,
    t.task_type      AS task_type,
    c.sentences_json AS sentences_json
"""


@router.post("/tasks/{task_id}/resolve")
async def resolve_task(
    task_id: str,
    payload: ResolveTaskRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Resolve a HITL task with auditable provenance.

    When a task is resolved (not dismissed or escalated), the linked candidate
    data is written to the TrainingLabel store so the approval is captured as
    a learning signal for the NER model.
    """
    valid_statuses = {"resolved", "dismissed", "escalated"}
    if payload.status not in valid_statuses:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(valid_statuses)}",
        )
    client = PatientGraphClient()
    try:
        if not scope.is_admin:
            task_check = client.run(
                "MATCH (t:HITLTask {task_id: $task_id}) RETURN t.patient_id AS patient_id",
                task_id=task_id,
            )
            if task_check:
                pid = task_check[0].get("patient_id")
                if pid:
                    from libs.auth.org_scope import require_patient_in_scope
                    require_patient_in_scope(client, scope, pid)

        with client.session() as session:
            task_row = session.run(_FETCH_TASK_FOR_LABEL, task_id=task_id).single()

            result = session.run(
                RESOLVE_HITL_TASK,
                task_id=task_id,
                status=payload.status,
                resolved_by=payload.resolved_by,
                resolution=payload.resolution,
            )
            row = result.single()
            if not row:
                raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")

        logger.info(
            "HITL task %s resolved: status=%s by=%s",
            task_id, payload.status, payload.resolved_by,
        )

        # Write training label for approved resolutions only.
        if payload.status == "resolved" and task_row and task_row.get("sentences_json"):
            try:
                import json as _json
                sentences = _json.loads(task_row["sentences_json"] or "[]")
                for sent in sentences:
                    entities = sent.get("entities", [])
                    if not entities:
                        continue
                    upsert_training_label(
                        encounter_id=task_row["encounter_id"] or "",
                        patient_id=task_row["patient_id"] or "",
                        text=sent.get("text", ""),
                        entities=entities,
                        source="hitl_approval",
                        source_ref=task_id,
                        client=client,
                    )
            except Exception:
                logger.warning(
                    "HITL training label write failed for task %s — non-fatal",
                    task_id, exc_info=True,
                )

        return {"task_id": row["task_id"], "status": row["status"]}
    finally:
        client.close()


# ------------------------------------------------------------------
# GET /operations/metrics
# ------------------------------------------------------------------

_METRICS_QUERY = """
MATCH (t:HITLTask)
RETURN t.task_type  AS task_type,
       t.status     AS status,
       count(*)     AS count
ORDER BY t.task_type, t.status
"""


@router.get("/metrics")
async def get_operations_metrics(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return aggregate per-stage review metrics.

    Scoped users see metrics only for tasks linked to patients in their org.
    """
    client = PatientGraphClient()
    try:
        if scope.is_admin:
            with client.session() as session:
                rows = session.run(_METRICS_QUERY)
                by_type: dict[str, dict[str, int]] = {}
                for row in rows:
                    tt = row["task_type"] or "unknown"
                    st = row["status"] or "unknown"
                    by_type.setdefault(tt, {})[st] = row["count"]
        else:
            raw = client.run(
                "MATCH (t:HITLTask) "
                "WHERE EXISTS { "
                "  MATCH (p:Patient) WHERE toString(p.id) = t.patient_id "
                "  MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(_gp) "
                "  WHERE _gp.id IN $scope_org_ids "
                "} "
                "RETURN t.task_type AS task_type, t.status AS status, count(*) AS count "
                "ORDER BY t.task_type, t.status",
                scope_org_ids=scope.org_ids,
            )
            by_type = {}
            for row in raw:
                tt = row["task_type"] or "unknown"
                st = row["status"] or "unknown"
                by_type.setdefault(tt, {})[st] = row["count"]
        return {"metrics_by_stage": by_type}
    finally:
        client.close()


# ------------------------------------------------------------------
# GET /operations/policy
# ------------------------------------------------------------------


@router.get("/policy")
async def get_operations_policy() -> dict[str, Any]:
    """Return current per-stage HITL policy configuration."""
    return {"policy": _POLICY}


# ------------------------------------------------------------------
# Helper: peer-review sampling
# ------------------------------------------------------------------


def should_peer_review() -> bool:
    """Return True if this item should be routed to peer-review.

    Uses the HITL_PEER_REVIEW_RATE env var (default 10%).
    """
    rate = _POLICY["peer_review"]["sampling_rate"]
    return random.random() < rate


def create_peer_review_task(
    session,
    episode_id: str,
    patient_id: str,
    candidate_id: str,
) -> str:
    """Create a peer-review HITLTask and return its task_id."""
    from libs.cypher.exclusion_queries import CREATE_EXCLUSION_HITL_TASK

    task_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"peer-review:{episode_id}:{candidate_id}",
    ))

    _CREATE_PEER_REVIEW = """
MERGE (t:HITLTask {task_id: $task_id})
ON CREATE SET
    t.task_type   = 'peer_review',
    t.episode_id  = $episode_id,
    t.patient_id  = $patient_id,
    t.candidate_id = $candidate_id,
    t.status      = 'pending',
    t.priority    = 30,
    t.reason      = '10% mandatory peer-review sample',
    t.created_at  = datetime(),
    t.updated_at  = datetime()
ON MATCH SET
    t.updated_at  = datetime()
"""
    session.run(
        _CREATE_PEER_REVIEW,
        task_id=task_id,
        episode_id=episode_id,
        patient_id=patient_id,
        candidate_id=candidate_id,
    )
    return task_id
