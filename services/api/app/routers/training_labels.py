"""TrainingLabel store router -- inspect, include, and exclude NER training labels.

Atlas trace:
  DO: DO-236545C8
  Also implements: DO-2D2CE052, DO-54397CCD, DO-6CD07544, DO-94D87FA7, DO-A35D2D57, DO-B88D4941, DO-BA2B7A99
  DI: DI-2D9F5064, DI-37B3DC71, DI-3EA60D5A, DI-54D00E21, DI-6EFD68D0, DI-A0579B64, DI-AF5A1668, DI-D2D0117E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

Extracted from services/api/app/routers/training.py (2026-07 CTO peer-review
item 2: core-api router decomposition). Pure move, no behaviour change --
existing DO/DI trace headers carried over unchanged.

Routes: label stats/list/get, exclude/include, entity updates, verify-all + verification queue/history, verifier scorecard, bulk-import, export-preview.

Depends on app.routers._training_common for _VALID_ENTITY_LABELS and UpdateEntitiesRequest (shared with coding_review / training_gold_labels).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from libs.auth.org_scope import (
    CallerScope,
    get_caller_scope,
)
from libs.auth.service_auth import get_service_auth_header
from libs.neo4j_client.client import PatientGraphClient
from libs.cypher.training_label_queries import (
    COUNT_EXPORTABLE_LABELS,
    COUNT_TRAINING_LABELS_PAGE,
    EXCLUDE_TRAINING_LABEL,
    GET_TRAINING_LABEL_BY_ID,
    GET_TRAINING_LABEL_STATS,
    GET_TRAINING_LABELS_PAGE,
    INCLUDE_TRAINING_LABEL,
    LABEL_ENTITY_TYPE_BREAKDOWN,
    UPDATE_TRAINING_LABEL_ENTITIES,
)
from libs.cypher.label_verification_queries import (
    COUNT_VERIFICATION_HISTORY,
    COUNT_VERIFICATION_QUEUE_PENDING,
    GET_VERIFICATION_HISTORY,
    GET_LABEL_VERIFIER_SCORECARD,
    GET_LABEL_VERIFIER_SCORECARD_BREAKDOWN,
    GET_VERIFICATION_QUEUE,
    GET_VERIFICATION_STATS,
    RESOLVE_LABEL_VERIFICATION_REVIEW,
)
from libs.ner.training_label_writer import bulk_upsert_training_labels
from app.routers._training_common import (
    _VALID_ENTITY_LABELS,
    UpdateEntitiesRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


PIPELINE_WORKER_BASE = os.getenv("PIPELINE_WORKER_URL", "http://localhost:8006").rstrip(
    "/"
)


async def _proxy_pipeline_worker_json(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{PIPELINE_WORKER_BASE}{path}"
    headers = {**get_service_auth_header()}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.request(method, url, json=json_body, headers=headers)

    if resp.status_code >= 400:
        detail: Any
        try:
            payload = resp.json()
            detail = payload.get("detail", payload)
        except ValueError:
            detail = resp.text or f"Pipeline worker error ({resp.status_code})"
        raise HTTPException(status_code=resp.status_code, detail=detail)

    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail="Pipeline worker returned invalid JSON"
        ) from exc


class ExcludeLabelRequest(BaseModel):
    reason: str


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


class VerifyAllRequest(BaseModel):
    mode: str = "all"  # all | hitl_only | re_extract
    reset_pending: bool = False


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


@router.post("/labels/{label_id}/exclude")
def exclude_label(
    label_id: str,
    body: ExcludeLabelRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Mark a training label as excluded (soft delete — preserves the record)."""
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=422, detail="reason must be non-empty")
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                EXCLUDE_TRAINING_LABEL, label_id=label_id, reason=body.reason.strip()
            ).single()
            if not row:
                raise HTTPException(
                    status_code=404, detail=f"Label {label_id!r} not found"
                )
        logger.info("TrainingLabel excluded: %s reason=%r", label_id[:8], body.reason)
        return {
            "label_id": label_id,
            "include": False,
            "excluded_reason": body.reason.strip(),
        }
    finally:
        client.close()


@router.post("/labels/{label_id}/include")
def include_label(
    label_id: str, scope: CallerScope = Depends(get_caller_scope)
) -> dict[str, Any]:
    """Re-include a previously excluded training label."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(INCLUDE_TRAINING_LABEL, label_id=label_id).single()
            if not row:
                raise HTTPException(
                    status_code=404, detail=f"Label {label_id!r} not found"
                )
        logger.info("TrainingLabel re-included: %s", label_id[:8])
        return {"label_id": label_id, "include": True}
    finally:
        client.close()


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
            raise HTTPException(
                status_code=422, detail=f"Entity #{i}: text must be non-empty"
            )
        validated.append(
            {
                "text": ent["text"].strip(),
                "label": label_val,
                "start": ent.get("start", 0),
                "end": ent.get("end", 0),
                **({"assertion": ent["assertion"]} if "assertion" in ent else {}),
                **({"confidence": ent["confidence"]} if "confidence" in ent else {}),
            }
        )

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
                raise HTTPException(
                    status_code=404, detail=f"Label {label_id!r} not found"
                )
        logger.info(
            "TrainingLabel entities updated: %s count=%d", label_id[:8], len(validated)
        )
        return {"label_id": label_id, "entities": validated}
    finally:
        client.close()


@router.post("/labels/verify-all")
async def verify_all_labels(
    body: VerifyAllRequest | None = None,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Trigger background dual-model verification over included labels."""
    _ = scope
    payload = (
        {"mode": "all", "reset_pending": False} if body is None else body.model_dump()
    )
    return await _proxy_pipeline_worker_json(
        "POST", "/label-verify/start", json_body=payload
    )


@router.post("/labels/verify-all/cancel")
async def cancel_verify_all(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Request graceful cancellation of running label verification job."""
    _ = scope
    return await _proxy_pipeline_worker_json("POST", "/label-verify/stop")


@router.get("/labels/verify-all/status")
async def verification_status(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return current background verification status plus corpus stats."""
    _ = scope
    return await _proxy_pipeline_worker_json("GET", "/label-verify/status")


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
                raise HTTPException(
                    status_code=404, detail=f"Review {review_id!r} not found"
                )

            label_row = session.run(
                GET_TRAINING_LABEL_BY_ID,
                label_id=review_row["label_id"],
            ).single()
            if not label_row:
                raise HTTPException(
                    status_code=404,
                    detail=f"Label {review_row['label_id']!r} not found",
                )

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
                    raise HTTPException(
                        status_code=404, detail=f"Review {review_id!r} not found"
                    )
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
                        if str(ent.get("text", ""))
                        == str(review_row.get("entity_text", ""))
                        and str(ent.get("label", ""))
                        == str(review_row.get("current_label", ""))
                    ),
                    -1,
                )
                if fallback_idx == -1:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Invalid entity index {idx} for this label",
                    )
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
                        and (
                            not target_label
                            or str(ent.get("label", "")) == target_label
                        )
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
                    raise HTTPException(
                        status_code=404, detail=f"Review {review_id!r} not found"
                    )
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
                raise HTTPException(
                    status_code=422, detail="resolved_text must be non-empty"
                )

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
                raise HTTPException(
                    status_code=404, detail=f"Review {review_id!r} not found"
                )

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
def get_verifier_scorecard(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Per-model accuracy scorecard across all resolved label verification reviews."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_LABEL_VERIFIER_SCORECARD).single()
            breakdown_rows = [
                dict(r) for r in session.run(GET_LABEL_VERIFIER_SCORECARD_BREAKDOWN)
            ]
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
            label_bucket = by_label.setdefault(
                label, {"total": 0, "model_a_correct": 0, "model_b_correct": 0}
            )
            label_bucket["total"] += n
            label_bucket["model_a_correct"] += model_a_correct
            label_bucket["model_b_correct"] += model_b_correct
            bucket = by_resolver.setdefault(
                resolver, {"total": 0, "model_a_correct": 0, "model_b_correct": 0}
            )
            bucket["total"] += n
            bucket["model_a_correct"] += model_a_correct
            bucket["model_b_correct"] += model_b_correct

        label_accuracy = {
            k: {
                "total": v["total"],
                "model_a_accuracy": (
                    round(v["model_a_correct"] / v["total"], 4) if v["total"] else None
                ),
                "model_b_accuracy": (
                    round(v["model_b_correct"] / v["total"], 4) if v["total"] else None
                ),
            }
            for k, v in by_label.items()
        }
        resolver_accuracy = {
            k: {
                "total": v["total"],
                "model_a_accuracy": (
                    round(v["model_a_correct"] / v["total"], 4) if v["total"] else None
                ),
                "model_b_accuracy": (
                    round(v["model_b_correct"] / v["total"], 4) if v["total"] else None
                ),
            }
            for k, v in by_resolver.items()
        }
        auto_rows = [v for k, v in by_resolver.items() if k.startswith("auto_triage:")]
        auto_total = sum(v["total"] for v in auto_rows)
        auto_a_correct = sum(v["model_a_correct"] for v in auto_rows)
        auto_b_correct = sum(v["model_b_correct"] for v in auto_rows)
        return {
            **data,
            "model_a_accuracy": (
                round(data["model_a_correct"] / total, 4) if total else None
            ),
            "model_b_accuracy": (
                round(data["model_b_correct"] / total, 4) if total else None
            ),
            "per_label": label_accuracy,
            "by_resolved_by": resolver_accuracy,
            "auto_triage_accuracy": {
                "total": auto_total,
                "model_a_accuracy": (
                    round(auto_a_correct / auto_total, 4) if auto_total else None
                ),
                "model_b_accuracy": (
                    round(auto_b_correct / auto_total, 4) if auto_total else None
                ),
            },
        }
    finally:
        client.close()


@router.get("/labels/{label_id}")
def get_label(
    label_id: str, scope: CallerScope = Depends(get_caller_scope)
) -> dict[str, Any]:
    """Return full detail for a single training label."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_TRAINING_LABEL_BY_ID, label_id=label_id).single()
            if not row:
                raise HTTPException(
                    status_code=404, detail=f"Label {label_id!r} not found"
                )
            return dict(row)
    finally:
        client.close()


@router.post("/labels/bulk-import")
def bulk_import_labels(
    body: BulkImportRequest, scope: CallerScope = Depends(get_caller_scope)
) -> dict[str, Any]:
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
        len(label_ids),
        body.source,
        body.source_ref,
    )
    return {
        "imported": len(label_ids),
        "source": body.source,
        "label_ids": label_ids[:20],  # truncate for response size
    }


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
            "ready_to_train": total
            >= int(__import__("os").getenv("TRAINING_MIN_LABEL_COUNT", "50")),
            "min_required": int(
                __import__("os").getenv("TRAINING_MIN_LABEL_COUNT", "50")
            ),
            "by_label_type": by_label,
        }
    finally:
        client.close()
