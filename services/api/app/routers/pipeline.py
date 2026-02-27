"""Pipeline endpoints for candidate generation."""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone

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
    """Remove all pipeline artefacts for the given patients and return totals.

    Clears Neo4j artefacts (candidates, documents, alerts, episodes) AND
    Redis checkpoints (classification and analysis stage caches) so a
    re-run starts completely fresh.
    """
    from libs.cypher.cleanup_queries import (
        RESET_PATIENT_REVIEW_QUEUE,
        RESET_PATIENT_DOCUMENTS,
        RESET_PATIENT_DIRECT_SEMANTIC,
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

    # Clear Redis checkpoints so retries get a genuinely fresh run
    try:
        store = CheckpointStore()
        redis_deleted = 0
        for pid in patient_ids:
            store.delete_pattern(f"classify:{pid}:*")
            store.delete_pattern(f"analysis:{pid}:*")
            redis_deleted += 1
        totals["redis_checkpoints_cleared"] = redis_deleted
    except Exception:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "Could not clear Redis checkpoints during patient clean", exc_info=True
        )

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
async def enqueue_consensus(
    payload: PipelineRunRequest,
    clean: bool = Query(default=True),
    mode: str = Query(default="consensus_fanout"),
):
    """Publish coding jobs to the message bus for worker-based consensus processing.

    Default mode is ``consensus_fanout``: the first worker to pick up the
    message acts as coordinator — it splits encounters into chunks and
    re-publishes them so multiple worker replicas can classify in parallel.

    Set ``mode=consensus`` for a single-worker run (useful for debugging).
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
                    "mode": mode,
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
        "mode": mode,
        "queue": CODING_QUEUE,
    }
    if clean_totals is not None:
        result["clean_totals"] = clean_totals
    return result


# ── HITL Classification Review ─────────────────────────────────────────────

from pydantic import BaseModel as _BaseModel  # noqa: E402


class ClassificationVoteRequest(_BaseModel):
    encounter_id: str
    correct_type: str          # "clinical" | "admin_only" | "document_transfer"
    model_a_type: str          # what model A originally said
    model_b_type: str          # what model B originally said
    notes: str = ""
    reviewer: str = "unknown"


@router.get("/classification-disagreements")
async def get_classification_disagreements(
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

    client = PatientGraphClient()
    try:
        with client.session() as session:
            if patient_id:
                rows = session.run(GET_CLASSIFICATION_DISAGREEMENTS, patient_id=patient_id)
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
async def submit_classification_vote(payload: ClassificationVoteRequest):
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
async def get_classification_scorecard():
    """Return aggregate accuracy stats for Model A (Haiku) vs Model B (GPT-5-mini)."""
    from libs.cypher.classification_vote_queries import GET_MODEL_SCORECARD

    client = PatientGraphClient()
    try:
        with client.session() as session:
            result = session.run(GET_MODEL_SCORECARD)
            row = result.single()
            if not row or row["total_votes"] == 0:
                return {"model_a_correct": 0, "model_b_correct": 0, "both_wrong": 0, "total_votes": 0}
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
async def enqueue_recode(payload: PipelineRunRequest):
    """Re-run extraction/coding only — skip classification.

    Reads ``classification_content_type = 'clinical'`` directly from Neo4j
    for each patient (classification must have already been run) and fans out
    one ``extract_encounter`` job per clinical encounter.

    Use this after fixing the persist bug to recode already-classified patients
    without paying the cost of re-running the two-model classification.
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
                    "mode": "extract_patient",
                    "trigger_analysis": True,
                },
                correlation_id=run_id,
            )
            await bus.send(CODING_QUEUE, msg)
    finally:
        await bus.close()

    return {
        "run_id": run_id,
        "queued": len(patient_ids),
        "patient_ids": patient_ids,
        "mode": "extract_patient",
        "note": "Classification skipped — using existing classification_content_type from Neo4j",
    }


@router.get("/gold-dataset-stats")
async def get_gold_dataset_stats():
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
            sentences = json.loads(sentences_raw) if isinstance(sentences_raw, str) else sentences_raw
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
                per_tag[tag] = {"approved": 0, "edited": 0, "rejected": 0, "escalated": 0, "total": 0}
            per_tag[tag]["total"] += 1
            bucket = action if action in ("edited", "rejected", "escalated") else "approved"
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
        scorecard.append({
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
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_reviewed": total,
        "outcomes": outcome_counts,
        "overall_approval_rate_pct": round(
            sum(1 for r in rows if r.get("last_action") in ("approve", "edit") or r.get("approval_status") == "approved") / total * 100, 1
        ) if total > 0 else None,
        "reviewers": sorted(reviewer_set),
        "gold_entities_by_tag": gold_entities_by_tag,
        "total_gold_entities": sum(gold_entities_by_tag.values()),
        "patients_covered": len(gold_patients),
        "encounters_covered": sum(1 for r in rows if r.get("approval_status") in ("approved",)),
        "date_from": min(dates) if dates else None,
        "date_to": max(dates) if dates else None,
        "per_tag_scorecard": scorecard,
    }


@router.post("/backfill-documents")
async def backfill_documents(payload: dict | None = None):
    """Re-materialise :DOCUMENTS and :HAS_<tag> links from existing EncounterCandidate nodes.

    Useful when candidates were created before the coding worker was updated to
    write DOCUMENTS links automatically.  Safe to run multiple times — the
    underlying MERGE queries are idempotent.

    Optional body: ``{"patient_id": "4203796334"}`` to restrict to one patient.
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
async def get_classification_prompt_preview():
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
        "combined_prompt": base_prompt + few_shot_section if few_shot_section else base_prompt,
        "using_few_shot": bool(few_shot_section),
        "example_counts": counts,
        "total_examples": sum(counts.values()),
        "examples_by_class": examples_by_class,
    }


@router.get("/classification-report")
async def get_classification_report():
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
        return {"total_reviewed": 0, "audit_trail": [], "message": "No votes recorded yet"}

    total = len(voted_rows)

    def per_class_metrics(predicted_field: str) -> dict:
        metrics = {}
        for cls in CLASSES:
            tp = sum(1 for r in voted_rows if r[predicted_field] == cls and r["human_verdict"] == cls)
            fp = sum(1 for r in voted_rows if r[predicted_field] == cls and r["human_verdict"] != cls)
            fn = sum(1 for r in voted_rows if r[predicted_field] != cls and r["human_verdict"] == cls)
            precision = tp / (tp + fp) if (tp + fp) > 0 else None
            recall = tp / (tp + fn) if (tp + fn) > 0 else None
            f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
            metrics[cls] = {
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "support": tp + fn,
                "precision_pct": round(precision * 100, 1) if precision is not None else None,
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
