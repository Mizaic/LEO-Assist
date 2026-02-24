"""Pipeline endpoints for candidate generation."""

from __future__ import annotations

import json
import queue
import threading
import time

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.db.neo4j_client import CodingGraphClient, PatientGraphClient
from app.models.contracts import PipelineRunRequest, PipelineRunResponse
from app.services.v3.pipeline_service import V3PipelineService


router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def get_creator() -> V3PipelineService:
    patient_client = PatientGraphClient()
    coding_client = CodingGraphClient()
    coding_client.initialize_schema()
    return V3PipelineService(
        patient_client=patient_client, coding_client=coding_client
    )


def _format_sse(event_type: str, payload: dict[str, object]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


@router.post("/run", response_model=PipelineRunResponse)
def run_pipeline(
    payload: PipelineRunRequest,
    service: V3PipelineService = Depends(get_creator),
):
    run_id, stats = service.run(
        patient_ids=payload.patient_ids,
        max_encounters_per_patient=payload.max_encounters_per_patient,
        dry_run=payload.dry_run,
    )
    return PipelineRunResponse(
        run_id=run_id,
        processed_encounters=stats.processed_encounters,
        queued_for_review=stats.queued_for_review,
        rejected_hard_fail=stats.rejected_hard_fail,
        warnings_only=stats.warnings_only,
    )


@router.get("/stream")
def stream_pipeline(
    patient_ids: str = Query(min_length=1),
    max_encounters_per_patient: int | None = Query(default=None, gt=0),
    dry_run: bool = Query(default=False),
    workers: int = Query(default=4, ge=1, le=8),
):
    ids = [pid.strip() for pid in patient_ids.split(",") if pid.strip()]
    if not ids:
        ids = [patient_ids.strip()]

    service = get_creator()
    events: queue.Queue[dict[str, object] | None] = queue.Queue()

    def emit(event: dict[str, object]) -> None:
        events.put(event)

    def worker() -> None:
        try:
            service.run(
                patient_ids=ids,
                max_encounters_per_patient=max_encounters_per_patient,
                dry_run=dry_run,
                workers=workers,
                progress_hook=emit,
            )
        except Exception as exc:  # pragma: no cover
            events.put({"type": "pipeline_error", "message": str(exc)})
        finally:
            try:
                service.patient_graph.close()
                service.coding_graph.close()
            finally:
                events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def event_generator():
        while True:
            try:
                event = events.get(timeout=2.0)
            except queue.Empty:
                yield _format_sse(
                    "heartbeat", {"type": "heartbeat", "ts": time.time()}
                )
                continue
            if event is None:
                break
            event_type = str(event.get("type", "message"))
            yield _format_sse(event_type, event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
