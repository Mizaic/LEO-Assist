"""Terminology search and writeback endpoints against coding graph."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.db.neo4j_client import CodingGraphClient, PatientGraphClient
from app.models.neo4j_schema import TERMINOLOGY_SEARCH
from app.services.terminology_writeback_service import writeback_approved_terms


router = APIRouter(prefix="/terminology", tags=["terminology"])


@router.get("/search")
def search_terms(q: str = Query(min_length=1), limit: int = Query(default=15, ge=1, le=50)):
    client = CodingGraphClient()
    try:
        return client.run(TERMINOLOGY_SEARCH, q=q, limit=limit)
    finally:
        client.close()


class WritebackRequest(BaseModel):
    patient_id: str | None = None


class WritebackResponse(BaseModel):
    candidates_scanned: int
    terms_scanned: int
    surface_forms_written: int
    skipped_no_concept: int


@router.post("/writeback", response_model=WritebackResponse)
def trigger_writeback(body: WritebackRequest | None = None):
    """Write approved surface-form -> SNOMED mappings from patient graph into coding graph SurfaceForm nodes."""
    patient_client = PatientGraphClient()
    coding_client = CodingGraphClient()
    try:
        with patient_client.session() as patient_session, coding_client.session() as coding_session:
            result = writeback_approved_terms(
                patient_session=patient_session,
                coding_session=coding_session,
                patient_id=body.patient_id if body else None,
            )
        return WritebackResponse(**result)
    finally:
        patient_client.close()
        coding_client.close()
