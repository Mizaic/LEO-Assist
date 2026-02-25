"""Audit timeline endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db.neo4j_client import PatientGraphClient
from app.models.contracts import AuditTimelineResponse
from app.services.review_service import ReviewService


router = APIRouter(prefix="/audit", tags=["audit"])


def get_review_service() -> ReviewService:
    client = PatientGraphClient()
    client.initialize_schema()
    return ReviewService(client)


@router.get("/candidate/{candidate_id}", response_model=AuditTimelineResponse)
def get_timeline(candidate_id: str, service: ReviewService = Depends(get_review_service)):
    payload = service.audit_timeline(candidate_id)
    return AuditTimelineResponse(**payload)
