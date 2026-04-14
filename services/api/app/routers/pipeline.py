"""Pipeline endpoints for candidate generation."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db.neo4j_client import CodingGraphClient, PatientGraphClient, run_with_retry
from app.models.contracts import (
    LLMUsageResponse,
    PipelineRunRequest,
    PipelineRunResponse,
)
from app.models.neo4j_schema import (
    DELETE_ENCOUNTER_DOCUMENTS,
    RESET_ENCOUNTER_REVIEW_QUEUE,
)
from app.services.pipeline_service import PipelineService, _REMOVED_MSG
from libs.auth.org_scope import CallerScope, get_caller_scope, require_patient_in_scope

PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
_PROGRESS_IDLE_TIMEOUT_S = 300  # close relay after 5 min of silence

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

SUBGRAPH_PORTS: dict[str, dict[str, object]] = {
    "encounter_loader": {"reads": ["encounter_id"], "writes": ["encounter_text"]},
    "extraction": {
        "reads": ["encounter_text"],
        "writes": ["entities", "sentences", "errors"],
    },
    "post_processing": {
        "reads": ["entities", "encounter_text"],
        "writes": ["entities", "errors"],
    },
    "extraction_check": {
        "reads": ["entities", "encounter_text", "model_tier", "prompt_config"],
        "writes": ["entities", "llm_check_result", "llm_check_changes", "errors"],
    },
    "terminology": {"reads": ["entities"], "writes": ["entities", "errors"]},
    "coding_check": {
        "reads": ["entities", "encounter_text", "model_tier", "prompt_config"],
        "writes": ["entities", "llm_check_result", "llm_check_changes", "errors"],
    },
    "tier_classify": {"reads": ["entities"], "writes": ["entities", "tier_decisions"]},
    "verification": {
        "reads": ["entities", "encounter_text"],
        "writes": ["is_verified", "verification_result", "errors"],
    },
    "persist": {
        "reads": ["entities", "encounter_id", "patient_id", "output_target"],
        "writes": ["documents_written", "training_labels_written"],
    },
    "sbar": {
        "reads": ["entities", "encounter_text", "patient_id"],
        "writes": ["sbar_report"],
    },
    "compliance": {"reads": ["entities"], "writes": ["compliance_result"]},
    "anchor_detect": {"reads": ["entities"], "writes": ["anchors"]},
    "episode_build": {"reads": ["entities", "patient_id"], "writes": ["episodes"]},
    "safety_net": {
        "reads": ["entities", "patient_id"],
        "writes": ["safety_net_alerts"],
    },
    "quality_check": {"reads": ["entities"], "writes": ["quality_issues"]},
    "next_best_action": {
        "reads": ["entities", "patient_id"],
        "writes": ["recommendations"],
    },
    "surface_form_validation": {
        "reads": ["entities"],
        "writes": ["entities", "errors"],
    },
    "rest_connector": {"reads": ["*"], "writes": ["connector_response", "errors"]},
    "queue_publish": {"reads": ["*"], "writes": ["queued", "errors"]},
    "guidance_rule_extraction": {
        "reads": ["recommendation", "guideline_id"],
        "writes": ["coded_criteria", "errors"],
    },
}


class RunGoldTrainingRequest(BaseModel):
    plan_definition_id: str = "pd-gold-training-audit"
    mode: Literal["all_pending", "specific"] = "all_pending"
    candidate_ids: list[str] = []  # used when mode="specific"
    preview: bool = False


class RunPatientRequest(BaseModel):
    patient_id: str
    action: Literal["code_new", "recode_all", "run_analysis", "full_pipeline"]
    preview: bool = False


class RunCohortRequest(BaseModel):
    patient_ids: list[str]
    action: Literal["code_new", "recode_all", "full_pipeline", "run_analysis"]
    preview: bool = False


_BULK_RESET_CONFIRM_TEXT = "RESET AND REPROCESS ALL PATIENTS"


class RunAllPatientsRequest(BaseModel):
    org_id: str | None = None
    preview: bool = True
    acknowledge_expensive: bool = False
    acknowledge_destructive: bool = False
    acknowledge_background: bool = False
    confirmation_text: str = ""
    expected_patient_count: int | None = None


@router.get("/subgraphs")
def list_pipeline_subgraphs(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, object]:
    _ = scope  # reserved for future role-specific filtering
    items: list[dict[str, object]] = []
    for subgraph_id, port_meta in SUBGRAPH_PORTS.items():
        items.append(
            {
                "id": subgraph_id,
                "label": subgraph_id.replace("_", " ").title(),
                "description": "",
                "reads": port_meta.get("reads", []),
                "writes": port_meta.get("writes", []),
                "requiredFields": {},
            }
        )
    return {"subgraphs": items}


async def _publish_coding_jobs(
    encounter_jobs: list[dict[str, str]],
    *,
    run_id: str,
    mode: str,
    preview: bool,
    trigger_analysis: bool,
) -> int:
    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    bus = create_message_bus()
    sent_count = 0
    try:
        for job in encounter_jobs:
            pid = str(job.get("patient_id") or "")
            encounter_id = str(job.get("encounter_id") or "")
            await bus.send(
                PIPELINE_QUEUE,
                Message(
                    body={
                        "event_type": "encounter-created",
                        "patient_id": pid,
                        "encounter_id": encounter_id,
                        "plan_definition_id": "pd-gp-encounter-coding",
                        "mode": "extract_encounter",
                        "dry_run": preview,
                        "trigger_analysis": trigger_analysis,
                        "context": {
                            "dry_run": preview,
                            "mode": "extract_encounter",
                            "trigger_analysis": trigger_analysis,
                            "encounter_id": encounter_id,
                        },
                    },
                    correlation_id=run_id,
                    subject="encounter-created",
                ),
            )
            sent_count += 1
        return sent_count
    except Exception as exc:
        raise RuntimeError(
            f"coding_job_publish_failed sent={sent_count} total={len(encounter_jobs)} err={exc}"
        ) from exc
    finally:
        await bus.close()


async def _publish_analysis_jobs(patient_ids: list[str], *, run_id: str) -> int:
    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    bus = create_message_bus()
    sent_count = 0
    try:
        for pid in patient_ids:
            await bus.send(
                PIPELINE_QUEUE,
                Message(
                    body={
                        "event_type": "manual_run_analysis",
                        "patient_id": pid,
                        "plan_definition_id": "pd-gp-encounter-coding",
                        "context": {},
                    },
                    correlation_id=run_id,
                    subject="manual_run_analysis",
                ),
            )
            sent_count += 1
        return sent_count
    except Exception as exc:
        raise RuntimeError(
            f"analysis_job_publish_failed sent={sent_count} total={len(patient_ids)} err={exc}"
        ) from exc
    finally:
        await bus.close()


def _require_patients_in_scope(scope: CallerScope, patient_ids: list[str]) -> None:
    """Validate that all patients in the batch are visible to the caller."""
    if scope.is_admin:
        return
    from libs.neo4j_client.client import PatientGraphClient as LibPGClient

    client = LibPGClient()
    try:
        rows = client.run(
            "UNWIND $pids AS pid "
            "MATCH (p:Patient) WHERE toString(p.id) = pid "
            "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
            "RETURN pid, gp.id AS gp_id",
            pids=patient_ids,
        )
        for row in rows:
            if row.get("gp_id") not in scope.org_ids:
                raise HTTPException(
                    status_code=403,
                    detail=f"Not authorized for patient {row['pid']}",
                )
    finally:
        client.close()


def _expand_patients_to_clinical_encounters(
    patient_ids: list[str],
) -> list[dict[str, str]]:
    """Resolve patient IDs into clinical encounter jobs."""
    from libs.neo4j_client.client import PatientGraphClient as LibPGClient

    client = LibPGClient()
    try:
        rows = client.run(
            "UNWIND $pids AS pid "
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = pid "
            "  AND coalesce(e.classification_content_type, 'clinical') = 'clinical' "
            "  AND trim(coalesce(e.text, '')) <> '' "
            "RETURN pid AS patient_id, toString(e.id) AS encounter_id",
            pids=patient_ids,
        )
        jobs: list[dict[str, str]] = []
        for row in rows:
            jobs.append(
                {
                    "patient_id": str(row.get("patient_id") or ""),
                    "encounter_id": str(row.get("encounter_id") or ""),
                }
            )
        return jobs
    finally:
        client.close()


def _resolve_scope_patients(scope: CallerScope, org_id: str | None) -> list[str]:
    """Resolve patient IDs for bulk runs, restricted to caller visibility."""
    if org_id and org_id.strip():
        patient_ids = _resolve_org_patients(org_id.strip())
        _require_patients_in_scope(scope, patient_ids)
        return patient_ids

    if scope.is_admin:
        raise HTTPException(
            status_code=400,
            detail="org_id is required for admin bulk runs",
        )

    if not scope.org_ids:
        return []

    from libs.neo4j_client.client import PatientGraphClient as LibPGClient

    client = LibPGClient()
    try:
        rows = client.run(
            "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
            "WHERE gp.id IN $org_ids "
            "RETURN DISTINCT toString(p.id) AS pid "
            "LIMIT 50000",
            org_ids=scope.org_ids,
        )
        return [str(r.get("pid") or "") for r in rows if r.get("pid")]
    finally:
        client.close()


def _validate_bulk_run_confirmation(
    payload: RunAllPatientsRequest,
    *,
    patient_count: int,
) -> None:
    """Require explicit acknowledgements for destructive bulk operations."""
    if payload.confirmation_text.strip() != _BULK_RESET_CONFIRM_TEXT:
        raise HTTPException(
            status_code=400,
            detail="Type the exact confirmation text before running.",
        )
    if not payload.acknowledge_expensive:
        raise HTTPException(
            status_code=400,
            detail="You must confirm this run can be expensive.",
        )
    if not payload.acknowledge_destructive:
        raise HTTPException(
            status_code=400,
            detail="You must confirm this run deletes existing patient pipeline artefacts.",
        )
    if not payload.acknowledge_background:
        raise HTTPException(
            status_code=400,
            detail="You must confirm this run continues in the background.",
        )
    if (
        payload.expected_patient_count is not None
        and payload.expected_patient_count != patient_count
    ):
        raise HTTPException(
            status_code=409,
            detail="Patient count changed since preview. Refresh preview and confirm again.",
        )


@router.get("/extractor-status")
def get_extractor_status(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, object]:
    """Return the active extractor backend configuration for UI display."""
    _ = scope
    backend = os.getenv("CODING_EXTRACTOR_BACKEND", "llm")
    strict = os.getenv("CODING_EXTRACTOR_STRICT", "false").lower() == "true"
    model_name = os.getenv("CODING_MODEL_NAME", "")
    model_version = os.getenv("CODING_MODEL_VERSION", "")
    endpoint = os.getenv("CODING_MODEL_ENDPOINT", "http://localhost:8004")
    return {
        "backend": backend,
        "strict": strict,
        "model_name": model_name,
        "model_version": model_version,
        "model_endpoint": endpoint,
        "fallback_enabled": backend == "auto" or (backend == "model" and not strict),
    }


def get_creator() -> PipelineService:
    patient_client = PatientGraphClient()
    patient_client.initialize_schema()
    coding_client = CodingGraphClient()
    coding_client.initialize_schema()
    return PipelineService(patient_client=patient_client, coding_client=coding_client)


def _format_sse(event_type: str, payload: dict[str, object]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


@router.post("/run", response_model=PipelineRunResponse)
def run_pipeline(
    payload: PipelineRunRequest,
    scope: CallerScope = Depends(get_caller_scope),
    service: V3PipelineService = Depends(get_creator),
):
    _ = (payload, scope, service)
    raise HTTPException(
        status_code=410,
        detail=_REMOVED_MSG,
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
        filters = (
            _json.loads(filters_raw) if isinstance(filters_raw, str) else filters_raw
        )
        where_parts, params = [], {}
        if filters.get("org_id"):
            where_parts.append(
                "EXISTS { MATCH (p)-[:REGISTERED_AT]->(o:Organization {id: $org_id}) }"
            )
            params["org_id"] = filters["org_id"]
        if filters.get("episode_status"):
            where_parts.append(
                "EXISTS { MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) WHERE ep.status IN $ep_statuses }"
            )
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
    scope: CallerScope = Depends(get_caller_scope),
):
    _ = (patient_ids, dry_run, workers, scope)
    raise HTTPException(
        status_code=410,
        detail=_REMOVED_MSG,
    )


@router.get("/stream-encounter")
def stream_encounter(
    patient_id: str = Query(min_length=1),
    encounter_id: str = Query(min_length=1),
    dry_run: bool = Query(default=False),
    scope: CallerScope = Depends(get_caller_scope),
):
    _ = (patient_id, encounter_id, dry_run, scope)
    raise HTTPException(
        status_code=410,
        detail=_REMOVED_MSG,
    )


@router.get("/progress/{run_id}")
def stream_progress(run_id: str, scope: CallerScope = Depends(get_caller_scope)):
    """Relay coding-worker progress events for *run_id* to the browser via SSE.

    The coding worker publishes events to Redis pub/sub channel
    ``pipeline:{run_id}`` as each encounter is processed.  This endpoint
    subscribes to that channel and relays the events as SSE, so the browser
    gets the same live feedback regardless of whether the job was dispatched
    via Service Bus or the in-process stream endpoint.

    The connection is automatically closed when:
    - A ``run_completed``, ``pipeline_error``, or ``run_error`` event is received.
    - No events arrive for ``PROGRESS_IDLE_TIMEOUT_S`` seconds (default 5 min).
    """
    _ = scope
    events: queue.Queue[dict | None] = queue.Queue()

    def _redis_listener() -> None:
        try:
            import redis as _redis  # lazy import — redis may not be installed in all envs

            r = _redis.from_url(REDIS_URL)
            last_key = f"pipeline:last:{run_id}"
            last_raw = r.get(last_key)
            if last_raw:
                try:
                    if isinstance(last_raw, bytes):
                        last_raw = last_raw.decode("utf-8")
                    last_event = json.loads(last_raw)
                    if isinstance(last_event, dict):
                        events.put(last_event)
                        if last_event.get("type") in {
                            "run_completed",
                            "pipeline_error",
                            "run_error",
                            "extraction_done",
                            "encounter_completed",
                            "encounter_error",
                        }:
                            return
                except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                    pass
            ps = r.pubsub(ignore_subscribe_messages=True)
            channel = f"pipeline:{run_id}"
            ps.subscribe(channel)
            idle_s = 0.0
            while idle_s < _PROGRESS_IDLE_TIMEOUT_S:
                msg = ps.get_message(timeout=1.0)
                if msg is None:
                    idle_s += 1.0
                    continue
                idle_s = 0.0
                if msg.get("type") != "message":
                    continue
                try:
                    data: dict = json.loads(msg["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                events.put(data)
                if data.get("type") in {
                    "run_completed",
                    "pipeline_error",
                    "run_error",
                    "extraction_done",
                }:
                    break
        except Exception as exc:
            events.put(
                {"type": "pipeline_error", "message": str(exc), "run_id": run_id}
            )
        finally:
            events.put(None)

    threading.Thread(target=_redis_listener, daemon=True).start()

    def _event_generator():
        idle_ticks = 0
        while True:
            try:
                event = events.get(timeout=2.0)
            except queue.Empty:
                idle_ticks += 1
                yield _format_sse(
                    "heartbeat",
                    {"type": "heartbeat", "ts": time.time(), "run_id": run_id},
                )
                if idle_ticks > (_PROGRESS_IDLE_TIMEOUT_S // 2):
                    break
                continue
            if event is None:
                break
            idle_ticks = 0
            yield _format_sse(str(event.get("type", "message")), event)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


_FAILED_EVENTS = frozenset({"pipeline_error", "run_error", "encounter_error"})
_COMPLETED_EVENTS = frozenset(
    {"run_completed", "encounter_completed", "pipeline_done", "extraction_done"}
)
_RUNNING_EVENTS = frozenset(
    {
        "run_started",
        "patient_started",
        "encounter_started",
        "step_completed",
        "step_done",
    }
)
_COMPLETED_STATUSES = frozenset({"completed", "empty_extraction", "needs_review"})

_MAX_BATCH_STATUS_IDS = 500


def _resolve_run_state(payload: dict) -> str:
    event_type = str(payload.get("type") or "")
    status = str(payload.get("status") or "")
    if event_type in _FAILED_EVENTS or status == "error":
        return "failed"
    if event_type in _COMPLETED_EVENTS or status in _COMPLETED_STATUSES:
        return "completed"
    if event_type in _RUNNING_EVENTS:
        return "running"
    return "queued"


def _run_status_snapshot(run_id: str, raw: object) -> dict[str, object]:
    if raw is None:
        return {"run_id": run_id, "state": "queued", "event_type": None, "status": None}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    event_type = str(payload.get("type") or "")
    status = str(payload.get("status") or "")
    return {
        "run_id": run_id,
        "state": _resolve_run_state(payload),
        "event_type": event_type or None,
        "status": status or None,
    }


@router.get("/progress-status/{run_id}")
def get_progress_status(
    run_id: str, scope: CallerScope = Depends(get_caller_scope)
) -> dict[str, object]:
    """Return latest known run status snapshot for UI polling fallback."""
    _ = scope
    try:
        import redis as _redis

        r = _redis.from_url(REDIS_URL)
        raw = r.get(f"pipeline:last:{run_id}")
        return _run_status_snapshot(run_id, raw)
    except Exception:
        return {"run_id": run_id, "state": "queued", "event_type": None, "status": None}


class BatchStatusRequest(BaseModel):
    run_ids: list[str]


@router.post("/progress-status/batch")
def get_progress_status_batch(
    body: BatchStatusRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> list[dict[str, object]]:
    """Return status snapshots for up to 500 run IDs in a single request.

    Used by the UI batch-recode path to avoid opening one SSE connection per
    encounter (which saturates the browser connection pool).
    """
    _ = scope
    run_ids = [r for r in body.run_ids if r][:_MAX_BATCH_STATUS_IDS]
    if not run_ids:
        return []
    try:
        import redis as _redis

        r = _redis.from_url(REDIS_URL)
        keys = [f"pipeline:last:{rid}" for rid in run_ids]
        raws = r.mget(keys)
        return [_run_status_snapshot(rid, raw) for rid, raw in zip(run_ids, raws)]
    except Exception:
        return [
            {"run_id": rid, "state": "queued", "event_type": None, "status": None}
            for rid in run_ids
        ]


@router.get("/stream")
def stream_pipeline(
    patient_ids: str = Query(min_length=1),
    max_encounters_per_patient: int | None = Query(default=None, gt=0),
    dry_run: bool = Query(default=False),
    workers: int = Query(default=4, ge=1, le=8),
    scope: CallerScope = Depends(get_caller_scope),
):
    _ = (patient_ids, max_encounters_per_patient, dry_run, workers, scope)
    raise HTTPException(
        status_code=410,
        detail=_REMOVED_MSG,
    )


def _clean_patients(patient_ids: list[str]) -> dict:
    """Remove all pipeline artefacts for the given patients and return totals.

    Clears Neo4j artefacts (review queue, DOCUMENTS links, shortcut rels,
    LLM usage, coding decisions, sentences payload, alerts, episodes) AND
    Redis checkpoints so a re-run starts completely fresh.

    Returns a dict of {step_name: deleted_count} for audit logging.
    """
    from libs.cypher.cleanup_queries import (
        RESET_PATIENT_REVIEW_QUEUE,
        RESET_PATIENT_DOCUMENTS,
        RESET_PATIENT_DIRECT_SEMANTIC,
        RESET_PATIENT_LLM_USAGE,
        RESET_PATIENT_CODING_DECISIONS,
        RESET_PATIENT_SENTENCES_PAYLOAD,
        RESET_PATIENT_ALERTS,
        RESET_PATIENT_EPISODES,
        RESET_PATIENT_LEGACY_ALERTS,
        RESET_PATIENT_LEGACY_EPISODES,
    )
    from libs.redis_client.checkpoint import CheckpointStore

    pg = PatientGraphClient()
    totals: dict[str, int] = {}
    try:
        with pg.session() as session:
            for pid in patient_ids:
                for query_name, query in [
                    ("review_queue", RESET_PATIENT_REVIEW_QUEUE),
                    ("documents", RESET_PATIENT_DOCUMENTS),
                    ("direct_semantic", RESET_PATIENT_DIRECT_SEMANTIC),
                    ("llm_usage", RESET_PATIENT_LLM_USAGE),
                    ("coding_decisions", RESET_PATIENT_CODING_DECISIONS),
                    ("sentences_payload", RESET_PATIENT_SENTENCES_PAYLOAD),
                    ("alerts", RESET_PATIENT_ALERTS),
                    ("episodes", RESET_PATIENT_EPISODES),
                    ("legacy_alerts", RESET_PATIENT_LEGACY_ALERTS),
                    ("legacy_episodes", RESET_PATIENT_LEGACY_EPISODES),
                ]:
                    r = session.run(query, patient_id=pid).single()
                    count = 0
                    if r:
                        count = int(
                            r.get(
                                "deleted",
                                r.get("links_deleted", r.get("direct_deleted", 0)),
                            )
                            or 0
                        )
                    totals[query_name] = totals.get(query_name, 0) + count
                    logger.info(
                        "Patient reset step=%s patient=%s deleted=%d",
                        query_name,
                        pid,
                        count,
                    )
    finally:
        pg.close()

    logger.info(
        "Patient reset complete patients=%s totals=%s",
        patient_ids,
        totals,
    )

    # Clear Redis checkpoints so retries get a genuinely fresh run
    try:
        store = CheckpointStore()
        redis_deleted = 0
        for pid in patient_ids:
            store.delete_pattern(f"classify:{pid}:*")
            store.delete_pattern(f"analysis:{pid}:*")
            redis_deleted += 1
        totals["redis_checkpoints_cleared"] = redis_deleted
        logger.info(
            "Patient reset cleared Redis checkpoints patients=%s count=%d",
            patient_ids,
            redis_deleted,
        )
    except Exception:
        logger.warning(
            "Could not clear Redis checkpoints during patient clean", exc_info=True
        )

    return totals


@router.get("/gold-training/stats")
async def gold_training_stats(_: CallerScope = Depends(get_caller_scope)) -> dict:
    """Return counts of TrainingCandidates by status for the run UI."""
    from libs.cypher.training_candidate_queries import GET_TRAINING_CANDIDATE_STATS

    client = CodingGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_TRAINING_CANDIDATE_STATS).single()
            if not row:
                return {
                    "total": 0,
                    "pending": 0,
                    "processing": 0,
                    "completed": 0,
                    "failed": 0,
                }
            return dict(row)
    finally:
        client.close()


@router.post("/run-gold-training")
async def run_gold_training(
    payload: RunGoldTrainingRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict:
    """Queue gold training pipeline jobs — one per TrainingCandidate.

    Fetches pending (or specified) TrainingCandidate nodes from the Knowledge
    Graph and publishes one pipeline-job message per candidate to the Service
    Bus pipeline queue.  The pipeline worker picks each up and runs the
    gold training PlanDefinition, writing GoldLabel outputs back to the KG.
    """
    from libs.cypher.training_candidate_queries import (
        GET_TRAINING_CANDIDATES_PAGE,
        GET_TRAINING_CANDIDATE_BY_ID,
    )
    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    client = CodingGraphClient()
    candidates: list[dict] = []
    try:
        with client.session() as session:
            if payload.mode == "specific" and payload.candidate_ids:
                for cid in payload.candidate_ids:
                    row = session.run(
                        GET_TRAINING_CANDIDATE_BY_ID, candidate_id=cid
                    ).single()
                    if row:
                        candidates.append(dict(row))
            else:
                # All pending candidates (paginated in batches of 500)
                skip = 0
                while True:
                    batch = list(
                        session.run(
                            GET_TRAINING_CANDIDATES_PAGE,
                            status="pending",
                            source=None,
                            search=None,
                            skip=skip,
                            limit=500,
                        )
                    )
                    if not batch:
                        break
                    candidates.extend(dict(r) for r in batch)
                    if len(batch) < 500:
                        break
                    skip += 500
    finally:
        client.close()

    if not candidates:
        raise HTTPException(
            status_code=404, detail="No matching TrainingCandidates found."
        )

    run_id = str(uuid.uuid4())
    bus = create_message_bus()
    try:
        for cand in candidates:
            msg = Message(
                body={
                    "event_type": "gold-training-run",
                    "patient_id": "",  # not patient-scoped
                    "encounter_id": None,
                    "plan_definition_id": payload.plan_definition_id,
                    "context": {
                        "candidate_id": cand["candidate_id"],
                        "encounter_text": cand.get("text", ""),
                        "output_target": "gold_training",
                        "dry_run": payload.preview,
                    },
                },
                correlation_id=run_id,
            )
            await bus.send(PIPELINE_QUEUE, msg)
    finally:
        await bus.close()

    return {
        "run_id": run_id,
        "queued": len(candidates),
        "mode": payload.mode,
        "preview": payload.preview,
        "stream_path": f"/api/pipeline/progress/{run_id}",
    }


@router.post("/run-patient")
async def run_patient(
    payload: RunPatientRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    patient_id = payload.patient_id.strip()
    if not patient_id:
        raise HTTPException(status_code=400, detail="patient_id is required")
    _require_patients_in_scope(scope, [patient_id])

    run_id = str(uuid.uuid4())
    cleaned_totals: dict[str, int] | None = None
    encounter_jobs: list[dict[str, str]] = []

    try:
        if payload.action == "recode_all":
            cleaned_totals = _clean_patients([patient_id])
            encounter_jobs = _expand_patients_to_clinical_encounters([patient_id])
            if not encounter_jobs:
                raise HTTPException(
                    status_code=404,
                    detail=f"No clinical encounters with text found for patient {patient_id}",
                )
            queued = await _publish_coding_jobs(
                encounter_jobs,
                run_id=run_id,
                mode="all",
                preview=payload.preview,
                trigger_analysis=False,
            )
        elif payload.action == "code_new":
            encounter_jobs = _expand_patients_to_clinical_encounters([patient_id])
            if not encounter_jobs:
                raise HTTPException(
                    status_code=404,
                    detail=f"No clinical encounters with text found for patient {patient_id}",
                )
            queued = await _publish_coding_jobs(
                encounter_jobs,
                run_id=run_id,
                mode="unprocessed",
                preview=payload.preview,
                trigger_analysis=False,
            )
        elif payload.action == "run_analysis":
            queued = await _publish_analysis_jobs([patient_id], run_id=run_id)
        elif payload.action == "full_pipeline":
            # Clean all existing artefacts first so the re-run starts from a
            # blank slate.  This mirrors recode_all but also triggers episode
            # detection after coding completes.
            cleaned_totals = _clean_patients([patient_id])
            logger.info(
                "full_pipeline reset complete patient=%s cleaned=%s",
                patient_id,
                cleaned_totals,
            )
            encounter_jobs = _expand_patients_to_clinical_encounters([patient_id])
            if not encounter_jobs:
                raise HTTPException(
                    status_code=404,
                    detail=f"No clinical encounters with text found for patient {patient_id}",
                )
            queued = await _publish_coding_jobs(
                encounter_jobs,
                run_id=run_id,
                mode="all",
                preview=payload.preview,
                trigger_analysis=True,
            )
            try:
                from libs.redis_client.rebuild_status import begin_rebuild

                begin_rebuild(patient_id, run_id, len(encounter_jobs))
            except Exception:
                logger.warning(
                    "Could not set rebuild status patient=%s run=%s",
                    patient_id,
                    run_id,
                    exc_info=True,
                )
        else:  # pragma: no cover - Literal keeps this unreachable
            raise HTTPException(
                status_code=400, detail=f"Unsupported action: {payload.action}"
            )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "failed",
                "run_id": run_id,
                "action": payload.action,
                "error": str(exc),
            },
        ) from exc

    return {
        "run_id": run_id,
        "queued": queued,
        "patient_ids": [patient_id],
        "action": payload.action,
        "preview": payload.preview,
        "stream_path": f"/api/pipeline/progress/{run_id}",
        "cleaned_totals": cleaned_totals,
    }


@router.post("/run-cohort")
async def run_cohort(
    payload: RunCohortRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    patient_ids = [pid.strip() for pid in payload.patient_ids if pid and pid.strip()]
    if not patient_ids:
        raise HTTPException(
            status_code=400, detail="At least one patient_id is required"
        )
    _require_patients_in_scope(scope, patient_ids)

    run_id = str(uuid.uuid4())
    cleaned_totals: dict[str, int] | None = None
    encounter_jobs: list[dict[str, str]] = []
    try:
        if payload.action == "recode_all":
            cleaned_totals = _clean_patients(patient_ids)
            encounter_jobs = _expand_patients_to_clinical_encounters(patient_ids)
            if not encounter_jobs:
                raise HTTPException(
                    status_code=404,
                    detail="No clinical encounters with text found for requested patients",
                )
            queued = await _publish_coding_jobs(
                encounter_jobs,
                run_id=run_id,
                mode="all",
                preview=payload.preview,
                trigger_analysis=False,
            )
        elif payload.action == "code_new":
            encounter_jobs = _expand_patients_to_clinical_encounters(patient_ids)
            if not encounter_jobs:
                raise HTTPException(
                    status_code=404,
                    detail="No clinical encounters with text found for requested patients",
                )
            queued = await _publish_coding_jobs(
                encounter_jobs,
                run_id=run_id,
                mode="unprocessed",
                preview=payload.preview,
                trigger_analysis=False,
            )
        elif payload.action == "full_pipeline":
            encounter_jobs = _expand_patients_to_clinical_encounters(patient_ids)
            if not encounter_jobs:
                raise HTTPException(
                    status_code=404,
                    detail="No clinical encounters with text found for requested patients",
                )
            queued = await _publish_coding_jobs(
                encounter_jobs,
                run_id=run_id,
                mode="all",
                preview=payload.preview,
                trigger_analysis=True,
            )
        elif payload.action == "run_analysis":
            queued = await _publish_analysis_jobs(patient_ids, run_id=run_id)
        else:  # pragma: no cover
            raise HTTPException(
                status_code=400, detail=f"Unsupported action: {payload.action}"
            )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "failed",
                "run_id": run_id,
                "action": payload.action,
                "error": str(exc),
            },
        ) from exc

    return {
        "run_id": run_id,
        "queued": queued,
        "patient_ids": patient_ids,
        "action": payload.action,
        "preview": payload.preview,
        "stream_path": f"/api/pipeline/progress/{run_id}",
        "cleaned_totals": cleaned_totals,
    }


@router.post("/run-all-patients")
async def run_all_patients(
    payload: RunAllPatientsRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Bulk reset and reprocess all scoped patients with explicit safety gates."""
    patient_ids = _resolve_scope_patients(scope, payload.org_id)
    if not patient_ids:
        raise HTTPException(
            status_code=404, detail="No patients found for the selected scope"
        )

    encounter_jobs = _expand_patients_to_clinical_encounters(patient_ids)
    patient_count = len(patient_ids)
    encounter_count = len(encounter_jobs)

    if payload.preview:
        return {
            "preview": True,
            "org_id": payload.org_id,
            "patient_count": patient_count,
            "encounter_count": encounter_count,
            "confirmation_text_required": _BULK_RESET_CONFIRM_TEXT,
        }

    _validate_bulk_run_confirmation(payload, patient_count=patient_count)

    if not encounter_jobs:
        raise HTTPException(
            status_code=404,
            detail="No clinical encounters with text found for selected patients",
        )

    run_id = str(uuid.uuid4())
    cleaned_totals = _clean_patients(patient_ids)
    try:
        queued = await _publish_coding_jobs(
            encounter_jobs,
            run_id=run_id,
            mode="all",
            preview=False,
            trigger_analysis=True,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "failed",
                "run_id": run_id,
                "action": "bulk_full_pipeline",
                "error": str(exc),
            },
        ) from exc

    return {
        "preview": False,
        "run_id": run_id,
        "queued": queued,
        "patient_count": patient_count,
        "encounter_count": encounter_count,
        "org_id": payload.org_id,
        "stream_path": f"/api/pipeline/progress/{run_id}",
        "cleaned_totals": cleaned_totals,
    }


@router.post("/clean-patients")
def clean_patients_endpoint(
    payload: PipelineRunRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
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
        raise HTTPException(400, "Provide patient_ids, cohort_id, or org_id")
    _require_patients_in_scope(scope, patient_ids)

    totals = _clean_patients(patient_ids)
    return {
        "patients_cleaned": len(patient_ids),
        "totals": totals,
    }


# ── HITL Classification Review ─────────────────────────────────────────────


class ClassificationVoteRequest(BaseModel):
    encounter_id: str
    correct_type: str  # "clinical" | "admin_only" | "document_transfer"
    model_a_type: str  # what model A originally said
    model_b_type: str  # what model B originally said
    notes: str = ""
    reviewer: str = "unknown"


@router.get("/classification-disagreements")
async def get_classification_disagreements(
    scope: CallerScope = Depends(get_caller_scope),
    patient_id: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """Return encounters where the two classification models disagreed.

    Pass ``patient_id`` to scope to a single patient, or omit to get all
    disagreements across the database (paginated via skip/limit).
    Also returns the pending count (disagreements with no vote yet).
    """
    from libs.cypher.classification_vote_queries import (
        GET_CLASSIFICATION_DISAGREEMENTS,
        GET_ALL_DISAGREEMENTS,
        COUNT_DISAGREEMENTS_PENDING_REVIEW,
    )

    if patient_id and not scope.is_admin:
        _require_patients_in_scope(scope, [patient_id])

    client = PatientGraphClient()
    try:
        with client.session() as session:
            if patient_id:
                rows = session.run(
                    GET_CLASSIFICATION_DISAGREEMENTS, patient_id=patient_id
                )
            else:
                rows = session.run(GET_ALL_DISAGREEMENTS, skip=skip, limit=limit)

            disagreements = [dict(r) for r in rows]

            pending_result = session.run(COUNT_DISAGREEMENTS_PENDING_REVIEW)
            pending_count = pending_result.single()["pending_count"]

        return {
            "disagreements": disagreements,
            "total_returned": len(disagreements),
            "pending_review": pending_count,
        }
    finally:
        client.close()


@router.post("/classification-vote")
async def submit_classification_vote(
    payload: ClassificationVoteRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Record a human reviewer's verdict on a classification disagreement.

    Writes a ``ClassificationVote`` node linked to the ``Encounter`` and
    updates ``classification_content_type`` with the human-verified label.
    Also sets ``classification_human_corrected = true`` on the encounter.
    Invalidates the few-shot example cache so the next classification run
    picks up the new vote immediately.
    """
    from libs.cypher.classification_vote_queries import UPSERT_CLASSIFICATION_VOTE
    from libs.prompts.few_shot_builder import invalidate_cache as _invalidate_few_shot

    model_a_was_correct = payload.model_a_type == payload.correct_type
    model_b_was_correct = payload.model_b_type == payload.correct_type

    client = PatientGraphClient()
    try:
        with client.session() as session:
            result = session.run(
                UPSERT_CLASSIFICATION_VOTE,
                encounter_id=payload.encounter_id,
                correct_type=payload.correct_type,
                model_a_was_correct=model_a_was_correct,
                model_b_was_correct=model_b_was_correct,
                reviewer=payload.reviewer,
                notes=payload.notes,
                model_a_type=payload.model_a_type,
                model_b_type=payload.model_b_type,
            )
            row = result.single()
        result = {
            "encounter_id": row["encounter_id"],
            "correct_type": row["correct_type"],
            "model_a_was_correct": model_a_was_correct,
            "model_b_was_correct": model_b_was_correct,
        }
    finally:
        client.close()

    # Invalidate the in-process few-shot cache so the next classify run
    # can pick up this new example without waiting for the TTL.
    _invalidate_few_shot()

    return result


@router.get("/classification-scorecard")
async def get_classification_scorecard(
    scope: CallerScope = Depends(get_caller_scope),
):
    """Return aggregate accuracy stats for Model A (Haiku) vs Model B (GPT-5-mini)."""
    from libs.cypher.classification_vote_queries import GET_MODEL_SCORECARD

    client = PatientGraphClient()
    try:
        with client.session() as session:
            result = session.run(GET_MODEL_SCORECARD)
            row = result.single()
            if not row or row["total_votes"] == 0:
                return {
                    "model_a_correct": 0,
                    "model_b_correct": 0,
                    "both_wrong": 0,
                    "total_votes": 0,
                }
            total = row["total_votes"]
            return {
                "model_a_label": "Claude Haiku (AWS)",
                "model_b_label": "GPT-5-mini (Azure)",
                "model_a_correct": row["model_a_correct"],
                "model_b_correct": row["model_b_correct"],
                "both_wrong": row["both_wrong"],
                "total_votes": total,
                "model_a_accuracy_pct": round(row["model_a_correct"] / total * 100, 1),
                "model_b_accuracy_pct": round(row["model_b_correct"] / total * 100, 1),
            }
    finally:
        client.close()


@router.post("/enqueue-recode")
async def enqueue_recode(
    payload: PipelineRunRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Re-run canonical extraction/coding path only.

    Reads ``classification_content_type = 'clinical'`` directly from Neo4j
    for each patient (classification must have already been run) and fans out
    one ``extract_encounter`` job per clinical encounter.
    """
    patient_ids = payload.patient_ids
    if not patient_ids and payload.cohort_id:
        patient_ids = _resolve_cohort_patients(payload.cohort_id)
    if not patient_ids and payload.org_id:
        patient_ids = _resolve_org_patients(payload.org_id)
    if not patient_ids:
        raise HTTPException(400, "Provide patient_ids, cohort_id, or org_id")
    _require_patients_in_scope(scope, patient_ids)

    run_id = str(uuid.uuid4())
    # Standalone coding-worker (coding-jobs queue) is deprecated; use pipeline-jobs.
    await _publish_coding_jobs(
        patient_ids,
        run_id=run_id,
        mode="extract_patient",
        preview=payload.dry_run,
        trigger_analysis=True,
    )

    return {
        "run_id": run_id,
        "queued": len(patient_ids),
        "patient_ids": patient_ids,
        "mode": "extract_patient",
        "note": "Classification skipped — using existing classification_content_type from Neo4j; jobs sent to pipeline-jobs",
    }


@router.get("/gold-dataset-stats")
async def get_gold_dataset_stats(
    scope: CallerScope = Depends(get_caller_scope),
):
    """Return gold dataset health and extraction model quality signals.

    Parses ``sentences_json`` from all reviewed candidates to produce:
    - Review outcome counts (approved / edited / rejected / escalated)
    - Per-semantic-tag entity counts in the gold set (approved candidates)
    - Per-semantic-tag candidate counts by approval action (quality proxy)
    - Gold set coverage: unique patients, encounters, date range

    Approval rate per tag is a proxy for extraction precision on that tag type —
    if 90% of candidates containing ``finding`` terms were approved without edit,
    the model has high precision on findings.
    """
    from libs.cypher.candidate_queries import GET_CANDIDATES_FOR_SCORECARD

    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = [dict(r) for r in session.run(GET_CANDIDATES_FOR_SCORECARD)]
    finally:
        client.close()

    if not rows:
        return {
            "total_reviewed": 0,
            "outcomes": {},
            "gold_entities_by_tag": {},
            "per_tag_scorecard": [],
            "patients_covered": 0,
            "encounters_covered": 0,
        }

    # -----------------------------------------------------------------------
    # Aggregate outcome counts
    # -----------------------------------------------------------------------
    outcome_counts: dict[str, int] = {}
    reviewer_set: set[str] = set()
    dates: list[str] = []
    gold_patients: set[str] = set()
    gold_entities_by_tag: dict[str, int] = {}

    # per_tag: tag -> {approved, edited, rejected, escalated, total_candidates}
    per_tag: dict[str, dict[str, int]] = {}

    for row in rows:
        action = row.get("last_action") or row.get("approval_status", "unknown")
        # Normalise: edit action → approved status
        if action == "edit":
            action = "edited"
        outcome_counts[action] = outcome_counts.get(action, 0) + 1
        if row.get("reviewer"):
            reviewer_set.add(row["reviewer"])
        if row.get("date"):
            dates.append(str(row["date"])[:10])

        # Parse sentences_json → term stats
        sentences_raw = row.get("sentences_json") or "[]"
        try:
            sentences = (
                json.loads(sentences_raw)
                if isinstance(sentences_raw, str)
                else sentences_raw
            )
        except (json.JSONDecodeError, TypeError):
            sentences = []

        tags_in_candidate: set[str] = set()
        for sentence in sentences:
            for term in sentence.get("terms", []):
                tag = str(term.get("semantic_tag") or "unknown").lower()
                tags_in_candidate.add(tag)
                # Gold entity count (approved or edited = human-verified)
                if action in ("approve", "edited", "approved"):
                    gold_entities_by_tag[tag] = gold_entities_by_tag.get(tag, 0) + 1
                    gold_patients.add(row.get("patient_id", ""))

        # Per-tag candidate quality
        for tag in tags_in_candidate:
            if tag not in per_tag:
                per_tag[tag] = {
                    "approved": 0,
                    "edited": 0,
                    "rejected": 0,
                    "escalated": 0,
                    "total": 0,
                }
            per_tag[tag]["total"] += 1
            bucket = (
                action if action in ("edited", "rejected", "escalated") else "approved"
            )
            per_tag[tag][bucket] = per_tag[tag].get(bucket, 0) + 1

    total = len(rows)

    # -----------------------------------------------------------------------
    # Per-tag scorecard rows (sorted by total descending)
    # -----------------------------------------------------------------------
    scorecard = []
    for tag, counts in sorted(per_tag.items(), key=lambda x: -x[1]["total"]):
        t = counts["total"]
        approved = counts.get("approved", 0)
        edited = counts.get("edited", 0)
        rejected = counts.get("rejected", 0)
        escalated = counts.get("escalated", 0)
        # Approval rate = candidates approved (with or without edit) / total with this tag
        human_verified = approved + edited
        approval_rate = round(human_verified / t * 100, 1) if t > 0 else None
        rejection_rate = round(rejected / t * 100, 1) if t > 0 else None
        scorecard.append(
            {
                "tag": tag,
                "total_candidates": t,
                "approved": approved,
                "edited": edited,
                "rejected": rejected,
                "escalated": escalated,
                "human_verified": human_verified,
                "approval_rate_pct": approval_rate,
                "rejection_rate_pct": rejection_rate,
                "gold_entities": gold_entities_by_tag.get(tag, 0),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_reviewed": total,
        "outcomes": outcome_counts,
        "overall_approval_rate_pct": (
            round(
                sum(
                    1
                    for r in rows
                    if r.get("last_action") in ("approve", "edit")
                    or r.get("approval_status") == "approved"
                )
                / total
                * 100,
                1,
            )
            if total > 0
            else None
        ),
        "reviewers": sorted(reviewer_set),
        "gold_entities_by_tag": gold_entities_by_tag,
        "total_gold_entities": sum(gold_entities_by_tag.values()),
        "patients_covered": len(gold_patients),
        "encounters_covered": sum(
            1 for r in rows if r.get("approval_status") in ("approved",)
        ),
        "date_from": min(dates) if dates else None,
        "date_to": max(dates) if dates else None,
        "per_tag_scorecard": scorecard,
    }


@router.post("/backfill-documents")
async def backfill_documents(
    payload: dict | None = None,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Re-materialise :DOCUMENTS and :HAS_<tag> links from existing EncounterCandidate nodes.

    Useful when candidates were created before the coding worker was updated to
    write DOCUMENTS links automatically.  Safe to run multiple times — the
    underlying MERGE queries are idempotent.

    Optional body: ``{"patient_id": "9990000002"}`` to restrict to one patient.
    Omit body (or pass ``{}``) to process all candidates.
    """
    from libs.cypher.documents_queries import write_documents_from_sentences_payload

    patient_filter = (payload or {}).get("patient_id")

    client = PatientGraphClient()
    if patient_filter:
        cypher = (
            "MATCH (c:EncounterCandidate) "
            "WHERE c.patient_id = $pid AND c.sentences_json IS NOT NULL "
            "RETURN c.encounter_id AS encounter_id, "
            "c.patient_id AS patient_id, "
            "c.approval_status AS approval_status, "
            "c.sentences_json AS sentences_json"
        )
        params: dict = {"pid": str(patient_filter)}
    else:
        cypher = (
            "MATCH (c:EncounterCandidate) "
            "WHERE c.sentences_json IS NOT NULL "
            "RETURN c.encounter_id AS encounter_id, "
            "c.patient_id AS patient_id, "
            "c.approval_status AS approval_status, "
            "c.sentences_json AS sentences_json"
        )
        params = {}

    with client.session() as session:
        rows = list(session.run(cypher, **params))

    total_links = 0
    total_candidates = 0

    with client.session() as session:
        for row in rows:
            sentences_payload = json.loads(row["sentences_json"] or "[]")
            source = (
                "human_reviewed"
                if row.get("approval_status") == "approved"
                else "provisional"
            )
            written = write_documents_from_sentences_payload(
                row["encounter_id"],
                sentences_payload,
                session,
                source=source,
            )
            total_links += written
            total_candidates += 1

    return {
        "candidates_processed": total_candidates,
        "documents_written": total_links,
        "patient_filter": patient_filter,
    }


@router.get("/classification-prompt-preview")
async def get_classification_prompt_preview(
    scope: CallerScope = Depends(get_caller_scope),
):
    """Return the current effective classification prompt including any few-shot examples.

    Shows the base (v1) prompt, the dynamically generated few-shot section built
    from human-reviewed votes, and the combined prompt that the classifier will
    actually use.  Useful for auditing what the models are being told and for
    verifying that new votes are being incorporated correctly.
    """
    from libs.prompts.registry import get_prompt
    from libs.prompts.few_shot_builder import (
        build_few_shot_section,
        get_cached_examples,
        example_counts,
    )

    base_prompt = get_prompt("encounter_classify", version=1)
    few_shot_section = build_few_shot_section()
    examples_by_class = get_cached_examples()
    counts = example_counts()

    return {
        "base_prompt": base_prompt,
        "few_shot_section": few_shot_section if few_shot_section else None,
        "combined_prompt": (
            base_prompt + few_shot_section if few_shot_section else base_prompt
        ),
        "using_few_shot": bool(few_shot_section),
        "example_counts": counts,
        "total_examples": sum(counts.values()),
        "examples_by_class": examples_by_class,
    }


@router.get("/classification-report")
async def get_classification_report(
    scope: CallerScope = Depends(get_caller_scope),
):
    """Return full validation evidence report for ISO 13485 / ISO 14971.

    Includes: overall accuracy, per-class precision/recall/F1 for each model,
    confusion breakdown, reviewer list, date range, and a complete audit trail
    of all human-reviewed disagreement cases.
    """
    from libs.cypher.classification_vote_queries import (
        GET_ALL_VOTED,
        GET_CONFUSION_BREAKDOWN,
        GET_MODEL_SCORECARD,
    )

    CLASSES = ["clinical", "admin_only", "document_transfer"]

    client = PatientGraphClient()
    try:
        with client.session() as session:
            scorecard_row = session.run(GET_MODEL_SCORECARD).single()
            voted_rows = [dict(r) for r in session.run(GET_ALL_VOTED)]
            confusion_rows = [dict(r) for r in session.run(GET_CONFUSION_BREAKDOWN)]
    finally:
        client.close()

    if not voted_rows:
        return {
            "total_reviewed": 0,
            "audit_trail": [],
            "message": "No votes recorded yet",
        }

    total = len(voted_rows)

    def per_class_metrics(predicted_field: str) -> dict:
        metrics = {}
        for cls in CLASSES:
            tp = sum(
                1
                for r in voted_rows
                if r[predicted_field] == cls and r["human_verdict"] == cls
            )
            fp = sum(
                1
                for r in voted_rows
                if r[predicted_field] == cls and r["human_verdict"] != cls
            )
            fn = sum(
                1
                for r in voted_rows
                if r[predicted_field] != cls and r["human_verdict"] == cls
            )
            precision = tp / (tp + fp) if (tp + fp) > 0 else None
            recall = tp / (tp + fn) if (tp + fn) > 0 else None
            f1 = (
                2 * precision * recall / (precision + recall)
                if precision and recall
                else None
            )
            metrics[cls] = {
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "support": tp + fn,
                "precision_pct": (
                    round(precision * 100, 1) if precision is not None else None
                ),
                "recall_pct": round(recall * 100, 1) if recall is not None else None,
                "f1_pct": round(f1 * 100, 1) if f1 is not None else None,
            }
        return metrics

    timestamps = [r["voted_at"] for r in voted_rows if r.get("voted_at")]
    reviewers = sorted(set(r["reviewer"] for r in voted_rows if r.get("reviewer")))
    sc = scorecard_row or {}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_reviewed": total,
            "haiku_correct": sc.get("model_a_correct", 0),
            "haiku_accuracy_pct": round(sc.get("model_a_correct", 0) / total * 100, 1),
            "gpt_correct": sc.get("model_b_correct", 0),
            "gpt_accuracy_pct": round(sc.get("model_b_correct", 0) / total * 100, 1),
            "both_wrong": sc.get("both_wrong", 0),
            "both_wrong_pct": round(sc.get("both_wrong", 0) / total * 100, 1),
            "date_from": min(timestamps) if timestamps else None,
            "date_to": max(timestamps) if timestamps else None,
            "reviewers": reviewers,
        },
        "haiku_per_class": per_class_metrics("haiku_predicted"),
        "gpt_per_class": per_class_metrics("gpt_predicted"),
        "confusion_breakdown": confusion_rows,
        "audit_trail": voted_rows,
    }
