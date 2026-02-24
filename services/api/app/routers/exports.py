"""Dataset export endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db.neo4j_client import CodingGraphClient
from app.models.contracts import ExportDatasetRequest, ExportDatasetResponse
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
