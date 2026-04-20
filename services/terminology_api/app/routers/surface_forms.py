"""Surface-form CRUD endpoints for the terminology API.

Atlas trace:
  DO: DO-0F8F8E02
  DI: DI-5EECDA58
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0F8F8E02")

Provides browsing, editing, and auditing of SurfaceForm→Concept mappings
stored in the Knowledge Graph.  These are consumed by the UI's
Settings → Surface Forms page.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from libs.auth.service_auth import verify_service_token
from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.terminology import (
    AUDIT_SURFACE_FORM_DUPLICATES,
    COUNT_GROUPED_SURFACE_FORMS,
    COUNT_SURFACE_FORMS,
    DEDUPLICATE_SURFACE_FORM_RELS,
    DELETE_SURFACE_FORM,
    DELETE_SURFACE_FORM_MAPPING,
    GROUPED_SURFACE_FORMS,
    KEEP_SURFACE_FORM_MAPPING,
    LIST_SURFACE_FORMS,
    UPSERT_SURFACE_FORM_MAPPING,
)

router = APIRouter()


# ── List (flat) ───────────────────────────────────────────────────────────────


@router.get("/surface-forms")
def list_surface_forms(
    q: Optional[str] = Query(
        default=None, description="Filter by form text or concept name"
    ),
    concept_id: Optional[str] = Query(
        default=None, description="Filter by SNOMED concept ID"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Paginated list of surface forms with their mapped SNOMED concepts."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            LIST_SURFACE_FORMS, q=q, concept_id=concept_id, offset=offset, limit=limit
        )
        count_rows = client.run(COUNT_SURFACE_FORMS, q=q, concept_id=concept_id)
        total = count_rows[0]["total"] if count_rows else 0
        return {"items": rows, "total": total, "offset": offset, "limit": limit}
    finally:
        client.close()


# ── List (grouped by concept) ─────────────────────────────────────────────────


@router.get("/surface-forms/grouped")
def list_grouped_surface_forms(
    q: Optional[str] = Query(
        default=None,
        description="Filter by surface form text, concept name, SNOMED ID, or Read code",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return surface forms grouped by SNOMED concept, with pagination."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(GROUPED_SURFACE_FORMS, q=q, offset=offset, limit=limit)
        count_rows = client.run(COUNT_GROUPED_SURFACE_FORMS, q=q)
        total = count_rows[0]["total"] if count_rows else 0
        return {"items": rows, "total": total, "offset": offset, "limit": limit}
    finally:
        client.close()


# ── Duplicate audit ───────────────────────────────────────────────────────────


@router.get("/surface-forms/duplicates")
def audit_surface_form_duplicates():
    """Return surface forms that have more than one MAPS_TO relationship."""
    client = KnowledgeGraphClient()
    try:
        return client.run(AUDIT_SURFACE_FORM_DUPLICATES)
    finally:
        client.close()


# ── Auto-deduplicate ──────────────────────────────────────────────────────────


@router.post("/surface-forms/deduplicate")
def deduplicate_surface_forms(_: None = Depends(verify_service_token)):
    """Remove duplicate MAPS_TO relationships, keeping the highest-confidence mapping per surface form."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(DEDUPLICATE_SURFACE_FORM_RELS)
        removed = rows[0]["duplicates_removed"] if rows else 0
        return {"duplicates_removed": removed}
    finally:
        client.close()


# ── Upsert mapping ────────────────────────────────────────────────────────────


class UpsertMappingRequest(BaseModel):
    normalized: str
    form: str
    concept_id: str
    confidence: float = 1.0
    source: str = "manual"
    provenance: str = "manual_correction"


@router.post("/surface-forms/upsert-mapping")
def upsert_surface_form_mapping(
    body: UpsertMappingRequest, _: None = Depends(verify_service_token)
):
    """Add or correct a MAPS_TO relationship. Creates the SurfaceForm node if it does not exist."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            UPSERT_SURFACE_FORM_MAPPING,
            normalized=body.normalized,
            form=body.form,
            concept_id=body.concept_id,
            confidence=body.confidence,
            source=body.source,
            provenance=body.provenance,
        )
        if not rows:
            raise HTTPException(
                status_code=404, detail=f"Concept {body.concept_id} not found"
            )
        return rows[0]
    finally:
        client.close()


# ── Delete (node or mapping) ──────────────────────────────────────────────────


@router.delete("/surface-forms/{normalized:path}")
def delete_surface_form(
    normalized: str,
    concept_id: Optional[str] = Query(default=None),
    keep_concept_id: Optional[str] = Query(default=None),
    _: None = Depends(verify_service_token),
):
    """Delete a surface form or one of its mappings.

    No params          → detach-delete the entire SurfaceForm node.
    ?concept_id=X      → remove only the MAPS_TO relationship to concept X.
    ?keep_concept_id=X → remove all MAPS_TO relationships except to concept X.
    """
    client = KnowledgeGraphClient()
    try:
        if concept_id:
            rows = client.run(
                DELETE_SURFACE_FORM_MAPPING,
                normalized=normalized,
                concept_id=concept_id,
            )
            removed = rows[0]["removed"] if rows else 0
            return {
                "normalized": normalized,
                "concept_id": concept_id,
                "removed": removed,
            }
        if keep_concept_id:
            rows = client.run(
                KEEP_SURFACE_FORM_MAPPING,
                normalized=normalized,
                keep_concept_id=keep_concept_id,
            )
            removed = rows[0]["removed"] if rows else 0
            return {
                "normalized": normalized,
                "kept_concept_id": keep_concept_id,
                "removed": removed,
            }
        client.run(DELETE_SURFACE_FORM, normalized=normalized)
        return {"deleted": normalized}
    finally:
        client.close()
