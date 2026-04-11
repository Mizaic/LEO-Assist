"""Terminology writeback endpoint.

Writes approved surface-form -> SNOMED mappings from Patient Graph
into Knowledge Graph SurfaceForm nodes (the learning loop).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from libs.auth.service_auth import verify_service_token
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from services.terminology_api.app.services.writeback_service import (
    writeback_approved_terms,
)

router = APIRouter()


class WritebackRequest(BaseModel):
    patient_id: Optional[str] = None


class WritebackResponse(BaseModel):
    candidates_scanned: int
    terms_scanned: int
    surface_forms_written: int
    skipped_no_concept: int


@router.post("/writeback", response_model=WritebackResponse)
def trigger_writeback(
    body: WritebackRequest | None = None, _: None = Depends(verify_service_token)
):
    """Write approved surface-form -> SNOMED mappings from Patient Graph into Knowledge Graph."""
    patient_client = PatientGraphClient()
    knowledge_client = KnowledgeGraphClient()
    try:
        with (
            patient_client.session() as patient_session,
            knowledge_client.session() as knowledge_session,
        ):
            result = writeback_approved_terms(
                patient_session=patient_session,
                knowledge_session=knowledge_session,
                patient_id=body.patient_id if body else None,
            )
        return WritebackResponse(**result)
    finally:
        patient_client.close()
        knowledge_client.close()
