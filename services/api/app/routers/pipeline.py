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


def _clean_patients(patient_ids: list[str]) -> dict:
    """Remove all pipeline artefacts for the given patients and return totals."""
    from libs.cypher.cleanup_queries import (
        RESET_PATIENT_REVIEW_QUEUE,
        RESET_PATIENT_DOCUMENTS,
        RESET_PATIENT_DIRECT_SEMANTIC,
        RESET_PATIENT_ALERTS,
        RESET_PATIENT_EPISODES,
        RESET_PATIENT_LEGACY_ALERTS,
        RESET_PATIENT_LEGACY_EPISODES,
    )

    pg = PatientGraphClient()
    totals: dict[str, int] = {}
    try:
        with pg.session() as session:
            for pid in patient_ids:
                for query_name, query in [
                    ("review_queue", RESET_PATIENT_REVIEW_QUEUE),
                    ("documents", RESET_PATIENT_DOCUMENTS),
                    ("direct_semantic", RESET_PATIENT_DIRECT_SEMANTIC),
                    ("alerts", RESET_PATIENT_ALERTS),
                    ("episodes", RESET_PATIENT_EPISODES),
                    ("legacy_alerts", RESET_PATIENT_LEGACY_ALERTS),
                    ("legacy_episodes", RESET_PATIENT_LEGACY_EPISODES),
                ]:
                    r = session.run(query, patient_id=pid).single()
                    count = 0
                    if r:
                        count = r.get("deleted", r.get("links_deleted", r.get("direct_deleted", 0)))
                    totals[query_name] = totals.get(query_name, 0) + count
    finally:
        pg.close()

    return totals


@router.post("/clean-patients")
def clean_patients_endpoint(payload: PipelineRunRequest):
    """Clean all pipeline artefacts for the specified patients.

    Removes EncounterCandidates, ReviewTasks, Approvals, Changes,
    DOCUMENTS links, SafetyNetAlerts, EpisodeOfCare nodes,
    and legacy CSSAlert/CancerEpisode nodes.
    """
    patient_ids = payload.patient_ids
    if not patient_ids and payload.cohort_id:
        patient_ids = _resolve_cohort_patients(payload.cohort_id)
    if not patient_ids and payload.org_id:
        patient_ids = _resolve_org_patients(payload.org_id)
    if not patient_ids:
        from fastapi import HTTPException
        raise HTTPException(400, "Provide patient_ids, cohort_id, or org_id")

    totals = _clean_patients(patient_ids)
    return {
        "patients_cleaned": len(patient_ids),
        "totals": totals,
    }


# ── Worker-based consensus pipeline ──────────────────────────

@router.post("/enqueue-consensus")
async def enqueue_consensus(payload: PipelineRunRequest, clean: bool = Query(default=True)):
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

    clean_totals = None
    if clean:
        clean_totals = _clean_patients(patient_ids)

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

    result = {
        "run_id": run_id,
        "patients_enqueued": len(patient_ids),
        "queue": CODING_QUEUE,
    }
    if clean_totals is not None:
        result["clean_totals"] = clean_totals
    return result
