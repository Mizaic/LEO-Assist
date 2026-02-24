"""Dataset export endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db.neo4j_client import CodingGraphClient
from app.models.contracts import (
    ExportDatasetRequest,
    ExportDatasetResponse,
    ExportMedSpaCyRequest,
    ExportMedSpaCyResponse,
)
from app.services.export_service import ExportService


router = APIRouter(prefix="/exports", tags=["exports"])


def get_export_service() -> ExportService:
    client = CodingGraphClient()
    client.initialize_schema()
    return ExportService(client)


@router.post("/dataset", response_model=ExportDatasetResponse)
def export_dataset(request: ExportDatasetRequest, service: ExportService = Depends(get_export_service)):
    payload = service.create_export(
        export_name=request.export_name,
        train_ratio=request.train_ratio,
        seed=request.random_seed,
    )
    return ExportDatasetResponse(**payload)


@router.post("/medspacy-training", response_model=ExportMedSpaCyResponse)
def export_medspacy_training(
    request: ExportMedSpaCyRequest,
    service: ExportService = Depends(get_export_service),
):
    """Export approved gold to MedSpaCy training format (entities + KB)."""
    payload = service.export_medspacy_training(
        export_name=request.export_name,
        patient_ids=request.patient_ids,
    )
    return ExportMedSpaCyResponse(**payload)
