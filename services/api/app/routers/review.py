"""Review queue endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.neo4j_client import PatientGraphClient
from app.models.contracts import (
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewStatus,
    ReviewTaskDetail,
    ReviewTaskSummary,
)
from app.services.review_service import ReviewService
from libs.auth.org_scope import CallerScope, get_caller_scope, require_patient_in_scope

router = APIRouter(prefix="/review", tags=["review"])


def get_review_service() -> ReviewService:
    client = PatientGraphClient()
    client.initialize_schema()
    return ReviewService(client)


@router.get("/tasks", response_model=list[ReviewTaskSummary])
def list_tasks(
    scope: CallerScope = Depends(get_caller_scope),
    status: ReviewStatus | None = Query(default=None),
    patient_id: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    service: ReviewService = Depends(get_review_service),
):
    if patient_id and not scope.is_admin:
        require_patient_in_scope(service.client, scope, patient_id)
    tasks = service.list_tasks(status=status, patient_id=patient_id, limit=limit)
    if not scope.is_admin and not patient_id:
        tasks = [t for t in tasks if _task_patient_in_scope(service.client, scope, t)]
    return tasks


@router.get("/tasks/{task_id}", response_model=ReviewTaskDetail)
def get_task(
    task_id: str,
    scope: CallerScope = Depends(get_caller_scope),
    service: ReviewService = Depends(get_review_service),
):
    payload = service.get_task(task_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Task not found")
    candidate = payload["candidate"]
    pid = candidate.get("patient_id") if candidate else None
    if pid and not scope.is_admin:
        require_patient_in_scope(service.client, scope, pid)
    task_payload = {k: v for k, v in payload.items() if k != "candidate"}
    return ReviewTaskDetail(task=task_payload, candidate=candidate)


@router.post("/tasks/{task_id}/decision", response_model=ReviewDecisionResponse)
def decide_task(
    task_id: str,
    decision: ReviewDecisionRequest,
    scope: CallerScope = Depends(get_caller_scope),
    service: ReviewService = Depends(get_review_service),
):
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    candidate = task.get("candidate") or {}
    pid = candidate.get("patient_id")
    if pid and not scope.is_admin:
        require_patient_in_scope(service.client, scope, pid)
    result = service.decide(task_id=task_id, decision=decision)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return ReviewDecisionResponse(**result)


def _task_patient_in_scope(client, scope: CallerScope, task) -> bool:
    """Check if a review task's patient is in the caller's org scope."""
    pid = getattr(task, "patient_id", None) or (
        task.get("patient_id") if isinstance(task, dict) else None
    )
    if not pid:
        return True
    rows = client.run(
        "MATCH (p:Patient) WHERE toString(p.id) = $pid "
        "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
        "RETURN gp.id AS gp_id",
        pid=str(pid),
    )
    if not rows:
        return False
    return rows[0].get("gp_id") in scope.org_ids
