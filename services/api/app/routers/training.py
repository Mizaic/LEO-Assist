"""Training data management router.

Exposes the TrainingLabel store — the single source of truth for all NER
training data — so reviewers can inspect, include, and exclude individual
labels before triggering a training run.

Routes
------
GET  /training/labels/stats            — corpus statistics (total, by source)
GET  /training/labels                  — paginated label list with filters
GET  /training/labels/{label_id}       — single label detail
POST /training/labels/{label_id}/exclude  — mark excluded (with reason)
POST /training/labels/{label_id}/include  — re-include
POST /training/labels/bulk-import      — bulk upsert from scripts
POST /training/export-preview          — dry-run count of what would be exported
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import threading
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from app.deps import require_admin
from libs.cypher.training_label_queries import (
    COUNT_EXPORTABLE_LABELS,
    COUNT_TRAINING_LABELS_PAGE,
    EXCLUDE_TRAINING_LABEL,
    GET_ALL_INCLUDED_LABELS_FOR_EXPORT,
    GET_TRAINING_LABEL_BY_ID,
    GET_TRAINING_LABEL_STATS,
    GET_TRAINING_LABELS_PAGE,
    INCLUDE_TRAINING_LABEL,
    LABEL_ENTITY_TYPE_BREAKDOWN,
    UPDATE_TRAINING_LABEL_ENTITIES,
)
from libs.cypher.coding_review_queries import (
    AUTO_RESOLVE_CODING_REVIEW,
    BATCH_RESOLVE_BY_ENTITY_TEXT,
    COUNT_ASSERTION_REVIEW_GROUPS,
    COUNT_CODING_REVIEW_GROUPS,
    COUNT_CODING_REVIEW_PENDING,
    DEACTIVATE_CODING_IGNORE_RULE,
    GET_ALL_CODING_IGNORE_RULES,
    GET_ASSERTION_REVIEW_QUEUE,
    GET_CODING_IGNORE_RULES,
    GET_CODING_REVIEW_FOR_ENTITY,
    GET_CODING_REVIEW_QUEUE,
    GET_CODING_REVIEW_STATS,
    GET_ENCOUNTER_SIBLINGS,
    GET_PENDING_FOR_RECHECK,
    GROUP_CODING_REVIEWS_BY_ENTITY,
    IGNORE_CODING_REVIEW,
    RESOLVE_CODING_REVIEW,
    UPDATE_CODING_REVIEW_FIELDS,
    DEACTIVATE_CONTEXT_RULE,
    GET_CONTEXT_RULES,
    UPDATE_ASSERTION_FOR_REVIEW,
    UPDATE_ENTITY_LABEL_FOR_TEXT,
    UPSERT_CODING_IGNORE_RULE,
    UPSERT_CONTEXT_RULE,
    GET_TIER_OVERRIDE_STATS,
)
from services.terminology_api.app.queries.terminology import (
    APPROVE_SURFACE_FORM,
)
from libs.cypher.label_verification_queries import (
    COUNT_VERIFICATION_HISTORY,
    COUNT_VERIFICATION_QUEUE_PENDING,
    DELETE_ALL_VERIFICATION_REVIEWS_FOR_INCLUDED,
    GET_VERIFICATION_HISTORY,
    GET_LABEL_VERIFIER_SCORECARD,
    GET_LABEL_VERIFIER_SCORECARD_BREAKDOWN,
    GET_VERIFICATION_QUEUE,
    GET_VERIFICATION_STATS,
    RESET_TRAINING_LABEL_VERIFICATION_FIELDS,
    RESOLVE_LABEL_VERIFICATION_REVIEW,
)
from libs.cypher.post_processor_rule_queries import (
    GET_POST_PROCESSOR_RULES,
    UPSERT_POST_PROCESSOR_RULE,
    UPDATE_POST_PROCESSOR_RULE_ACTIVE,
)
from libs.llm_client.escalation import escalate_coding
from libs.ner.schema_mapper import LABEL_TO_SNOMED_TAG
from libs.ner.training_label_writer import bulk_upsert_training_labels
from libs.utils.logging import logging_context
from app.services.label_verifier import (
    begin_job,
    begin_job_with_mode,
    get_job_state,
    request_stop_job,
    run_verification,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/training", tags=["training"])


# ---------------------------------------------------------------------------
# Regex safety helper (GAP-016 — ReDoS + injection via user-supplied patterns)
# ---------------------------------------------------------------------------

# Probe strings used by the ReDoS subprocess to trigger catastrophic backtracking.
# - _REDOS_PROBE_LOWER: all-lowercase; fails patterns requiring uppercase (email-style).
# - _REDOS_PROBE_SIMPLE: classic probe for nested-quantifier patterns.
_REDOS_PROBE_LOWER = "a" * 38
_REDOS_PROBE_SIMPLE = "a" * 50 + "b"


def _validate_regex(pattern: str, max_length: int = 200) -> None:
    """Validate a user-supplied regex for safety before persisting.

    Raises HTTPException(422) if:
    - The pattern exceeds max_length characters.
    - The pattern contains a regex syntax error.
    - The pattern exhibits catastrophic backtracking (ReDoS).

    Uses a subprocess for the ReDoS probe so the GIL cannot block the timeout.
    The subprocess is killed at the OS level if it does not complete within 0.5s.
    """
    if len(pattern) > max_length:
        raise HTTPException(
            status_code=422,
            detail=f"context_regex must not exceed {max_length} characters",
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise HTTPException(status_code=422, detail=f"Invalid regex: {exc}") from exc

    probe_code = (
        "import re, sys\n"
        f"compiled = re.compile({pattern!r})\n"
        f"compiled.search({_REDOS_PROBE_LOWER!r})\n"
        f"compiled.search({_REDOS_PROBE_SIMPLE!r})\n"
        "sys.exit(0)\n"
    )
    try:
        subprocess.run(
            [sys.executable, "-c", probe_code],
            timeout=0.5,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        logger.warning("ReDoS probe timed out for regex: %r", pattern[:80])
        raise HTTPException(
            status_code=422,
            detail="context_regex exhibits catastrophic backtracking and is not permitted",
        )


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------


class ExcludeLabelRequest(BaseModel):
    reason: str


class UpdateEntitiesRequest(BaseModel):
    entities: list[dict[str, Any]]


class ResolveVerificationRequest(BaseModel):
    resolved_label: str
    resolved_text: str | None = None
    remove_entity: bool = False
    resolve_only: bool = False
    reviewer: str = "unknown"


class BulkImportRecord(BaseModel):
    encounter_id: str
    patient_id: str
    text: str
    entities: list[dict[str, Any]]
    quality_score: float = 1.0


class BulkImportRequest(BaseModel):
    records: list[BulkImportRecord]
    source: str = "anchor_mining"
    source_ref: str = ""


class PostProcessorRuleRequest(BaseModel):
    action: str  # suppress | rewrite | relabel
    match_text: str | None = None
    match_label: str | None = None
    context_regex: str | None = None
    window_chars: int = 40
    rewrite_text: str | None = None
    rewrite_label: str | None = None
    priority: int = 100
    active: bool = True
    notes: str = ""
    created_by: str = "operations_ui"


class UpdatePostProcessorRuleRequest(BaseModel):
    active: bool


class VerifyAllRequest(BaseModel):
    mode: str = "all"  # all | hitl_only | re_extract
    reset_pending: bool = False


# ------------------------------------------------------------------
# GET /training/labels/stats
# ------------------------------------------------------------------


@router.get("/labels/stats")
def get_label_stats(scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Return corpus statistics: total, included, excluded, broken down by source."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_TRAINING_LABEL_STATS).single()
            stats = dict(row) if row else {}

            # Per-label-type breakdown (only for included labels)
            type_rows = session.run(LABEL_ENTITY_TYPE_BREAKDOWN)
            by_label = {r["label"]: r["n"] for r in type_rows}

        return {
            "total": stats.get("total", 0),
            "included": stats.get("included", 0),
            "excluded": stats.get("excluded", 0),
            "by_source": {
                "hitl_approval": stats.get("hitl", 0),
                "coding_correction": stats.get("coding_correction", 0),
                "anchor_mining": stats.get("anchor_mining", 0),
                "seed": stats.get("seed", 0),
            },
            "by_label_type": by_label,
        }
    finally:
        client.close()


# ------------------------------------------------------------------
# GET /training/labels
# ------------------------------------------------------------------


@router.get("/labels")
def list_labels(
    scope: CallerScope = Depends(get_caller_scope),
    source: Optional[str] = Query(default=None),
    include: Optional[bool] = Query(default=None),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, le=200),
) -> dict[str, Any]:
    """Return a paginated list of training labels with optional filters."""
    skip = (page - 1) * page_size
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                GET_TRAINING_LABELS_PAGE,
                source=source,
                include=include,
                search=search,
                skip=skip,
                limit=page_size,
            )
            labels = [dict(r) for r in rows]

            total_row = session.run(
                COUNT_TRAINING_LABELS_PAGE,
                source=source,
                include=include,
                search=search,
            ).single()
            total = total_row["total"] if total_row else 0

        return {
            "labels": labels,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, -(-total // page_size)),
        }
    finally:
        client.close()


# POST /training/labels/{label_id}/exclude
# ------------------------------------------------------------------


@router.post("/labels/{label_id}/exclude")
def exclude_label(label_id: str, body: ExcludeLabelRequest, scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Mark a training label as excluded (soft delete — preserves the record)."""
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=422, detail="reason must be non-empty")
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(EXCLUDE_TRAINING_LABEL, label_id=label_id, reason=body.reason.strip()).single()
            if not row:
                raise HTTPException(status_code=404, detail=f"Label {label_id!r} not found")
        logger.info("TrainingLabel excluded: %s reason=%r", label_id[:8], body.reason)
        return {"label_id": label_id, "include": False, "excluded_reason": body.reason.strip()}
    finally:
        client.close()


# ------------------------------------------------------------------
# POST /training/labels/{label_id}/include
# ------------------------------------------------------------------


@router.post("/labels/{label_id}/include")
def include_label(label_id: str, scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Re-include a previously excluded training label."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(INCLUDE_TRAINING_LABEL, label_id=label_id).single()
            if not row:
                raise HTTPException(status_code=404, detail=f"Label {label_id!r} not found")
        logger.info("TrainingLabel re-included: %s", label_id[:8])
        return {"label_id": label_id, "include": True}
    finally:
        client.close()


# ------------------------------------------------------------------
# PATCH /training/labels/{label_id}/entities
# ------------------------------------------------------------------

_VALID_ENTITY_LABELS: frozenset[str] = frozenset(
    {
        "disorder", "finding", "procedure", "observable_entity",
        "qualifier_value", "substance", "medicinal_product", "clinical_drug",
        "situation", "event", "body_structure", "tumor_staging",
        "assessment_scale", "staging_scale", "regime_therapy", "record_artifact",
        "physical_object", "organism", "morphologic_abnormality", "occupation",
        "attribute", "environment", "product",
        "X_TEMPORAL", "X_DOSAGE", "X_FREQUENCY", "X_ROUTE",
    }
)


@router.patch("/labels/{label_id}/entities")
def update_label_entities(
    label_id: str,
    body: UpdateEntitiesRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Replace the entities_json of a training label.

    Each entity must carry at minimum ``text`` and ``label``.  ``label`` must
    be one of the canonical NER label types.  ``start`` / ``end`` offsets are
    optional — if omitted they are inferred by substring search or default to 0.
    """
    import json

    validated: list[dict[str, Any]] = []
    for i, ent in enumerate(body.entities):
        label_val = ent.get("label", "")
        if label_val not in _VALID_ENTITY_LABELS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Entity #{i}: label {label_val!r} is not valid. "
                    f"Allowed: {sorted(_VALID_ENTITY_LABELS)}"
                ),
            )
        if not ent.get("text", "").strip():
            raise HTTPException(status_code=422, detail=f"Entity #{i}: text must be non-empty")
        validated.append({
            "text": ent["text"].strip(),
            "label": label_val,
            "start": ent.get("start", 0),
            "end": ent.get("end", 0),
            **({"assertion": ent["assertion"]} if "assertion" in ent else {}),
            **({"confidence": ent["confidence"]} if "confidence" in ent else {}),
        })

    entities_json = json.dumps(validated)
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPDATE_TRAINING_LABEL_ENTITIES,
                label_id=label_id,
                entities_json=entities_json,
            ).single()
            if not row:
                raise HTTPException(status_code=404, detail=f"Label {label_id!r} not found")
        logger.info(
            "TrainingLabel entities updated: %s count=%d", label_id[:8], len(validated)
        )
        return {"label_id": label_id, "entities": validated}
    finally:
        client.close()


# ------------------------------------------------------------------
# POST /training/labels/verify-all
# GET  /training/labels/verify-all/status
# ------------------------------------------------------------------


@router.post("/labels/verify-all")
def verify_all_labels(
    body: VerifyAllRequest | None = None,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Trigger background dual-model verification over included labels."""
    if body is None:
        started = begin_job()
        mode = "all"
        reset_pending = False
    else:
        mode = body.mode if body.mode in {"all", "hitl_only", "re_extract"} else "all"
        reset_pending = bool(body.reset_pending)
        started = begin_job_with_mode(run_mode=mode, reset_pending=reset_pending)

    if not started:
        raise HTTPException(status_code=409, detail="A label verification job is already running")

    if reset_pending:
        client = PatientGraphClient()
        try:
            with client.session() as session:
                session.run(RESET_TRAINING_LABEL_VERIFICATION_FIELDS)
                session.run(DELETE_ALL_VERIFICATION_REVIEWS_FOR_INCLUDED)
        finally:
            client.close()

    thread = threading.Thread(target=run_verification, daemon=True)
    thread.start()
    return {
        "status": "started",
        "mode": mode,
        "reset_pending": reset_pending,
        "message": "Label verification started in background",
    }


@router.post("/labels/verify-all/cancel")
def cancel_verify_all(scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Request graceful cancellation of running label verification job."""
    if not request_stop_job():
        raise HTTPException(status_code=409, detail="No running label verification job to cancel")
    return {"status": "stopping", "message": "Cancellation requested"}


@router.get("/labels/verify-all/status")
def verification_status(scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Return current background verification status plus corpus stats."""
    state = get_job_state()
    client = PatientGraphClient()
    try:
        with client.session() as session:
            stats_row = session.run(GET_VERIFICATION_STATS).single()
            pending_row = session.run(COUNT_VERIFICATION_QUEUE_PENDING).single()
        return {
            **state,
            "auto_resolved": int(state.get("auto_resolved", 0) or 0),
            "stats": dict(stats_row) if stats_row else {
                "total_labels": 0,
                "verified_labels": 0,
                "agreements": 0,
                "disagreements": 0,
                "pending": 0,
            },
            "pending_review": pending_row["pending"] if pending_row else 0,
        }
    finally:
        client.close()


# ------------------------------------------------------------------
# POST /training/labels/agentic-audit
# GET  /training/labels/agentic-audit/status
# POST /training/labels/agentic-audit/cancel
# ------------------------------------------------------------------

from app.services.agentic_audit_service import (  # noqa: E402
    begin_audit_job,
    get_audit_state,
    request_stop_audit,
    run_audit,
)


class AgenticAuditRequest(BaseModel):
    mode: str = "all"          # all | hitl_only
    apply: bool = False        # write safe fixes to Neo4j
    no_agentic: bool = False   # skip pass 2 (tool-use) — cheaper, faster
    limit: int = 0             # 0 = all labels


@router.post("/labels/agentic-audit")
def start_agentic_audit(
    body: AgenticAuditRequest | None = None,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Start a background Agentic Auditor review of training labels.

    Pass 1 reviews every included label for entity quality with auto-fix.
    Pass 2 uses agentic tool-use (Terminology API + second-opinion model)
    to resolve SNOMED ambiguities.  When both models agree, SNOMED fields
    can also be corrected.  Safe auto-fixes are applied if apply=true.
    """
    req = body or AgenticAuditRequest()
    mode = req.mode if req.mode in {"all", "hitl_only"} else "all"

    started = begin_audit_job(
        mode=mode,
        apply=req.apply,
        no_agentic=req.no_agentic,
        limit=req.limit,
    )
    if not started:
        raise HTTPException(status_code=409, detail="An agentic audit job is already running")

    thread = threading.Thread(target=run_audit, daemon=True)
    thread.start()

    return {
        "status": "started",
        "mode": mode,
        "apply": req.apply,
        "no_agentic": req.no_agentic,
        "message": "Agentic audit started in background",
    }


@router.get("/labels/agentic-audit/status")
def agentic_audit_status(scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Return current Agentic Auditor job status and live progress counters."""
    return get_audit_state()


@router.post("/labels/agentic-audit/cancel")
def cancel_agentic_audit(scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Request graceful cancellation of a running Agentic Auditor job."""
    if not request_stop_audit():
        raise HTTPException(status_code=409, detail="No running agentic audit job to cancel")
    return {"status": "stopping", "message": "Cancellation requested"}


# ------------------------------------------------------------------
# GET /training/labels/verification-queue
# POST /training/labels/verification-queue/{review_id}/resolve
# ------------------------------------------------------------------


@router.get("/labels/verification-queue")
def get_verification_queue(
    scope: CallerScope = Depends(get_caller_scope),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, le=500),
) -> dict[str, Any]:
    """Return unresolved label-verification disagreements for human review."""
    skip = (page - 1) * page_size
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_VERIFICATION_QUEUE, skip=skip, limit=page_size)
            reviews = [dict(r) for r in rows]
            pending_row = session.run(COUNT_VERIFICATION_QUEUE_PENDING).single()
            stats_row = session.run(GET_VERIFICATION_STATS).single()
        total = pending_row["pending"] if pending_row else 0
        return {
            "reviews": reviews,
            "total": total,
            "pending": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
            "stats": dict(stats_row) if stats_row else {},
        }
    finally:
        client.close()


@router.get("/labels/verification-history")
def get_verification_history(
    scope: CallerScope = Depends(get_caller_scope),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, le=500),
) -> dict[str, Any]:
    """Return resolved label-verification reviews so users can audit past decisions."""
    skip = (page - 1) * page_size
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_VERIFICATION_HISTORY, skip=skip, limit=page_size)
            reviews = [dict(r) for r in rows]
            total_row = session.run(COUNT_VERIFICATION_HISTORY).single()
        total = int(total_row["total"] if total_row else 0)
        return {
            "reviews": reviews,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }
    finally:
        client.close()


@router.post("/labels/verification-queue/{review_id}/resolve")
def resolve_verification_review(
    review_id: str,
    body: ResolveVerificationRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Resolve a disagreement and write the chosen entity label into TrainingLabel.

    Records which model(s) were correct so per-model accuracy stats can be
    calculated via GET /training/labels/verifier-scorecard.
    """
    if not body.remove_entity and body.resolved_label not in _VALID_ENTITY_LABELS:
        raise HTTPException(
            status_code=422,
            detail=f"resolved_label must be one of {sorted(_VALID_ENTITY_LABELS)}",
        )

    client = PatientGraphClient()
    try:
        with client.session() as session:
            review_row = session.run(
                """
                MATCH (r:LabelVerificationReview {review_id: $review_id})
                WHERE coalesce(r.resolved, false) = false
                RETURN r.label_id       AS label_id,
                       r.entity_index   AS entity_index,
                       r.entity_text    AS entity_text,
                       r.current_label  AS current_label,
                       r.model_a_label  AS model_a_label,
                       r.model_b_label  AS model_b_label
                """,
                review_id=review_id,
            ).single()
            if not review_row:
                raise HTTPException(status_code=404, detail=f"Review {review_id!r} not found")

            label_row = session.run(
                GET_TRAINING_LABEL_BY_ID,
                label_id=review_row["label_id"],
            ).single()
            if not label_row:
                raise HTTPException(status_code=404, detail=f"Label {review_row['label_id']!r} not found")

            if body.resolve_only:
                entities_json = label_row["entities_json"] or "[]"
                model_a_was_correct = review_row["model_a_label"] == body.resolved_label
                model_b_was_correct = review_row["model_b_label"] == body.resolved_label
                result_row = session.run(
                    RESOLVE_LABEL_VERIFICATION_REVIEW,
                    review_id=review_id,
                    resolved_label=body.resolved_label,
                    reviewer=body.reviewer,
                    entities_json=entities_json,
                    model_a_was_correct=model_a_was_correct,
                    model_b_was_correct=model_b_was_correct,
                ).single()
                if not result_row:
                    raise HTTPException(status_code=404, detail=f"Review {review_id!r} not found")
                return {
                    "review_id": result_row["review_id"],
                    "label_id": result_row["label_id"],
                    "resolved_label": result_row["resolved_label"],
                    "model_a_was_correct": result_row["model_a_was_correct"],
                    "model_b_was_correct": result_row["model_b_was_correct"],
                    "resolved_only": True,
                }

            entities = json.loads(label_row["entities_json"] or "[]")
            idx = int(review_row["entity_index"])
            if idx < 0 or idx >= len(entities):
                # Index can drift if another entity was removed first. Fallback by matching
                # review snapshot (entity_text + current_label) against current entities.
                fallback_idx = next(
                    (
                        i
                        for i, ent in enumerate(entities)
                        if str(ent.get("text", "")) == str(review_row.get("entity_text", ""))
                        and str(ent.get("label", "")) == str(review_row.get("current_label", ""))
                    ),
                    -1,
                )
                if fallback_idx == -1:
                    raise HTTPException(status_code=422, detail=f"Invalid entity index {idx} for this label")
                idx = fallback_idx

            if body.remove_entity:
                # Allow UI to target removal of any entity in the record by passing
                # resolved_text (+ optional resolved_label). Falls back to review idx.
                target_text = (body.resolved_text or "").strip()
                target_label = (body.resolved_label or "").strip()
                remove_idx = idx
                if target_text:
                    candidates = [
                        i
                        for i, ent in enumerate(entities)
                        if str(ent.get("text", "")).strip() == target_text
                        and (not target_label or str(ent.get("label", "")) == target_label)
                    ]
                    if candidates:
                        remove_idx = min(candidates, key=lambda i: abs(i - idx))

                entities.pop(remove_idx)
                entities_json = json.dumps(entities)
                if entities:
                    session.run(
                        UPDATE_TRAINING_LABEL_ENTITIES,
                        label_id=review_row["label_id"],
                        entities_json=entities_json,
                    )
                else:
                    session.run(
                        EXCLUDE_TRAINING_LABEL,
                        label_id=review_row["label_id"],
                        reason="No valid entities after verifier HITL span removal",
                    )

                result_row = session.run(
                    RESOLVE_LABEL_VERIFICATION_REVIEW,
                    review_id=review_id,
                    resolved_label="__REMOVED__",
                    reviewer=body.reviewer,
                    entities_json=entities_json,
                    model_a_was_correct=False,
                    model_b_was_correct=False,
                ).single()
                if not result_row:
                    raise HTTPException(status_code=404, detail=f"Review {review_id!r} not found")
                return {
                    "review_id": result_row["review_id"],
                    "label_id": result_row["label_id"],
                    "resolved_label": result_row["resolved_label"],
                    "model_a_was_correct": result_row["model_a_was_correct"],
                    "model_b_was_correct": result_row["model_b_was_correct"],
                    "removed_entity": True,
                    "remaining_entities": len(entities),
                }

            existing_text = str(entities[idx].get("text", ""))
            resolved_text = (body.resolved_text or existing_text).strip()
            if not resolved_text:
                raise HTTPException(status_code=422, detail="resolved_text must be non-empty")

            encounter_text = str(label_row.get("text", ""))
            old_start = int(entities[idx].get("start", 0) or 0)

            # 1) Exact substring (case-sensitive), choosing the closest occurrence
            # to previous offset if the span appears multiple times.
            exact_positions: list[int] = []
            scan_pos = encounter_text.find(resolved_text)
            while scan_pos != -1:
                exact_positions.append(scan_pos)
                scan_pos = encounter_text.find(resolved_text, scan_pos + 1)

            best_start: int | None = None
            if exact_positions:
                best_start = min(exact_positions, key=lambda p: abs(p - old_start))
            else:
                # 2) Case-insensitive fallback.
                hay = encounter_text.lower()
                needle = resolved_text.lower()
                ci_positions: list[int] = []
                scan_pos = hay.find(needle)
                while scan_pos != -1:
                    ci_positions.append(scan_pos)
                    scan_pos = hay.find(needle, scan_pos + 1)
                if ci_positions:
                    best_start = min(ci_positions, key=lambda p: abs(p - old_start))
                else:
                    # 3) Whitespace-normalized + case-insensitive fallback.
                    def _collapse_ws_with_map(s: str) -> tuple[str, list[int]]:
                        chars: list[str] = []
                        idx_map: list[int] = []
                        prev_space = False
                        for i, ch in enumerate(s):
                            if ch.isspace():
                                if prev_space:
                                    continue
                                chars.append(" ")
                                idx_map.append(i)
                                prev_space = True
                            else:
                                chars.append(ch)
                                idx_map.append(i)
                                prev_space = False
                        return "".join(chars), idx_map

                    norm_hay, map_hay = _collapse_ws_with_map(encounter_text)
                    norm_needle = re.sub(r"\s+", " ", resolved_text)
                    norm_pos = norm_hay.lower().find(norm_needle.lower())
                    if norm_pos != -1:
                        best_start = map_hay[norm_pos]

            if best_start is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "resolved_text not found in encounter text; try copying exact text "
                        "from the encounter, including punctuation/spacing."
                    ),
                )

            entities[idx]["label"] = body.resolved_label
            entities[idx]["text"] = resolved_text
            entities[idx]["start"] = best_start
            entities[idx]["end"] = best_start + len(resolved_text)
            entities_json = json.dumps(entities)

            # Determine which model(s) were correct — mirrors classification vote pattern.
            model_a_was_correct = review_row["model_a_label"] == body.resolved_label
            model_b_was_correct = review_row["model_b_label"] == body.resolved_label

            result_row = session.run(
                RESOLVE_LABEL_VERIFICATION_REVIEW,
                review_id=review_id,
                resolved_label=body.resolved_label,
                reviewer=body.reviewer,
                entities_json=entities_json,
                model_a_was_correct=model_a_was_correct,
                model_b_was_correct=model_b_was_correct,
            ).single()
            if not result_row:
                raise HTTPException(status_code=404, detail=f"Review {review_id!r} not found")

        return {
            "review_id": result_row["review_id"],
            "label_id": result_row["label_id"],
            "resolved_label": result_row["resolved_label"],
            "model_a_was_correct": result_row["model_a_was_correct"],
            "model_b_was_correct": result_row["model_b_was_correct"],
        }
    finally:
        client.close()


@router.get("/labels/verifier-scorecard")
def get_verifier_scorecard(scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Per-model accuracy scorecard across all resolved label verification reviews."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_LABEL_VERIFIER_SCORECARD).single()
            breakdown_rows = [dict(r) for r in session.run(GET_LABEL_VERIFIER_SCORECARD_BREAKDOWN)]
        if not row:
            return {"total_resolved": 0}
        data = dict(row)
        total = data.get("total_resolved") or 0
        by_label: dict[str, dict[str, Any]] = {}
        by_resolver: dict[str, dict[str, Any]] = {}
        for r in breakdown_rows:
            label = str(r.get("label") or "__UNKNOWN__")
            resolver = str(r.get("resolved_by") or "human")
            n = int(r.get("n") or 0)
            model_a_correct = int(r.get("model_a_correct") or 0)
            model_b_correct = int(r.get("model_b_correct") or 0)
            label_bucket = by_label.setdefault(label, {"total": 0, "model_a_correct": 0, "model_b_correct": 0})
            label_bucket["total"] += n
            label_bucket["model_a_correct"] += model_a_correct
            label_bucket["model_b_correct"] += model_b_correct
            bucket = by_resolver.setdefault(resolver, {"total": 0, "model_a_correct": 0, "model_b_correct": 0})
            bucket["total"] += n
            bucket["model_a_correct"] += model_a_correct
            bucket["model_b_correct"] += model_b_correct

        label_accuracy = {
            k: {
                "total": v["total"],
                "model_a_accuracy": round(v["model_a_correct"] / v["total"], 4) if v["total"] else None,
                "model_b_accuracy": round(v["model_b_correct"] / v["total"], 4) if v["total"] else None,
            }
            for k, v in by_label.items()
        }
        resolver_accuracy = {
            k: {
                "total": v["total"],
                "model_a_accuracy": round(v["model_a_correct"] / v["total"], 4) if v["total"] else None,
                "model_b_accuracy": round(v["model_b_correct"] / v["total"], 4) if v["total"] else None,
            }
            for k, v in by_resolver.items()
        }
        auto_rows = [v for k, v in by_resolver.items() if k.startswith("auto_triage:")]
        auto_total = sum(v["total"] for v in auto_rows)
        auto_a_correct = sum(v["model_a_correct"] for v in auto_rows)
        auto_b_correct = sum(v["model_b_correct"] for v in auto_rows)
        return {
            **data,
            "model_a_accuracy": round(data["model_a_correct"] / total, 4) if total else None,
            "model_b_accuracy": round(data["model_b_correct"] / total, 4) if total else None,
            "per_label": label_accuracy,
            "by_resolved_by": resolver_accuracy,
            "auto_triage_accuracy": {
                "total": auto_total,
                "model_a_accuracy": round(auto_a_correct / auto_total, 4) if auto_total else None,
                "model_b_accuracy": round(auto_b_correct / auto_total, 4) if auto_total else None,
            },
        }
    finally:
        client.close()


# ------------------------------------------------------------------
# Post-processor rules
# ------------------------------------------------------------------


@router.get("/post-processor-rules")
def list_post_processor_rules(scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """List all persisted post-processor rules."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_POST_PROCESSOR_RULES)
            rules = [dict(r) for r in rows]
        return {"rules": rules, "total": len(rules)}
    finally:
        client.close()


@router.post("/post-processor-rules")
def create_post_processor_rule(
    body: PostProcessorRuleRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Create or update a post-processor rule used by export and runtime pipeline."""
    valid_actions = {"suppress", "rewrite", "relabel"}
    if body.action not in valid_actions:
        raise HTTPException(status_code=422, detail=f"action must be one of {sorted(valid_actions)}")
    if body.context_regex:
        _validate_regex(body.context_regex)
    if body.action in {"rewrite", "relabel"} and not body.rewrite_label:
        raise HTTPException(status_code=422, detail="rewrite_label is required for rewrite/relabel actions")
    if body.action == "rewrite" and not body.rewrite_text:
        raise HTTPException(status_code=422, detail="rewrite_text is required for rewrite action")
    if not body.match_text and not body.match_label and not body.context_regex:
        raise HTTPException(status_code=422, detail="at least one matcher must be provided")

    rule_id = str(uuid.uuid4())
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPSERT_POST_PROCESSOR_RULE,
                rule_id=rule_id,
                active=body.active,
                priority=body.priority,
                action=body.action,
                match_text=body.match_text,
                match_label=body.match_label,
                context_regex=body.context_regex,
                window_chars=body.window_chars,
                rewrite_text=body.rewrite_text,
                rewrite_label=body.rewrite_label,
                created_by=body.created_by,
                notes=body.notes,
            ).single()
        return {"rule_id": row["rule_id"], "status": "created"}
    finally:
        client.close()


@router.patch("/post-processor-rules/{rule_id}")
def update_post_processor_rule(
    rule_id: str,
    body: UpdatePostProcessorRuleRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Toggle active status for an existing post-processor rule."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPDATE_POST_PROCESSOR_RULE_ACTIVE,
                rule_id=rule_id,
                active=body.active,
            ).single()
            if not row:
                raise HTTPException(status_code=404, detail=f"Rule {rule_id!r} not found")
        return {"rule_id": row["rule_id"], "active": row["active"]}
    finally:
        client.close()


# ------------------------------------------------------------------
# GET /training/labels/{label_id}
# ------------------------------------------------------------------


@router.get("/labels/{label_id}")
def get_label(label_id: str, scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Return full detail for a single training label."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_TRAINING_LABEL_BY_ID, label_id=label_id).single()
            if not row:
                raise HTTPException(status_code=404, detail=f"Label {label_id!r} not found")
            return dict(row)
    finally:
        client.close()


# ------------------------------------------------------------------
# POST /training/labels/bulk-import
# ------------------------------------------------------------------


@router.post("/labels/bulk-import")
def bulk_import_labels(body: BulkImportRequest, scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Bulk-upsert training labels from offline scripts (anchor mining, QA).

    Called by ``scripts/qa_all_domains_ner.py`` after a QA pass to ingest
    mined domain entities into Neo4j as TrainingLabel nodes.
    """
    valid_sources = {"anchor_mining", "seed", "hitl_approval", "coding_correction"}
    if body.source not in valid_sources:
        raise HTTPException(
            status_code=422,
            detail=f"source must be one of {sorted(valid_sources)}",
        )
    records = [r.model_dump() for r in body.records]
    label_ids = bulk_upsert_training_labels(
        records,
        source=body.source,
        source_ref=body.source_ref,
    )
    logger.info(
        "bulk-import: %d labels ingested source=%s ref=%s",
        len(label_ids), body.source, body.source_ref,
    )
    return {
        "imported": len(label_ids),
        "source": body.source,
        "label_ids": label_ids[:20],  # truncate for response size
    }


# ------------------------------------------------------------------
# POST /training/export-preview
# ------------------------------------------------------------------


@router.post("/export-preview")
def export_preview(scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Dry-run: count how many labels would be used in the next training run.

    Returns label counts broken down by source and label type so the user
    can verify the corpus before triggering a training job.
    """
    client = PatientGraphClient()
    try:
        with client.session() as session:
            total_row = session.run(COUNT_EXPORTABLE_LABELS).single()
            total = total_row["total"] if total_row else 0

            type_rows = session.run(LABEL_ENTITY_TYPE_BREAKDOWN)
            by_label = {r["label"]: r["n"] for r in type_rows}

        return {
            "exportable_label_count": total,
            "ready_to_train": total >= int(__import__("os").getenv("TRAINING_MIN_LABEL_COUNT", "50")),
            "min_required": int(__import__("os").getenv("TRAINING_MIN_LABEL_COUNT", "50")),
            "by_label_type": by_label,
        }
    finally:
        client.close()


# ------------------------------------------------------------------
# Coding Review endpoints
# ------------------------------------------------------------------


@router.get("/coding-review/queue")
def coding_review_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    entity_text: Optional[str] = Query(default=None),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Paginated queue of entities with missing or low-confidence SNOMED coding.

    When entity_text is provided, returns only records for that specific term
    so callers can inspect all encounter contexts before assigning a code.
    """
    client = PatientGraphClient()
    try:
        with client.session() as session:
            if entity_text:
                rows = session.run(
                    GET_CODING_REVIEW_FOR_ENTITY,
                    entity_text=entity_text,
                )
                items = [dict(r) for r in rows]
                return {
                    "items": items,
                    "page": 1,
                    "page_size": len(items),
                    "total_pages": 1,
                    "pending": len(items),
                    "stats": {},
                }

            skip = (page - 1) * page_size
            rows = session.run(GET_CODING_REVIEW_QUEUE, skip=skip, limit=page_size)
            items = [dict(r) for r in rows]

            pending_row = session.run(COUNT_CODING_REVIEW_PENDING).single()
            pending = pending_row["pending"] if pending_row else 0

            stats_row = session.run(GET_CODING_REVIEW_STATS).single()
            stats = dict(stats_row) if stats_row else {}

        total_pages = max(1, (pending + page_size - 1) // page_size)
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "pending": pending,
            "stats": stats,
        }
    finally:
        client.close()


@router.post("/coding-review/encounter-siblings")
def coding_review_encounter_siblings(
    body: dict[str, Any],
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return all CodingReview nodes for the same TrainingLabels.

    Accepts ``{"label_ids": ["id1", "id2", ...]}``.
    Groups results by label_id so the UI can show what other entities
    share the same encounter text.
    """
    label_ids = body.get("label_ids") or []
    if not label_ids or len(label_ids) > 500:
        return {"siblings": {}}

    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_ENCOUNTER_SIBLINGS, label_ids=label_ids)
            grouped: dict[str, list[dict]] = {}
            for r in rows:
                rec = dict(r)
                lid = rec.pop("label_id")
                grouped.setdefault(lid, []).append(rec)
        return {"siblings": grouped}
    finally:
        client.close()


class CorrectEntityLabelRequest(BaseModel):
    entity_text: str
    entity_label: str
    corrected_by: str = "operations_ui"


@router.patch("/coding-review/entity-label")
def correct_entity_label(
    body: CorrectEntityLabelRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Correct the NER entity label on all pending reviews for a given entity text.

    Called when a reviewer notices the model assigned the wrong semantic type
    (e.g. 'situation' instead of 'finding').  Updates all unresolved
    CodingReview nodes so subsequent searches and recheck runs use the right label.
    """
    if body.entity_label not in _VALID_ENTITY_LABELS:
        raise HTTPException(
            status_code=422,
            detail=f"entity_label must be one of {sorted(_VALID_ENTITY_LABELS)}",
        )
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPDATE_ENTITY_LABEL_FOR_TEXT,
                entity_text=body.entity_text,
                entity_label=body.entity_label,
            ).single()
        updated = row["updated_count"] if row else 0
        logger.info(
            "Entity label corrected: %r -> %r by %s (%d reviews updated)",
            body.entity_text, body.entity_label, body.corrected_by, updated,
        )
        return {
            "entity_text": body.entity_text,
            "entity_label": body.entity_label,
            "updated_count": updated,
        }
    finally:
        client.close()


_VALID_ASSERTIONS = frozenset({
    "present", "absent", "refuted", "possible", "historical", "hypothetical",
    "family", "declined", "cancelled",
})


class CorrectAssertionRequest(BaseModel):
    assertion: str
    corrected_by: str = "operations_ui"


@router.patch("/coding-review/{review_id}/assertion")
def correct_assertion(
    review_id: str,
    body: CorrectAssertionRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Override the ConText assertion for a single CodingReview record.

    Sets assertion_override=true so re-processing never overwrites
    a human correction.
    """
    if body.assertion not in _VALID_ASSERTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"assertion must be one of {sorted(_VALID_ASSERTIONS)}",
        )
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPDATE_ASSERTION_FOR_REVIEW,
                review_id=review_id,
                assertion=body.assertion,
            ).single()
        if not row:
            raise HTTPException(status_code=404, detail=f"Review {review_id!r} not found")
        logger.info(
            "Assertion overridden: review=%s assertion=%r by %s",
            review_id[:12], body.assertion, body.corrected_by,
        )
        return {"review_id": review_id, "assertion": body.assertion}
    finally:
        client.close()


@router.get("/coding-review/grouped")
def coding_review_grouped(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Pending reviews grouped by entity_text.

    Returns one row per unique entity_text with the count of affected reviews,
    the best score, and a sample review_id.  This lets the HITL operator
    resolve an entire root cause (e.g. missing surface form) in one action
    instead of clicking through N identical items.
    """
    client = PatientGraphClient()
    try:
        with client.session() as session:
            skip = (page - 1) * page_size
            rows = session.run(
                GROUP_CODING_REVIEWS_BY_ENTITY,
                skip=skip,
                limit=page_size,
            )
            groups = [dict(r) for r in rows]

            count_row = session.run(COUNT_CODING_REVIEW_GROUPS).single()
            total_groups = count_row["group_count"] if count_row else 0

        total_pages = max(1, (total_groups + page_size - 1) // page_size)
        return {
            "groups": groups,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_groups": total_groups,
        }
    finally:
        client.close()


@router.get("/coding-review/tier-calibration")
def coding_review_tier_calibration(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Override rate per decision tier -- used to calibrate safety layer thresholds.

    Returns the count of resolved items and the override rate (%) for each
    tier so quality leads can monitor whether the Tier 1 auto-code threshold
    is too permissive or the Tier 3 gate is blocking codeable items.
    """
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_TIER_OVERRIDE_STATS)
            stats = [dict(r) for r in rows]
        return {"tiers": stats}
    finally:
        client.close()


class ResolveCodingReviewRequest(BaseModel):
    resolved_concept_id: str
    resolved_term: str
    resolved_entity_text: str | None = None
    reviewer: str = "operations_ui"
    # Assertion to record on the resolved code. "declined", "cancelled", or
    # "refuted" when LEO detected the patient declined/cancelled or an initial
    # impression was overridden by subsequent investigation.
    resolved_assertion: str = "present"


class IgnoreCodingReviewRequest(BaseModel):
    reviewer: str = "operations_ui"
    reason: str = ""


@router.post("/coding-review/{review_id}/resolve")
def resolve_coding_review(
    review_id: str,
    body: ResolveCodingReviewRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Manually assign a SNOMED concept to an uncoded entity.

    Also upserts a SurfaceForm mapping in the knowledge graph so the
    terminology API can resolve this surface form in future.
    """
    from services.api.app.db.neo4j_client import CodingGraphClient
    from services.api.app.models.neo4j_schema import UPSERT_SURFACE_FORM_MAPPING

    client = PatientGraphClient()
    try:
        with client.session() as session:
            # Fetch the entity text before resolving so we can create the surface form.
            cr_row = session.run(
                "MATCH (cr:CodingReview {review_id: $review_id}) "
                "RETURN cr.entity_text AS entity_text",
                review_id=review_id,
            ).single()
            entity_text = str(cr_row["entity_text"]) if cr_row else ""
            resolved_entity_text = (body.resolved_entity_text or "").strip()
            if resolved_entity_text:
                entity_text = resolved_entity_text

            result = session.run(
                RESOLVE_CODING_REVIEW,
                review_id=review_id,
                resolved_concept_id=body.resolved_concept_id,
                resolved_term=body.resolved_term,
                reviewer=body.reviewer,
                resolved_assertion=body.resolved_assertion,
            ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Coding review not found")
    finally:
        client.close()

    if entity_text:
        normalized = re.sub(r"\s+", " ", entity_text.strip().lower())
        try:
            coding_client = CodingGraphClient()
            coding_client.run(
                UPSERT_SURFACE_FORM_MAPPING,
                normalized=normalized,
                form=entity_text.strip(),
                concept_id=body.resolved_concept_id,
                confidence=1.0,
                source="coding_review",
                provenance="coding_review_resolution",
                created_by="coding_review",
            )
            coding_client.close()
            logger.info(
                "Created surface form mapping: %r -> %s (%s)",
                entity_text, body.resolved_concept_id, body.resolved_term,
            )
        except Exception:
            logger.warning(
                "Failed to create surface form mapping for %r", entity_text,
                exc_info=True,
            )

    cascade_count = 0
    if entity_text:
        cascade_client = PatientGraphClient()
        try:
            with cascade_client.session() as session:
                cascade_row = session.run(
                    BATCH_RESOLVE_BY_ENTITY_TEXT,
                    entity_text=entity_text,
                    resolved_concept_id=body.resolved_concept_id,
                    resolved_term=body.resolved_term,
                    reviewer=f"cascade:{body.reviewer}",
                    resolved_assertion=body.resolved_assertion,
                ).single()
                cascade_count = (cascade_row["resolved_count"] if cascade_row else 0)
        except Exception:
            logger.warning(
                "Cascade resolve failed for %r", entity_text, exc_info=True
            )
        finally:
            cascade_client.close()
        if cascade_count:
            logger.info(
                "Cascade-resolved %d additional reviews for %r",
                cascade_count, entity_text,
            )

    return {
        "review_id": result["review_id"],
        "status": "resolved",
        "surface_form_created": bool(entity_text),
        "cascade_resolved": cascade_count,
    }


class BatchResolveCodingReviewRequest(BaseModel):
    entity_text: str
    entity_label: str = ""
    resolved_concept_id: str
    resolved_term: str
    reviewer: str = "operations_ui"
    resolved_assertion: str = "present"


@router.post("/coding-review/batch-resolve")
def batch_resolve_coding_review(
    body: BatchResolveCodingReviewRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Resolve all pending coding reviews for a given entity_text at once.

    Also creates a surface form mapping so the terminology API resolves
    this term in future pipeline runs.
    """
    from services.api.app.db.neo4j_client import CodingGraphClient
    from services.api.app.models.neo4j_schema import UPSERT_SURFACE_FORM_MAPPING

    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                BATCH_RESOLVE_BY_ENTITY_TEXT,
                entity_text=body.entity_text,
                resolved_concept_id=body.resolved_concept_id,
                resolved_term=body.resolved_term,
                reviewer=body.reviewer,
                resolved_assertion=body.resolved_assertion,
            ).single()
            resolved_count = row["resolved_count"] if row else 0
    finally:
        client.close()

    if not resolved_count:
        raise HTTPException(
            status_code=404,
            detail="No pending coding reviews found for this entity text",
        )

    normalized = re.sub(r"\s+", " ", body.entity_text.strip().lower())
    try:
        coding_client = CodingGraphClient()
        coding_client.run(
            UPSERT_SURFACE_FORM_MAPPING,
            normalized=normalized,
            form=body.entity_text.strip(),
            concept_id=body.resolved_concept_id,
            confidence=1.0,
            source="batch_coding_review",
            provenance="batch_coding_review_resolution",
            created_by="batch_coding_review",
        )
        coding_client.close()
    except Exception:
        logger.warning(
            "Failed to create surface form mapping for %r",
            body.entity_text,
            exc_info=True,
        )

    # Suppress this entity_text in future pipeline runs so it is not re-queued
    # even if entity index shifts or a new label is processed.
    _write_coding_ignore_rule(
        entity_text=body.entity_text,
        entity_label=body.entity_label,
        reason=f"resolved via batch coding review -> {body.resolved_concept_id}",
        created_by=body.reviewer,
    )

    return {
        "entity_text": body.entity_text,
        "resolved_count": resolved_count,
        "surface_form_created": True,
    }


class AskLeoRequest(BaseModel):
    entity_text: str
    entity_label: str = ""
    tier: str = "small"
    encounter_text: str = ""


@router.post("/coding-review/ask-leo")
def ask_leo_coding(
    body: AskLeoRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Ask LEO to suggest the best SNOMED concept for a clinical entity.

    Calls the escalation LLM chain starting at the requested tier.
    Encounter text is used to extract measurement units for disambiguation.
    Returns a concept suggestion with confidence and plain-language rationale.
    """
    result = escalate_coding(
        entity_text=body.entity_text,
        entity_label=body.entity_label or "clinical finding",
        encounter_text=body.encounter_text,
        start_tier=body.tier if body.tier in ("small", "big", "max") else "small",
        confidence_threshold=0.70,
    )
    return {
        "concept_term": result.concept_term,
        "confidence": round(result.confidence, 2),
        "rationale": result.rationale,
        "model_tier": result.model_tier,
        "resolved": result.resolved,
    }


class AskLeoRankRequest(BaseModel):
    entity_text: str
    encounter_text: str = ""
    candidates: list[dict[str, Any]]
    tier: str = "small"


@router.post("/coding-review/ask-leo-rank")
def ask_leo_rank_candidates(
    body: AskLeoRankRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Given real SNOMED candidates from a search, ask LEO to pick the best one.

    Called after ask-leo + terminology search when multiple results tie.
    Returns the selected index and a brief reason.
    """
    if not body.candidates:
        return {"selected_index": 0, "reason": ""}

    from libs.llm_client.escalation import _parse_json
    from libs.llm_client.factory import create_llm
    from libs.llm_client.prompt_safety import INJECTION_GUARD, sanitise_for_prompt
    from libs.ner.lab_value_guard import is_lab_result_sentence, should_suppress_disorder

    # Deterministic guard: block diagnostic inference from lab values
    if is_lab_result_sentence(body.encounter_text or ""):
        if should_suppress_disorder(
            entity_text=body.entity_text,
            entity_semantic_tag="disorder",
            entity_normalized=body.entity_text,
            sentence_text=body.encounter_text or "",
        ):
            return {
                "selected_index": 0,
                "reason": (
                    "Lab-value guard: a lab result does not constitute a diagnosis. "
                    "'CKD-EPI' is a formula name, not a diagnosis of CKD."
                ),
            }

    numbered = "\n".join(
        f"{i}. {c.get('term', '')} (SNOMED: {c.get('snomed_concept_id', '')})"
        for i, c in enumerate(body.candidates)
    )
    system = INJECTION_GUARD + (
        "You are a UK primary care SNOMED CT coding specialist.\n"
        "Pick the best concept from the numbered list for the clinical entity "
        "and encounter context.\n\n"
        "CRITICAL RULES:\n"
        "1. Only pick from the numbered list provided. Do not invent or "
        "reference any SNOMED concept IDs -- the list already contains the "
        "verified real codes.\n"
        "2. Clinical subtype matters. For example:\n"
        "   - 'weight loss' without a qualifier should map to the generic term, "
        "not a specific subtype (intentional/unintentional/unexplained) unless "
        "the encounter text clearly indicates which.\n"
        "   - 'no weight loss' or 'weight loss absent' suggests negation; pick "
        "the plain concept (the negation flag is handled separately).\n"
        "3. Use measurement units to disambiguate lab results: g/L -> mass "
        "concentration; mmol/L -> substance concentration.\n"
        "4. UK convention: blood tests are serum-based unless stated otherwise.\n"
        "5. If no candidate clearly fits, pick the closest and set a lower "
        "confidence in your reason.\n"
        "6. Do NOT infer diagnoses from lab values. A lab result (eGFR, HbA1c, "
        "creatinine, sodium, etc.) is an observation, NOT a diagnosis. 'CKD-EPI' "
        "is a formula name, not CKD. If the encounter text is a lab result, pick "
        "the observable entity concept, not a disorder concept.\n"
        "7. This system is a CODING tool. You code what is written, not what is "
        "inferred or recommended.\n\n"
        "Reply ONLY with JSON: "
        '{"selected_index": <int>, "reason": "<one sentence>"}'
    )
    user_msg = json.dumps({
        "entity_text": sanitise_for_prompt(body.entity_text, max_chars=200),
        "encounter_text": sanitise_for_prompt(body.encounter_text, max_chars=16_000),
        "candidates": numbered,
    })
    tier = body.tier if body.tier in ("small", "big", "max") else "small"
    try:
        client = create_llm(provider="aws", tier=tier)
        response = client.converse(
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            temperature=0.0,
            max_tokens=150,
        )
        parsed = _parse_json(response.text)
        idx = int(parsed.get("selected_index", 0))
        reason = str(parsed.get("reason", ""))[:300]
        if not (0 <= idx < len(body.candidates)):
            idx = 0
        return {"selected_index": idx, "reason": reason}
    except Exception:
        logger.warning("ask-leo-rank failed for %r", body.entity_text, exc_info=True)
        return {"selected_index": 0, "reason": ""}


# ---------------------------------------------------------------------------
# Agentic two-pass LEO SNOMED search
# ---------------------------------------------------------------------------

_ASSERTION_NOTES: dict[str, str] = {
    "absent":      "The entity was explicitly negated in this record. Coding is likely inappropriate.",
    "declined":    (
        "The patient declined or refused this. Code the underlying procedure or referral "
        "using its normal SNOMED concept -- do NOT search for 'patient declined [entity]'. "
        "The system will store the code with assertion='declined' on the relationship so "
        "the timeline shows it was offered but not accepted."
    ),
    "cancelled":   (
        "The appointment or procedure was cancelled (by patient or practice). Code the "
        "underlying procedure using its normal SNOMED concept. The system will store the "
        "code with assertion='cancelled' on the relationship."
    ),
    "refuted":     (
        "Initial impression overridden by subsequent investigation. "
        "Code the entity that WAS confirmed using its normal SNOMED concept. "
        "The refuted entity should NOT be coded."
    ),
    "historical":  "This may be a past event, not a current active condition.",
    "hypothetical": "This procedure is planned or awaiting -- it may not have occurred yet.",
    "possible":    "This was uncertain or suspected in the original record.",
    "family":      "This applies to a family member, not the patient directly.",
}


class AskLeoSmartRequest(BaseModel):
    entity_text: str
    encounter_text: str = ""
    initial_candidates: list[dict[str, Any]]
    semantic_tags: list[str] = []
    tier: str = "small"
    assertion: str = "present"


def _terminology_search(
    query: str,
    limit: int,
    semantic_tags: list[str],
) -> list[dict[str, Any]]:
    """Call the Terminology API search endpoint and return candidates."""
    import httpx
    params: dict[str, Any] = {"q": query, "limit": limit}
    if semantic_tags:
        params["semantic_tag"] = semantic_tags
    try:
        with httpx.Client(timeout=10) as http:
            resp = http.get(
                f"{_TERMINOLOGY_URL}/terminology/search",
                params=params,
            )
            resp.raise_for_status()
            return resp.json() or []
    except Exception:
        logger.warning("_terminology_search failed for %r", query, exc_info=True)
        return []


def _pick_candidate(
    candidates: list[dict[str, Any]],
    index: int,
) -> dict[str, Any] | None:
    if not candidates or not (0 <= index < len(candidates)):
        return None
    return candidates[index]


@router.post("/coding-review/ask-leo-smart")
def ask_leo_smart(
    body: AskLeoSmartRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Agentic two-pass SNOMED coding.

    Pass 1: LEO sees the real candidate list and either picks one, requests
    an alternative search query, or declares ambiguous.
    Pass 2 (only if "search"): backend fetches a new candidate list using
    LEO's query, then LEO picks or declares ambiguous.
    Hallucinated SNOMED IDs are structurally impossible as LEO only picks
    from verified terminology search results.
    """
    from libs.llm_client.escalation import escalate_coding_from_candidates
    from libs.ner.lab_value_guard import is_lab_result_sentence, should_suppress_disorder

    # -- Deterministic guard: block diagnostic inference from lab values ------
    if is_lab_result_sentence(body.encounter_text or ""):
        if should_suppress_disorder(
            entity_text=body.entity_text,
            entity_semantic_tag="disorder",
            entity_normalized=body.entity_text,
            sentence_text=body.encounter_text or "",
        ):
            return {
                "matched_candidate": None,
                "reason": (
                    "This encounter text is a lab result line. A lab value "
                    "(e.g. eGFR, HbA1c, creatinine) is an observation, not a "
                    "diagnosis. 'CKD-EPI' is a formula name, not a diagnosis "
                    "of chronic kidney disease. This entity should not be coded "
                    "as a disorder."
                ),
                "is_ambiguous": False,
                "alternative_query_used": None,
                "assertion_warning": (
                    "Lab-value guard: a lab result does not constitute a "
                    "diagnosis. This entity should not be coded as a disorder."
                ),
                "assertion": "present",
            }

    tier = body.tier if body.tier in ("small", "big", "max") else "small"
    assertion_note = _ASSERTION_NOTES.get(body.assertion, "")
    encounter_ctx = (
        f"{body.encounter_text}\n\nContext note: {assertion_note}"
        if assertion_note and body.encounter_text
        else body.encounter_text
    )

    def _smart_response(
        candidate: dict[str, Any] | None,
        reason: str,
        is_ambiguous: bool,
        alternative_query: str | None = None,
        assertion_warning: str | None = None,
        assertion: str = "present",
    ) -> dict[str, Any]:
        return {
            "matched_candidate": candidate,
            "reason": reason,
            "is_ambiguous": is_ambiguous,
            "alternative_query_used": alternative_query,
            "assertion_warning": assertion_warning,
            # "declined", "cancelled", or "refuted" when LEO detected the patient
            # declined/cancelled or an initial impression was overridden.
            "assertion": assertion,
        }

    # -- Pass 1 ---------------------------------------------------------------
    result1 = escalate_coding_from_candidates(
        entity_text=body.entity_text,
        encounter_text=encounter_ctx,
        candidates=body.initial_candidates,
        tier=tier,
    )

    if result1.action == "not_codeable":
        return _smart_response(
            None,
            result1.reason,
            is_ambiguous=False,
            assertion_warning=result1.reason,
        )

    if result1.action == "pick":
        candidate = _pick_candidate(body.initial_candidates, result1.selected_index)
        return _smart_response(
            candidate, result1.reason, is_ambiguous=False, assertion=result1.assertion,
        )

    if result1.action == "ambiguous":
        return _smart_response(None, result1.reason, is_ambiguous=True)

    # -- Pass 2: LEO requested an alternative search --------------------------
    alt_query = result1.alternative_query
    # Carry the assertion hint from pass 1 into pass 2's context note.
    pass2_ctx = encounter_ctx
    if result1.assertion in {"declined", "cancelled", "refuted"}:
        note = _ASSERTION_NOTES.get(result1.assertion, "")
        pass2_ctx = f"{encounter_ctx}\n\nContext note: {note}" if note else encounter_ctx

    new_candidates = _terminology_search(alt_query, 10, body.semantic_tags)
    if not new_candidates:
        return _smart_response(
            None, result1.reason, is_ambiguous=True,
            alternative_query=alt_query, assertion=result1.assertion,
        )

    result2 = escalate_coding_from_candidates(
        entity_text=body.entity_text,
        encounter_text=pass2_ctx,
        candidates=new_candidates,
        tier=tier,
    )

    if result2.action == "not_codeable":
        return _smart_response(
            None,
            result2.reason,
            is_ambiguous=False,
            alternative_query=alt_query,
            assertion_warning=result2.reason,
        )

    if result2.action == "pick":
        candidate = _pick_candidate(new_candidates, result2.selected_index)
        # Prefer the assertion from whichever pass detected the clinical context.
        assertion = result2.assertion if result2.assertion != "present" else result1.assertion
        return _smart_response(
            candidate, result2.reason, is_ambiguous=False,
            alternative_query=alt_query, assertion=assertion,
        )

    assertion = result2.assertion if result2.assertion != "present" else result1.assertion
    return _smart_response(
        None, result2.reason, is_ambiguous=True,
        alternative_query=alt_query, assertion=assertion,
    )


@router.post("/coding-review/{review_id}/ignore")
def ignore_coding_review(
    review_id: str,
    body: IgnoreCodingReviewRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Mark a coding review as ignored and create a persistent ignore rule.

    Future verification runs will skip this term automatically.
    """
    client = PatientGraphClient()
    try:
        with client.session() as session:
            cr_row = session.run(
                "MATCH (cr:CodingReview {review_id: $rid}) "
                "RETURN cr.entity_text AS entity_text, cr.entity_label AS entity_label",
                rid=review_id,
            ).single()
            result = session.run(
                IGNORE_CODING_REVIEW,
                review_id=review_id,
                reviewer=body.reviewer,
            ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Coding review not found")
    finally:
        client.close()

    if cr_row:
        _write_coding_ignore_rule(
            entity_text=str(cr_row["entity_text"] or ""),
            entity_label=str(cr_row["entity_label"] or ""),
            reason=body.reason,
            created_by=body.reviewer,
        )

    return {"review_id": result["review_id"], "status": "ignored"}


def _write_coding_ignore_rule(
    entity_text: str,
    entity_label: str,
    reason: str,
    created_by: str,
) -> None:
    """Upsert a CodingIgnoreRule so the term is suppressed in future runs."""
    normalized = re.sub(r"\s+", " ", entity_text.strip().lower())
    if not normalized:
        return
    rule_id = str(uuid.uuid4())
    client = PatientGraphClient()
    try:
        with client.session() as session:
            session.run(
                UPSERT_CODING_IGNORE_RULE,
                rule_id=rule_id,
                entity_text=normalized,
                entity_label=entity_label or None,
                reason=reason or "ignored via coding review",
                created_by=created_by,
            )
        logger.info("Coding ignore rule created: %r (label=%r)", normalized, entity_label)
    except Exception:
        logger.warning("Failed to write coding ignore rule for %r", normalized, exc_info=True)
    finally:
        client.close()


@router.get("/coding-ignore-rules")
def list_coding_ignore_rules(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """List all coding ignore rules (active and inactive)."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = [dict(r) for r in session.run(GET_ALL_CODING_IGNORE_RULES)]
        return {"rules": rows, "total": len(rows)}
    finally:
        client.close()


@router.delete("/coding-ignore-rules/{rule_id}")
def delete_coding_ignore_rule(
    rule_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Deactivate a coding ignore rule so the term can re-enter review."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            result = session.run(
                DEACTIVATE_CODING_IGNORE_RULE,
                rule_id=rule_id,
            ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Ignore rule not found")
        return {"rule_id": result["rule_id"], "status": "deactivated"}
    finally:
        client.close()


_RECHECK_BATCH_LIMIT = 500
_RECHECK_TERM_CHUNK = int(__import__("os").getenv("RECHECK_TERM_CHUNK", "50"))
_RECHECK_THRESHOLD = float(__import__("os").getenv("CODING_REVIEW_SCORE_THRESHOLD", "0.70"))
_RECHECK_ALT_LOW = float(__import__("os").getenv("CODING_ALT_THRESHOLD_LOW", "0.3"))
_TERMINOLOGY_URL = __import__("os").getenv("TERMINOLOGY_API_URL", "http://localhost:8001").rstrip("/")

# ---------------------------------------------------------------------------
# Recheck job state (module-level, updated by background thread)
# ---------------------------------------------------------------------------
_recheck_lock = threading.Lock()
_recheck_state: dict[str, Any] = {"status": "idle"}


def _get_recheck_state() -> dict[str, Any]:
    with _recheck_lock:
        return dict(_recheck_state)


def _set_recheck_state(**kwargs: Any) -> None:
    with _recheck_lock:
        _recheck_state.update(kwargs)


def _call_terminology_chunk(
    terms: list[str],
    expected_tags: dict[str, str] | None = None,
) -> dict[str, list]:
    """POST a single chunk of terms; return results map or empty dict on failure."""
    import httpx

    body: dict[str, Any] = {"terms": terms}
    if expected_tags:
        chunk_tags = {t: expected_tags[t] for t in terms if t in expected_tags}
        if chunk_tags:
            body["expected_tags"] = chunk_tags
    try:
        with httpx.Client(timeout=60) as http:
            resp = http.post(f"{_TERMINOLOGY_URL}/terminology/resolve", json=body)
            resp.raise_for_status()
            return (resp.json() or {}).get("results") or {}
    except Exception:
        logger.warning("Terminology chunk call failed (%d terms)", len(terms), exc_info=True)
        return {}


def _call_terminology_batch(
    terms: list[str],
    expected_tags: dict[str, str] | None = None,
) -> dict[str, list]:
    """POST terms to the terminology resolve endpoint in chunks to avoid timeouts."""
    merged: dict[str, list] = {}
    for i in range(0, len(terms), _RECHECK_TERM_CHUNK):
        chunk = terms[i: i + _RECHECK_TERM_CHUNK]
        merged.update(_call_terminology_chunk(chunk, expected_tags=expected_tags))
    return merged


def _load_ignore_texts(session) -> frozenset[str]:
    """Return a frozenset of normalised entity texts from active CodingIgnoreRules."""
    return frozenset(
        str(r["entity_text"])
        for r in session.run(GET_CODING_IGNORE_RULES)
        if r.get("entity_text")
    )


def _writeback_recheck_surface_form(
    *,
    entity_text: str,
    concept_id: str,
    resolved_by: str,
) -> bool:
    """Persist an auto-resolved LLM term as a SurfaceForm mapping."""
    if not entity_text.strip() or not concept_id.strip():
        return False
    normalized = re.sub(r"\s+", " ", entity_text.strip().lower())
    if not normalized:
        return False
    try:
        from services.api.app.db.neo4j_client import CodingGraphClient
        from services.api.app.models.neo4j_schema import UPSERT_SURFACE_FORM_MAPPING
    except Exception:
        logger.warning(
            "RECHECK: [WRITEBACK_FAIL] term=%r concept=%r -- import failure",
            entity_text,
            concept_id,
            exc_info=True,
        )
        return False

    coding_client = CodingGraphClient()
    try:
        coding_client.run(
            UPSERT_SURFACE_FORM_MAPPING,
            normalized=normalized,
            form=entity_text.strip(),
            concept_id=concept_id,
            confidence=1.0,
            source="coding_review_recheck",
            provenance="coding_review_recheck_llm_alt",
            created_by="coding_review_recheck",
        )
        logger.info(
            "RECHECK: [WRITEBACK_OK] term=%r -> concept=%r provenance=%s",
            entity_text,
            concept_id,
            "coding_review_recheck_llm_alt",
        )
        return True
    except Exception:
        logger.warning(
            "RECHECK: [WRITEBACK_FAIL] term=%r concept=%r -- upsert failed",
            entity_text,
            concept_id,
            exc_info=True,
        )
        return False
    finally:
        coding_client.close()


def _recheck_suggest_alts(term: str, entity_label: str) -> list[str]:
    """Ask a small LLM for SNOMED-friendly alternative phrasings of a near-miss term.

    The prompt explicitly allows an empty response so the LLM does not hallucinate
    alternatives when none exist.
    """
    import json as _json

    from libs.llm_client.factory import create_llm

    system = (
        "You are a UK primary care clinical terminology assistant. "
        "Your job is to suggest alternative phrasings that would match SNOMED CT concepts. "
        "If the term is too vague, ambiguous, or product-specific to have useful SNOMED "
        "alternatives, you MUST return an empty array []. "
        "Respond ONLY with a valid JSON array of strings -- no explanation, no markdown."
    )
    user = (
        f'Term: "{term}" (type: {entity_label})\n'
        "Suggest up to 3 alternatives: the preferred SNOMED term, a common abbreviation, "
        "and one synonym a UK GP might write. "
        "If you cannot suggest meaningful alternatives, return []. "
        'Output format: ["phrase1", "phrase2"] or []'
    )
    try:
        response = create_llm(tier="small").converse(
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=256,
            temperature=0.2,
        )
        raw_text = response.text.strip()
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if not match:
            logger.info(
                "RECHECK: [LLM_SUGGEST] term=%r label=%s -- no JSON array in response: %s",
                term, entity_label, raw_text[:120],
            )
            return []
        raw = _json.loads(match.group())
        seen = term.strip().lower()
        alts = [s.strip() for s in raw if isinstance(s, str) and s.strip().lower() != seen][:4]
        logger.info("RECHECK: [LLM_SUGGEST] term=%r label=%s -> alts=%r", term, entity_label, alts)
        return alts
    except Exception:
        logger.warning("RECHECK: [LLM_SUGGEST] LLM call failed for term=%r", term, exc_info=True)
        return []


def _recheck_alt_coding(term: str, entity_label: str) -> tuple[dict, str] | None:
    """Try LLM-suggested alternatives for a near-miss term.

    Returns (best_candidate, alt_term_used) if any alternative scores >= threshold,
    else None. Logs all alternatives tried and their scores for audit.
    """
    alt_terms = _recheck_suggest_alts(term, entity_label)
    if not alt_terms:
        logger.info("RECHECK: [LLM_ALT] term=%r label=%s -- LLM returned no alternatives", term, entity_label)
        return None

    results = _call_terminology_batch(alt_terms)
    best: dict | None = None
    best_alt = ""
    best_score = 0.0

    for alt in alt_terms:
        candidates = results.get(alt) or []
        top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        score = float(top.get("score") or 0)
        concept_id = top.get("snomed_concept_id", "")
        snomed_term = top.get("snomed_term", "")
        logger.info(
            "RECHECK: [LLM_ALT_PROBE] original=%r alt=%r -> concept=%r snomed=%r score=%.4f",
            term, alt, concept_id, snomed_term, score,
        )
        if score >= _RECHECK_THRESHOLD and score > best_score:
            best_score = score
            best = top
            best_alt = alt

    if best:
        logger.info(
            "RECHECK: [LLM_ALT_RESOLVED] term=%r via alt=%r -> concept=%r snomed=%r score=%.4f",
            term, best_alt, best.get("snomed_concept_id"), best.get("snomed_term"), best_score,
        )
        return best, best_alt

    logger.info("RECHECK: [LLM_ALT_NO_MATCH] term=%r -- no alternative cleared threshold=%.2f", term, _RECHECK_THRESHOLD)
    return None


def _apply_recheck_item(
    session,
    item: dict,
    results_map: dict,
    ignore_texts: frozenset[str],
    try_alternatives: bool,
) -> tuple[str, bool]:
    """Process one pending review item.

    Returns:
        (outcome, llm_writeback_ok)
    """
    entity_text = item.get("entity_text", "")
    entity_label = item.get("entity_label", "")
    review_id = item.get("review_id", "")
    normalized = re.sub(r"\s+", " ", entity_text.lower())

    if normalized in ignore_texts:
        logger.info(
            "RECHECK: [IGNORED] term=%r label=%s review=%s -- matched ignore rule",
            entity_text, entity_label, review_id,
        )
        session.run(
            AUTO_RESOLVE_CODING_REVIEW,
            review_id=review_id,
            concept_id="__ignored__",
            term="__ignored_by_rule__",
            resolved_by="ignore_rule",
        )
        return "ignored", False

    candidates = results_map.get(entity_text) or []
    top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
    concept_id = str(top.get("snomed_concept_id") or "")
    term = str(top.get("snomed_term") or "")
    score = float(top.get("score") or 0) if top.get("score") is not None else None
    semantic_tag = str(top.get("semantic_tag") or "")
    coded = bool(concept_id)
    resolved_by = "auto_recheck"

    if not coded:
        logger.info(
            "RECHECK: [UNCODED] term=%r label=%s review=%s -- terminology returned no concept",
            entity_text, entity_label, review_id,
        )
    elif score is not None and score >= _RECHECK_THRESHOLD:
        logger.info(
            "RECHECK: [DIRECT] term=%r label=%s -> concept=%r snomed=%r score=%.4f review=%s",
            entity_text, entity_label, concept_id, term, score, review_id,
        )
    elif try_alternatives and score is not None and score >= _RECHECK_ALT_LOW:
        logger.info(
            "RECHECK: [NEAR_MISS] term=%r label=%s score=%.4f -- trying LLM alternatives review=%s",
            entity_text, entity_label, score, review_id,
        )
        alt_result = _recheck_alt_coding(entity_text, entity_label)
        if alt_result:
            best, alt_term = alt_result
            top = best
            concept_id = str(best.get("snomed_concept_id") or "")
            term = str(best.get("snomed_term") or "")
            score = float(best.get("score") or 0)
            semantic_tag = str(best.get("semantic_tag") or "")
            coded = bool(concept_id)
            resolved_by = f"llm_alt:{alt_term[:80]}"
    else:
        logger.info(
            "RECHECK: [LOW_SCORE] term=%r label=%s score=%s -- below alt threshold, staying in queue review=%s",
            entity_text, entity_label, f"{score:.4f}" if score is not None else "None", review_id,
        )

    session.run(
        UPDATE_CODING_REVIEW_FIELDS,
        review_id=review_id,
        coded=coded,
        snomed_concept_id=concept_id if coded else None,
        snomed_term=term if coded else None,
        score=score if coded else None,
        semantic_tag=semantic_tag if coded else None,
    )

    if coded and score is not None and score >= _RECHECK_THRESHOLD:
        session.run(
            AUTO_RESOLVE_CODING_REVIEW,
            review_id=review_id,
            concept_id=concept_id,
            term=term,
            resolved_by=resolved_by,
        )
        # Write surface form for all auto-resolved paths so future pipeline
        # runs hit the Tier-1 fast path instead of re-querying the terminology API.
        writeback_ok = _writeback_recheck_surface_form(
            entity_text=entity_text,
            concept_id=concept_id,
            resolved_by=resolved_by,
        )
        logger.info(
            "RECHECK: [FINALISED] term=%r -> concept=%r snomed=%r score=%.4f"
            " method=%r review=%s writeback=%s",
            entity_text, concept_id, term, score, resolved_by, review_id, writeback_ok,
        )
        if resolved_by.startswith("llm_alt:"):
            return "resolved_llm", writeback_ok
        return "resolved_direct", writeback_ok

    # Last resort: model escalation (small -> big -> max) for unresolved items
    if try_alternatives:
        esc = escalate_coding(
            entity_text=entity_text,
            entity_label=entity_label,
            encounter_text="",
            confidence_threshold=0.85,
            start_tier="big",
        )
        if esc.resolved and esc.concept_id and esc.concept_term:
            resolved_by_esc = f"escalation:{esc.model_tier}"
            logger.info(
                "RECHECK: [ESCALATED] term=%r -> concept=%r tier=%s conf=%.2f review=%s",
                entity_text, esc.concept_id, esc.model_tier, esc.confidence, review_id,
            )
            session.run(
                AUTO_RESOLVE_CODING_REVIEW,
                review_id=review_id,
                concept_id=esc.concept_id,
                term=esc.concept_term,
                resolved_by=resolved_by_esc,
            )
            esc_writeback_ok = _writeback_recheck_surface_form(
                entity_text=entity_text,
                concept_id=esc.concept_id,
                resolved_by=resolved_by_esc,
            )
            return "resolved_llm", esc_writeback_ok

    logger.info(
        "RECHECK: [PENDING] term=%r label=%s -- not resolved, remains in queue review=%s",
        entity_text, entity_label, review_id,
    )
    if not coded:
        return "pending_uncoded", False
    if score is not None and score < _RECHECK_ALT_LOW:
        return "pending_low_score", False
    return "pending_unresolved", False


def _run_recheck_job(
    *,
    job_id: str,
    try_alternatives: bool,
    ignore_texts: frozenset[str],
    item_limit: int = 0,
) -> None:
    """Background worker: process pending coding review items in batches.

    item_limit: max total items to process across all batches (0 = no limit).
    """
    total_rechecked = 0
    total_auto_resolved = 0
    batch_num = 0
    counters: dict[str, int] = {
        "resolved_direct": 0,
        "resolved_llm": 0,
        "ignored_by_rule": 0,
        "pending_uncoded": 0,
        "pending_low_score": 0,
        "pending_unresolved": 0,
        "writeback_llm_success": 0,
        "writeback_llm_failed": 0,
    }

    with logging_context(correlation_id=job_id):
        logger.info(
            "RECHECK: [START] job=%s mode=%s ignore_rules=%d item_limit=%s",
            job_id,
            "llm_assisted" if try_alternatives else "quick",
            len(ignore_texts),
            item_limit if item_limit > 0 else "none",
        )
        try:
            while True:
                client = PatientGraphClient()
                try:
                    with client.session() as session:
                        remaining_budget = (
                            (item_limit - total_rechecked)
                            if item_limit > 0
                            else _RECHECK_BATCH_LIMIT
                        )
                        fetch_limit = min(_RECHECK_BATCH_LIMIT, remaining_budget)
                        rows = session.run(
                            GET_PENDING_FOR_RECHECK, limit=fetch_limit
                        )
                        pending = [dict(r) for r in rows]
                finally:
                    client.close()

                if not pending:
                    break

                batch_num += 1
                unique_terms = list(
                    {r["entity_text"] for r in pending if r.get("entity_text")}
                )
                tag_map: dict[str, str] = {}
                for r in pending:
                    txt = str(r.get("entity_text", ""))
                    if txt and txt not in tag_map:
                        snomed_tag = LABEL_TO_SNOMED_TAG.get(
                            str(r.get("entity_label", ""))
                        )
                        if snomed_tag:
                            tag_map[txt] = snomed_tag
                logger.info(
                    "RECHECK: [BATCH %d] fetched=%d items, unique_terms=%d -- requesting terminology API",
                    batch_num,
                    len(pending),
                    len(unique_terms),
                )

                results_map = _call_terminology_batch(
                    unique_terms, expected_tags=tag_map or None
                )
                logger.info(
                    "RECHECK: [BATCH %d] terminology returned %d results",
                    batch_num,
                    len(results_map),
                )

                batch_resolved = 0
                client = PatientGraphClient()
                try:
                    with client.session() as session:
                        for item in pending:
                            outcome, llm_writeback_ok = _apply_recheck_item(
                                session,
                                item,
                                results_map,
                                ignore_texts,
                                try_alternatives,
                            )
                            if outcome in {"resolved_direct", "resolved_llm", "ignored"}:
                                batch_resolved += 1
                            if outcome == "resolved_direct":
                                counters["resolved_direct"] += 1
                            elif outcome == "resolved_llm":
                                counters["resolved_llm"] += 1
                                if llm_writeback_ok:
                                    counters["writeback_llm_success"] += 1
                                else:
                                    counters["writeback_llm_failed"] += 1
                            elif outcome == "ignored":
                                counters["ignored_by_rule"] += 1
                            elif outcome == "pending_uncoded":
                                counters["pending_uncoded"] += 1
                            elif outcome == "pending_low_score":
                                counters["pending_low_score"] += 1
                            else:
                                counters["pending_unresolved"] += 1
                finally:
                    client.close()

                total_rechecked += len(pending)
                total_auto_resolved += batch_resolved
                _set_recheck_state(
                    rechecked=total_rechecked,
                    auto_resolved=total_auto_resolved,
                    ignored_by_rule=counters["ignored_by_rule"],
                    resolved_llm=counters["resolved_llm"],
                    resolved_direct=counters["resolved_direct"],
                    writeback_llm_success=counters["writeback_llm_success"],
                    writeback_llm_failed=counters["writeback_llm_failed"],
                )
                logger.info(
                    "RECHECK: [BATCH %d DONE] resolved=%d/%d (running total: %d/%d resolved)",
                    batch_num,
                    batch_resolved,
                    len(pending),
                    total_auto_resolved,
                    total_rechecked,
                )

                if item_limit > 0 and total_rechecked >= item_limit:
                    logger.info(
                        "RECHECK: [LIMIT_REACHED] job=%s processed=%d limit=%d -- stopping",
                        job_id, total_rechecked, item_limit,
                    )
                    break

                if len(pending) < _RECHECK_BATCH_LIMIT:
                    break

            report = {
                "processed": total_rechecked,
                "resolved_total": total_auto_resolved,
                "resolved_direct": counters["resolved_direct"],
                "resolved_llm": counters["resolved_llm"],
                "ignored_by_rule": counters["ignored_by_rule"],
                "pending_uncoded": counters["pending_uncoded"],
                "pending_low_score": counters["pending_low_score"],
                "pending_unresolved": counters["pending_unresolved"],
                "writeback_llm_success": counters["writeback_llm_success"],
                "writeback_llm_failed": counters["writeback_llm_failed"],
            }
            _set_recheck_state(
                status="done",
                report=report,
                rechecked=total_rechecked,
                auto_resolved=total_auto_resolved,
                ignored_by_rule=counters["ignored_by_rule"],
                resolved_llm=counters["resolved_llm"],
                resolved_direct=counters["resolved_direct"],
                writeback_llm_success=counters["writeback_llm_success"],
                writeback_llm_failed=counters["writeback_llm_failed"],
            )
            logger.info(
                "RECHECK: [COMPLETE] job=%s batches=%d report=%s",
                job_id,
                batch_num,
                report,
            )

        except Exception as exc:
            logger.exception(
                "RECHECK: [FAILED] job=%s raised an unhandled exception", job_id
            )
            _set_recheck_state(status="failed", last_error=str(exc))


@router.post("/coding-review/recheck")
def recheck_coding_review(
    try_alternatives: bool = False,
    item_limit: int = 0,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Start a background coding review recheck.

    Returns immediately with status 'started'. Poll
    GET /training/coding-review/recheck/status for progress.
    Set try_alternatives=true to enable the LLM alternative-term loop for near-misses.
    Set item_limit > 0 to cap total items processed (useful for testing).
    """
    with _recheck_lock:
        if _recheck_state.get("status") == "running":
            return {"status": "already_running", **_recheck_state}

    client = PatientGraphClient()
    try:
        with client.session() as session:
            ignore_texts = _load_ignore_texts(session)
    finally:
        client.close()

    job_id = str(uuid.uuid4())
    _set_recheck_state(
        job_id=job_id,
        status="running",
        try_alternatives=try_alternatives,
        item_limit=item_limit,
        rechecked=0,
        auto_resolved=0,
        ignored_by_rule=0,
        resolved_llm=0,
        resolved_direct=0,
        writeback_llm_success=0,
        writeback_llm_failed=0,
        report={},
        last_error=None,
    )

    thread = threading.Thread(
        target=_run_recheck_job,
        kwargs={
            "job_id": job_id,
            "try_alternatives": try_alternatives,
            "ignore_texts": ignore_texts,
            "item_limit": item_limit,
        },
        daemon=True,
    )
    thread.start()
    return {
        "status": "started",
        "job_id": job_id,
        "try_alternatives": try_alternatives,
        "item_limit": item_limit,
    }


@router.get("/coding-review/recheck/status")
def recheck_status(scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    """Return the current state of the background coding review recheck job."""
    return _get_recheck_state()


@router.get("/coding-review/stats")
def coding_review_stats(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Summary statistics for coding review."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_CODING_REVIEW_STATS).single()
        return dict(row) if row else {
            "total": 0, "coded": 0, "uncoded": 0,
            "resolved": 0, "pending": 0, "low_confidence": 0,
            "assertion_flagged": 0,
        }
    finally:
        client.close()


@router.get("/coding-review/assertion-queue")
def assertion_review_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Entities with possible/historical/family assertions requiring human review.

    These are not auto-coded -- a reviewer must either confirm the assertion
    and assign a code, change the assertion to present, or suppress the entity.
    Returns the same grouped shape as the coding-review/grouped endpoint so
    ReviewCard can render them without changes.
    """
    client = PatientGraphClient()
    try:
        with client.session() as session:
            skip = (page - 1) * page_size
            rows = session.run(
                GET_ASSERTION_REVIEW_QUEUE,
                skip=skip,
                limit=page_size,
            )
            groups = [dict(r) for r in rows]
            count_row = session.run(COUNT_ASSERTION_REVIEW_GROUPS).single()
            total_groups = count_row["group_count"] if count_row else 0
        total_pages = max(1, (total_groups + page_size - 1) // page_size)
        return {
            "groups": groups,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_groups": total_groups,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Context rules -- user-defined ConText rules stored in Neo4j.
# ---------------------------------------------------------------------------

_VALID_CATEGORIES = frozenset({
    "NEGATED_EXISTENCE", "POSSIBLE_EXISTENCE", "HISTORICAL",
    "HYPOTHETICAL", "FAMILY", "DECLINED",
})
_VALID_DIRECTIONS = frozenset({"FORWARD", "BACKWARD", "BIDIRECTIONAL"})


class ContextRuleRequest(BaseModel):
    literal: str
    category: str
    direction: str = "FORWARD"
    max_scope: int = 6
    description: str = ""
    example: str = ""
    created_by: str = "operations_ui"


@router.get("/context-rules")
def list_context_rules(
    active_only: bool = True,
    include_builtin: bool = True,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """List ConText rules: user-defined (Neo4j) plus optionally the shipped built-ins.

    Custom rules are scoped to the caller's org; platform admins see all orgs.
    Built-in rules (source='builtin') are read-only and global.
    """
    from libs.ner.context_engine import get_builtin_rules

    org_id = None if scope.is_admin else scope.primary_org_id

    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_CONTEXT_RULES, active_only=active_only, org_id=org_id)
            custom = [{**dict(r), "source": "custom"} for r in rows]
    finally:
        client.close()

    builtin = get_builtin_rules() if include_builtin else []
    return {"rules": builtin + custom}


@router.post("/context-rules")
def create_context_rule(
    body: ContextRuleRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Create a new user-defined ConText rule, scoped to the caller's org.

    The rule is picked up by the coding worker on the next pipeline restart.
    Only platform admins may create rules (GAP-015).
    """
    if not body.literal.strip():
        raise HTTPException(status_code=422, detail="literal must not be empty")
    if len(body.literal) > 200:
        raise HTTPException(status_code=422, detail="literal must not exceed 200 characters")
    if body.category not in _VALID_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"category must be one of {sorted(_VALID_CATEGORIES)}",
        )
    if body.direction.upper() not in _VALID_DIRECTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"direction must be one of {sorted(_VALID_DIRECTIONS)}",
        )
    rule_id = str(uuid.uuid4())
    org_id = scope.primary_org_id  # None for platform admins (platform-wide rule)
    client = PatientGraphClient()
    try:
        with client.session() as session:
            session.run(
                UPSERT_CONTEXT_RULE,
                rule_id=rule_id,
                literal=body.literal.strip().lower(),
                category=body.category.upper(),
                direction=body.direction.upper(),
                max_scope=max(1, min(20, body.max_scope)),
                description=body.description.strip(),
                example=body.example.strip(),
                created_by=scope.email,
                org_id=org_id,
            )
        logger.info(
            "ContextRule created: %s %r -> %s by %s (org=%s)",
            rule_id[:8], body.literal, body.category, scope.email, org_id,
        )
        return {"rule_id": rule_id, "literal": body.literal, "category": body.category, "org_id": org_id}
    finally:
        client.close()


@router.patch("/context-rules/{rule_id}/deactivate")
def deactivate_context_rule(
    rule_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Soft-delete a user-defined ConText rule."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(DEACTIVATE_CONTEXT_RULE, rule_id=rule_id).single()
        if not row:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id!r} not found")
        logger.info("ContextRule deactivated: %s", rule_id[:8])
        return {"rule_id": rule_id, "active": False}
    finally:
        client.close()


# -- Surface form approval --------------------------------------------------


@router.patch("/surface-forms/{normalized}/approve")
def approve_surface_form(
    normalized: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Promote a pending surface form to approved after second confirmation.

    Surface forms are created as 'pending' on first writeback. This endpoint
    confirms the mapping so the resolver treats it as a trusted Tier 1 match.
    """
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                APPROVE_SURFACE_FORM,
                normalized=normalized,
                approved_by=scope.user_id or "reviewer",
            ).single()
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No pending surface form found for {normalized!r}",
            )
        logger.info("SurfaceForm approved: %s", normalized[:40])
        return {"normalized": row["normalized"], "status": row["status"]}
    finally:
        client.close()
