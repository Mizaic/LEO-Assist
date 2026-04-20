"""Audit timeline endpoints.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db.neo4j_client import PatientGraphClient
from app.models.contracts import AuditTimelineResponse
from app.services.review_service import ReviewService
from libs.auth.org_scope import CallerScope, get_caller_scope

router = APIRouter(prefix="/audit", tags=["audit"])


def get_review_service() -> ReviewService:
    client = PatientGraphClient()
    client.initialize_schema()
    return ReviewService(client)


@router.get("/candidate/{candidate_id}", response_model=AuditTimelineResponse)
def get_timeline(
    candidate_id: str,
    scope: CallerScope = Depends(get_caller_scope),
    service: ReviewService = Depends(get_review_service),
):
    payload = service.audit_timeline(candidate_id)
    return AuditTimelineResponse(**payload)
