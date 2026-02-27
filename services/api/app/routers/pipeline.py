"""Pipeline endpoints for candidate generation."""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.db.neo4j_client import CodingGraphClient, PatientGraphClient, run_with_retry
from app.models.contracts import LLMUsageResponse, PipelineRunRequest, PipelineRunResponse
from app.models.neo4j_schema import DELETE_ENCOUNTER_DOCUMENTS, RESET_ENCOUNTER_REVIEW_QUEUE
from app.services.v3.pipeline_service import V3PipelineService

CODING_QUEUE = os.getenv("CODING_QUEUE_NAME", "coding-jobs")

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def get_creator() -> V3PipelineService:
    patient_client = PatientGraphClient()
    patient_client.initialize_schema()
    coding_client = CodingGraphClient()
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
    patient_ids = payload.patient_ids
    if not patient_ids and payload.cohort_id:
        patient_ids = _resolve_cohort_patients(payload.cohort_id)
    if not patient_ids and payload.org_id:
        patient_ids = _resolve_org_patients(payload.org_id)
    if not patient_ids:
        from fastapi import HTTPException
        raise HTTPException(400, "Provide patient_ids, cohort_id, or org_id")

    run_id, stats = service.run(
        patient_ids=patient_ids,
        max_encounters_per_patient=payload.max_encounters_per_patient,
        dry_run=payload.dry_run,
    )
    snap = stats.snapshot()
    usage_dict = snap.get("llm_usage", {})
    return PipelineRunResponse(
        run_id=run_id,
        processed_encounters=stats.processed_encounters,
        queued_for_review=stats.queued_for_review,
        rejected_hard_fail=stats.rejected_hard_fail,
        warnings_only=stats.warnings_only,
        llm_usage=LLMUsageResponse(**usage_dict) if usage_dict else None,
    )


def _resolve_cohort_patients(cohort_id: str) -> list[str]:
    """Resolve a cohort ID to patient IDs via the Patient Graph."""
    import json as _json
    from libs.neo4j_client.client import PatientGraphClient
    pg = PatientGraphClient()
    try:
        rows = pg.run(
            "MATCH (c:Cohort {cohort_id: $cid}) RETURN c.filters AS filters",
            cid=cohort_id,
        )
        if not rows:
            return []
        filters_raw = rows[0].get("filters", "{}")
        filters = _json.loads(filters_raw) if isinstance(filters_raw, str) else filters_raw
        where_parts, params = [], {}
        if filters.get("org_id"):
            where_parts.append("EXISTS { MATCH (p)-[:REGISTERED_AT]->(o:Organization {id: $org_id}) }")
            params["org_id"] = filters["org_id"]
        if filters.get("episode_status"):
            where_parts.append("EXISTS { MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) WHERE ep.status IN $ep_statuses }")
            params["ep_statuses"] = filters["episode_status"]
        where_clause = " AND ".join(where_parts) if where_parts else "true"
        result = pg.run(
            f"MATCH (p:Patient) WHERE {where_clause} RETURN toString(p.id) AS pid LIMIT 10000",
            **params,
        )
        return [str(r["pid"]) for r in result]
    finally:
        pg.close()


def _resolve_org_patients(org_id: str) -> list[str]:
    from libs.neo4j_client.client import PatientGraphClient
    pg = PatientGraphClient()
    try:
        rows = pg.run(
            "MATCH (p:Patient)-[:REGISTERED_AT]->(o:Organization {id: $org}) "
            "RETURN toString(p.id) AS pid LIMIT 10000",
            org=org_id,
        )
        return [str(r["pid"]) for r in rows]
    finally:
        pg.close()


@router.get("/stream-unprocessed")
def stream_unprocessed(
    patient_ids: str = Query(min_length=1),
    dry_run: bool = Query(default=False),
    workers: int = Query(default=4, ge=1, le=8),
):
    """Run pipeline only for encounters that don't yet have a ReviewTask."""
    ids = [pid.strip() for pid in patient_ids.split(",") if pid.strip()]
    if not ids:
        ids = [patient_ids.strip()]

    service = get_creator()
    events: queue.Queue[dict[str, object] | None] = queue.Queue()

    def emit(event: dict[str, object]) -> None:
        events.put(event)

    def worker() -> None:
        try:
            service.run_unprocessed(
                patient_ids=ids,
                dry_run=dry_run,
                workers=workers,
                progress_hook=emit,
            )
        except Exception as exc:
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


@router.get("/stream-encounter")
def stream_encounter(
    patient_id: str = Query(min_length=1),
    encounter_id: str = Query(min_length=1),
    dry_run: bool = Query(default=False),
):
    """Reset a single encounter (DOCUMENTS + review queue) then re-run the pipeline on it."""
    service = get_creator()
    events: queue.Queue[dict[str, object] | None] = queue.Queue()

    def emit(event: dict[str, object]) -> None:
        events.put(event)

    def worker() -> None:
        try:
            run_with_retry(
                service.patient_graph,
                DELETE_ENCOUNTER_DOCUMENTS,
                patient_id=patient_id,
                encounter_id=encounter_id,
            )
            run_with_retry(
                service.patient_graph,
                RESET_ENCOUNTER_REVIEW_QUEUE,
                patient_id=patient_id,
                encounter_id=encounter_id,
            )
            emit({"type": "reset_completed", "patient_id": patient_id, "encounter_id": encounter_id})

            service.run_single_encounter(
                patient_id=patient_id,
                encounter_id=encounter_id,
                dry_run=dry_run,
                progress_hook=emit,
            )
        except Exception as exc:
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


# ── Worker-based consensus pipeline ──────────────────────────

@router.post("/enqueue-consensus")
async def enqueue_consensus(payload: PipelineRunRequest):
    """Publish coding jobs to the message bus for worker-based consensus processing.

    Each patient gets a separate message with mode=consensus and
    trigger_analysis=True so the coding worker fires the analysis
    worker upon completion.
    """
    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    patient_ids = payload.patient_ids
    if not patient_ids and payload.cohort_id:
        patient_ids = _resolve_cohort_patients(payload.cohort_id)
    if not patient_ids and payload.org_id:
        patient_ids = _resolve_org_patients(payload.org_id)
    if not patient_ids:
        from fastapi import HTTPException
        raise HTTPException(400, "Provide patient_ids, cohort_id, or org_id")

    run_id = str(uuid.uuid4())
    bus = create_message_bus()
    try:
        for pid in patient_ids:
            msg = Message(
                body={
                    "patient_id": pid,
                    "dry_run": payload.dry_run,
                    "mode": "consensus",
                    "trigger_analysis": True,
                },
                correlation_id=run_id,
            )
            await bus.send(CODING_QUEUE, msg)
    finally:
        await bus.close()

    return {
        "run_id": run_id,
        "patients_enqueued": len(patient_ids),
        "queue": CODING_QUEUE,
    }
