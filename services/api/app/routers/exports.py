"""Dataset export endpoints.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db.neo4j_client import PatientGraphClient
from app.models.contracts import (
    ExportDatasetRequest,
    ExportDatasetResponse,
    ExportMedSpaCyRequest,
    ExportMedSpaCyResponse,
)
from app.services.export_service import ExportService
from libs.auth.org_scope import CallerScope, get_caller_scope

router = APIRouter(prefix="/exports", tags=["exports"])


def get_export_service() -> ExportService:
    client = PatientGraphClient()
    client.initialize_schema()
    return ExportService(client)


@router.post("/dataset", response_model=ExportDatasetResponse)
def export_dataset(
    request: ExportDatasetRequest,
    scope: CallerScope = Depends(get_caller_scope),
    service: ExportService = Depends(get_export_service),
):
    payload = service.create_export(
        export_name=request.export_name,
        train_ratio=request.train_ratio,
        seed=request.random_seed,
    )
    return ExportDatasetResponse(**payload)


@router.post("/medspacy-training", response_model=ExportMedSpaCyResponse)
def export_medspacy_training(
    request: ExportMedSpaCyRequest,
    scope: CallerScope = Depends(get_caller_scope),
    service: ExportService = Depends(get_export_service),
):
    """Export approved gold to MedSpaCy training format (entities + KB)."""
    payload = service.export_medspacy_training(
        export_name=request.export_name,
        patient_ids=request.patient_ids,
    )
    return ExportMedSpaCyResponse(**payload)
