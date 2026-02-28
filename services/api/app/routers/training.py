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

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient
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
)
from libs.ner.training_label_writer import bulk_upsert_training_labels

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/training", tags=["training"])


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------


class ExcludeLabelRequest(BaseModel):
    reason: str


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
