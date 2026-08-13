"""Patient document CRUD and milestone SBAR routes for Care journeys.

Atlas trace:
  UN: UN-236D97F4
  DI: DI-DD1989E6, DI-9DD9E548
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.neo4j_client import PatientGraphClient
from app.deps import require_admin_or_org_admin
from libs.auth.org_scope import CallerScope, require_patient_in_scope
from libs.patient_documents.milestone_sbar import (
    MilestoneSbarError,
    get_milestone_sbar_run,
    start_milestone_sbar,
)
from libs.patient_documents.service import (
    PatientDocumentError,
    create_patient_document,
    delete_patient_document,
    update_patient_document,
)

router = APIRouter(prefix="/patients", tags=["patient-documents"])


class CreatePatientDocumentBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    markdown_body: str = Field(..., min_length=1)
    category: str = Field(default="referral")
    document_date: str = ""
    episode_id: str = ""
    milestone_type: str = ""
    referral_id: str = ""
    run_pipeline: bool = False


class UpdatePatientDocumentBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    markdown_body: str | None = None
    category: str | None = None
    document_date: str | None = None
    episode_id: str | None = None
    milestone_type: str | None = None


class PatientDocumentResponse(BaseModel):
    document_id: str
    referral_id: str
    encounter_id: str = ""
    chunk_ids: list[str] = Field(default_factory=list)
    run_id: str | None = None


class MilestoneSbarBody(BaseModel):
    milestone_type: str = Field(..., min_length=1)
    include_rollup: bool = True


class MilestoneSbarResponse(BaseModel):
    run_id: str
    status: str
    episode_assessment_id: str
    rollup_assessment_id: str | None = None
    error_message: str | None = None


def _tenant_fallback(scope: CallerScope) -> str | None:
    if scope.primary_org_id:
        return str(scope.primary_org_id).strip() or None
    if scope.org_ids:
        first = str(scope.org_ids[0]).strip()
        return first or None
    return None


def _to_response(result: Any) -> PatientDocumentResponse:
    return PatientDocumentResponse(
        document_id=result.document_id,
        referral_id=result.referral_id,
        encounter_id=result.encounter_id or "",
        chunk_ids=list(result.chunk_ids or []),
        run_id=result.run_id,
    )


@router.post("/{patient_id}/documents", response_model=PatientDocumentResponse)
def create_document(
    patient_id: str,
    body: CreatePatientDocumentBody,
    scope: CallerScope = Depends(require_admin_or_org_admin),
) -> PatientDocumentResponse:
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        result = create_patient_document(
            client,
            patient_id=patient_id,
            title=body.title,
            markdown_body=body.markdown_body,
            category=body.category,
            document_date=body.document_date,
            episode_id=body.episode_id,
            milestone_type=body.milestone_type,
            referral_id=body.referral_id,
            run_pipeline=body.run_pipeline,
            requested_by=scope.email or "",
            tenant_fallback=_tenant_fallback(scope),
        )
        return _to_response(result)
    except PatientDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        client.close()


@router.patch(
    "/{patient_id}/documents/{document_id}",
    response_model=PatientDocumentResponse,
)
def patch_document(
    patient_id: str,
    document_id: str,
    body: UpdatePatientDocumentBody,
    scope: CallerScope = Depends(require_admin_or_org_admin),
) -> PatientDocumentResponse:
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        result = update_patient_document(
            client,
            patient_id=patient_id,
            document_id=document_id,
            title=body.title,
            markdown_body=body.markdown_body,
            category=body.category,
            document_date=body.document_date,
            episode_id=body.episode_id,
            milestone_type=body.milestone_type,
            tenant_fallback=_tenant_fallback(scope),
        )
        return _to_response(result)
    except PatientDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        client.close()


@router.delete("/{patient_id}/documents/{document_id}")
def remove_document(
    patient_id: str,
    document_id: str,
    scope: CallerScope = Depends(require_admin_or_org_admin),
) -> dict[str, str]:
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        deleted_id = delete_patient_document(
            client,
            patient_id=patient_id,
            document_id=document_id,
        )
        return {"document_id": deleted_id, "status": "deleted"}
    except PatientDocumentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()


@router.post(
    "/{patient_id}/episodes/{episode_id}/milestone-sbar",
    response_model=MilestoneSbarResponse,
)
def create_milestone_sbar(
    patient_id: str,
    episode_id: str,
    body: MilestoneSbarBody,
    scope: CallerScope = Depends(require_admin_or_org_admin),
) -> MilestoneSbarResponse:
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        started = start_milestone_sbar(
            client,
            patient_id=patient_id,
            episode_id=episode_id,
            milestone_type=body.milestone_type,
            include_rollup=body.include_rollup,
            requested_by=scope.email or "",
            tenant_id=_tenant_fallback(scope),
        )
        return MilestoneSbarResponse(
            run_id=started.run_id,
            status=started.status,
            episode_assessment_id=started.episode_assessment_id,
            rollup_assessment_id=started.rollup_assessment_id,
        )
    except MilestoneSbarError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        client.close()


@router.get(
    "/{patient_id}/episodes/{episode_id}/milestone-sbar/{run_id}",
    response_model=MilestoneSbarResponse,
)
def get_milestone_sbar(
    patient_id: str,
    episode_id: str,
    run_id: str,
    scope: CallerScope = Depends(require_admin_or_org_admin),
) -> MilestoneSbarResponse:
    _ = patient_id, episode_id
    payload = get_milestone_sbar_run(run_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Milestone SBAR run not found.")
    return MilestoneSbarResponse(
        run_id=str(payload.get("run_id") or run_id),
        status=str(payload.get("status") or "unknown"),
        episode_assessment_id=str(payload.get("episode_assessment_id") or ""),
        rollup_assessment_id=payload.get("rollup_assessment_id"),
        error_message=str(payload.get("error_message") or "") or None,
    )
