"""Terminology search and writeback endpoints against coding graph."""

from __future__ import annotations

from typing import Any

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.db.neo4j_client import CodingGraphClient, PatientGraphClient
from app.models.neo4j_schema import (
    TERMINOLOGY_SEARCH,
    TERMINOLOGY_SEARCH_FILTERED,
    DESCENDANTS_TEMPLATE,
    LIST_SURFACE_FORMS,
    COUNT_SURFACE_FORMS,
    GROUPED_SURFACE_FORMS,
    COUNT_GROUPED_SURFACE_FORMS,
    GET_CONCEPT_FOR_SUGGESTION,
    DELETE_SURFACE_FORM,
    DELETE_SURFACE_FORM_MAPPING,
    KEEP_SURFACE_FORM_MAPPING,
    UPSERT_SURFACE_FORM_MAPPING,
    DEDUPLICATE_SURFACE_FORM_RELS,
    AUDIT_SURFACE_FORM_DUPLICATES,
)
from app.services.terminology_writeback_service import writeback_approved_terms


router = APIRouter(prefix="/terminology", tags=["terminology"])

SNOMED_SEMANTIC_TAGS = [
    "body structure",
    "clinical drug",
    "disorder",
    "environment",
    "ethnic group",
    "event",
    "finding",
    "medicinal product",
    "morphologic abnormality",
    "observable entity",
    "occupation",
    "organism",
    "person",
    "physical object",
    "procedure",
    "qualifier value",
    "record artifact",
    "regime/therapy",
    "situation",
    "social concept",
    "specimen",
    "staging scale",
    "substance",
    "tumor staging",
]


@router.get("/semantic-tags")
def list_semantic_tags():
    """Return the fixed set of clinically relevant SNOMED CT semantic tags."""
    return SNOMED_SEMANTIC_TAGS


@router.get("/search")
def search_terms(
    q: str = Query(min_length=1),
    limit: int = Query(default=15, ge=1, le=50),
    semantic_tag: list[str] | None = Query(default=None),
):
    """Fulltext search across SNOMED terms, optionally filtered by semantic tags."""
    client = CodingGraphClient()
    try:
        if semantic_tag:
            return client.run(
                TERMINOLOGY_SEARCH_FILTERED, q=q, limit=limit, tags=semantic_tag
            )
        return client.run(TERMINOLOGY_SEARCH, q=q, limit=limit)
    finally:
        client.close()


class WritebackRequest(BaseModel):
    patient_id: str | None = None


class WritebackResponse(BaseModel):
    candidates_scanned: int
    terms_scanned: int
    surface_forms_written: int
    skipped_no_concept: int


@router.post("/writeback", response_model=WritebackResponse)
def trigger_writeback(body: WritebackRequest | None = None):
    """Write approved surface-form -> SNOMED mappings from patient graph into coding graph SurfaceForm nodes."""
    patient_client = PatientGraphClient()
    coding_client = CodingGraphClient()
    try:
        with patient_client.session() as patient_session, coding_client.session() as coding_session:
            result = writeback_approved_terms(
                patient_session=patient_session,
                coding_session=coding_session,
                patient_id=body.patient_id if body else None,
            )
        return WritebackResponse(**result)
    finally:
        patient_client.close()
        coding_client.close()


@router.get("/surface-forms")
def list_surface_forms(
    q: Optional[str] = Query(default=None, description="Filter by form text"),
    concept_id: Optional[str] = Query(default=None, description="Filter by SNOMED concept ID"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List surface forms with their mapped SNOMED concepts."""
    client = CodingGraphClient()
    try:
        rows = client.run(
            LIST_SURFACE_FORMS,
            q=q,
            concept_id=concept_id,
            offset=offset,
            limit=limit,
        )
        count_rows = client.run(
            COUNT_SURFACE_FORMS,
            q=q,
            concept_id=concept_id,
        )
        total = count_rows[0]["total"] if count_rows else 0
        return {"items": rows, "total": total, "offset": offset, "limit": limit}
    finally:
        client.close()


class UpsertMappingRequest(BaseModel):
    normalized: str
    form: str
    concept_id: str
    confidence: float = 1.0
    source: str = "manual"
    provenance: str = "manual_correction"
    created_by: str = "manual_mapping"


@router.post("/surface-forms/upsert-mapping")
def upsert_surface_form_mapping(body: UpsertMappingRequest):
    """Add or correct a MAPS_TO relationship. Creates the SurfaceForm node if it doesn't exist."""
    client = CodingGraphClient()
    try:
        rows = client.run(
            UPSERT_SURFACE_FORM_MAPPING,
            normalized=body.normalized,
            form=body.form,
            concept_id=body.concept_id,
            confidence=body.confidence,
            source=body.source,
            provenance=body.provenance,
            created_by=body.created_by,
        )
        if not rows:
            from fastapi import HTTPException
            raise HTTPException(404, f"Concept {body.concept_id} not found")
        return rows[0]
    finally:
        client.close()


@router.get("/surface-forms/grouped")
def list_grouped_surface_forms(
    q: Optional[str] = Query(default=None, description="Filter by surface form text or concept name"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return surface forms grouped by SNOMED concept."""
    client = CodingGraphClient()
    try:
        rows = client.run(GROUPED_SURFACE_FORMS, q=q, offset=offset, limit=limit)
        count_rows = client.run(COUNT_GROUPED_SURFACE_FORMS, q=q)
        total = count_rows[0]["total"] if count_rows else 0
        return {"items": rows, "total": total, "offset": offset, "limit": limit}
    finally:
        client.close()


@router.delete("/surface-forms/{normalized:path}")
def delete_surface_form(
    normalized: str,
    concept_id: Optional[str] = Query(default=None),
    keep_concept_id: Optional[str] = Query(default=None),
):
    """Delete a surface form or one of its mappings.

    No params         → delete the SurfaceForm node entirely.
    ?concept_id=X     → delete only the MAPS_TO relationship to concept X.
    ?keep_concept_id=X → delete all MAPS_TO relationships except to concept X.
    """
    client = CodingGraphClient()
    try:
        if concept_id:
            rows = client.run(DELETE_SURFACE_FORM_MAPPING, normalized=normalized, concept_id=concept_id)
            removed = rows[0]["removed"] if rows else 0
            return {"normalized": normalized, "concept_id": concept_id, "removed": removed}
        if keep_concept_id:
            rows = client.run(KEEP_SURFACE_FORM_MAPPING, normalized=normalized, keep_concept_id=keep_concept_id)
            removed = rows[0]["removed"] if rows else 0
            return {"normalized": normalized, "kept_concept_id": keep_concept_id, "removed": removed}
        client.run(DELETE_SURFACE_FORM, normalized=normalized)
        return {"deleted": normalized}
    finally:
        client.close()


@router.get("/surface-forms/duplicates")
def audit_surface_form_duplicates():
    """Return surface forms that have more than one MAPS_TO relationship (same or different concepts)."""
    client = CodingGraphClient()
    try:
        return client.run(AUDIT_SURFACE_FORM_DUPLICATES)
    finally:
        client.close()


@router.post("/surface-forms/deduplicate")
def deduplicate_surface_forms():
    """Remove duplicate MAPS_TO relationships, keeping the highest-confidence mapping per surface form."""
    client = CodingGraphClient()
    try:
        rows = client.run(DEDUPLICATE_SURFACE_FORM_RELS)
        removed = rows[0]["duplicates_removed"] if rows else 0
        return {"duplicates_removed": removed}
    finally:
        client.close()


@router.get("/concepts/{concept_id}/descendants")
def get_descendants(
    concept_id: str,
    depth: int = Query(default=3, ge=1, le=5),
    limit: int = Query(default=300, ge=1, le=500),
    semantic_tag: Optional[str] = Query(default=None),
):
    """Return active SNOMED descendants of a concept via IS_A relationships."""
    query = DESCENDANTS_TEMPLATE.format(depth=int(depth))
    client = CodingGraphClient()
    try:
        return client.run(query, concept_id=concept_id, semantic_tag=semantic_tag, limit=limit)
    finally:
        client.close()


@router.post("/concepts/{concept_id}/suggest-aliases")
def suggest_aliases_for_concept(concept_id: str):
    """Use a small LLM (Claude Haiku via Bedrock) to suggest additional surface form aliases."""
    import json
    import re

    from libs.llm_client.factory import create_llm

    coding_client = CodingGraphClient()
    try:
        rows = coding_client.run(GET_CONCEPT_FOR_SUGGESTION, concept_id=concept_id)
    finally:
        coding_client.close()

    if not rows:
        from fastapi import HTTPException
        raise HTTPException(404, f"Concept {concept_id} not found or inactive")

    row = rows[0]
    concept_fsn: str = row["concept_fsn"]
    semantic_tag: str = row.get("semantic_tag") or "clinical finding"
    existing: list[str] = row.get("existing_aliases") or []
    existing_lower = {e.lower() for e in existing}

    existing_list = (
        ", ".join(f'"{e}"' for e in existing) if existing else "none yet"
    )

    system_prompt = (
        "You are a UK primary care clinical terminology assistant. "
        "You suggest short text strings that UK GPs write in free-text consultation notes. "
        "Focus on NHS-specific abbreviations, clinical shorthand, and common spelling variants. "
        "Respond ONLY with a valid JSON array of strings — no explanation, no markdown fences."
    )
    user_prompt = (
        f'Concept: "{concept_fsn}" (SNOMED {concept_id}, type: {semantic_tag})\n'
        f"Existing aliases: {existing_list}\n\n"
        "Suggest up to 10 additional short phrases (1–6 words each) a UK GP might write "
        "in a free-text consultation note to mean this concept. "
        "Include abbreviations, misspellings, acronyms, and NHS shorthand. "
        "Do NOT repeat the existing aliases.\n"
        'Output format: ["alias1", "alias2", ...]'
    )

    try:
        llm = create_llm(tier="small")
        response = llm.converse(
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=512,
            temperature=0.3,
        )
        text = response.text.strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return {"suggestions": [], "concept_id": concept_id}
        raw = json.loads(match.group())
        suggestions = [
            s.strip()
            for s in raw
            if isinstance(s, str) and s.strip() and s.strip().lower() not in existing_lower
        ]
        return {"suggestions": suggestions[:10], "concept_id": concept_id}
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("suggest-aliases LLM error: %s", exc)
        return {"suggestions": [], "concept_id": concept_id}
