"""Run the referral pipeline on selected document chunks from Care.

Atlas trace:
  DO: DO-5D3EA371
  DI: DI-357A7468
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.neo4j_client import PatientGraphClient
from app.deps import require_admin_or_service
from libs.auth.org_scope import CallerScope, require_patient_in_scope
from libs.patient_document_runs.service import (
    DocumentRunError,
    refresh_document_run,
    start_document_run,
)

router = APIRouter(prefix="/patients", tags=["patient-document-runs"])


class StartDocumentRunBody(BaseModel):
    document_reference_id: str = Field(..., min_length=1)
    chunk_ids: list[str] = Field(..., min_length=1)
    plan_id: str = Field(default="pd-referral-assessment")


class DocumentRunResponse(BaseModel):
    run_id: str
    status: str
    assessment_id: str | None = None
    error_message: str | None = None
    stage_progress: list[dict[str, Any]] = Field(default_factory=list)


def _to_response(result: Any) -> DocumentRunResponse:
    return DocumentRunResponse(
        run_id=result.run_id,
        status=result.status,
        assessment_id=result.assessment_id or None,
        error_message=result.error_message or None,
        stage_progress=list(result.stage_progress or []),
    )


def _tenant_fallback(scope: CallerScope) -> str | None:
    """Best-effort tenant when graph nodes lack tenantId (legacy imports)."""
    if scope.primary_org_id:
        return str(scope.primary_org_id).strip() or None
    if scope.org_ids:
        first = str(scope.org_ids[0]).strip()
        return first or None
    return None


@router.post("/{patient_id}/document-runs", response_model=DocumentRunResponse)
def create_document_run(
    patient_id: str,
    body: StartDocumentRunBody,
    scope: CallerScope = Depends(require_admin_or_service),
) -> DocumentRunResponse:
    """Enqueue referral-received for selected chunks on a real patient document."""
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        result = start_document_run(
            client,
            patient_id=patient_id,
            document_reference_id=body.document_reference_id,
            chunk_ids=list(body.chunk_ids),
            plan_id=body.plan_id,
            requested_by=scope.email,
            tenant_fallback=_tenant_fallback(scope),
        )
        return _to_response(result)
    except DocumentRunError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        client.close()


@router.get(
    "/{patient_id}/document-runs/{run_id}",
    response_model=DocumentRunResponse,
)
def get_document_run(
    patient_id: str,
    run_id: str,
    scope: CallerScope = Depends(require_admin_or_service),
) -> DocumentRunResponse:
    """Poll pipeline status and assessment id for a document re-run."""
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        return _to_response(refresh_document_run(client, run_id=run_id))
    finally:
        client.close()
