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


router = APIRouter(prefix="/review", tags=["review"])


def get_review_service() -> ReviewService:
    client = PatientGraphClient()
    client.initialize_schema()
    return ReviewService(client)


@router.get("/tasks", response_model=list[ReviewTaskSummary])
def list_tasks(
    status: ReviewStatus | None = Query(default=None),
    patient_id: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    service: ReviewService = Depends(get_review_service),
):
    return service.list_tasks(status=status, patient_id=patient_id, limit=limit)


@router.get("/tasks/{task_id}", response_model=ReviewTaskDetail)
def get_task(task_id: str, service: ReviewService = Depends(get_review_service)):
    payload = service.get_task(task_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Task not found")
    candidate = payload["candidate"]
    task_payload = {k: v for k, v in payload.items() if k != "candidate"}
    return ReviewTaskDetail(task=task_payload, candidate=candidate)


@router.post("/tasks/{task_id}/decision", response_model=ReviewDecisionResponse)
def decide_task(
    task_id: str,
    decision: ReviewDecisionRequest,
    service: ReviewService = Depends(get_review_service),
):
    result = service.decide(task_id=task_id, decision=decision)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return ReviewDecisionResponse(**result)
