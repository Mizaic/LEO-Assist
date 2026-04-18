"""Patient Finder endpoints (DI-LEO-AI-230).

Backs the PatientFinder primitive used by the SBAR playground (and any
future surface that wants to pick a patient + their encounters /
documents) without forcing a reviewer to remember Neo4j ids.

Endpoints:
    GET  /patient-finder/search                    typeahead
    GET  /patient-finder/by-filter                 ad-hoc CohortFilter
    GET  /patient-finder/by-cohort/{cohort_id}     saved cohort listing
    GET  /patient-finder/{patient_id}/encounters
    GET  /patient-finder/{patient_id}/document-references
    GET  /document-references/{id}/chunks

Every endpoint respects the caller's CallerScope.org_ids; platform
admins bypass org gating.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient

from services.analytics_api.app.routers.cohorts import (
    CohortFilter,
    _build_where_clauses,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class PatientSummary(BaseModel):
    """Compact patient row shown in PatientFinder result lists.

    NHS number and date of birth are MANDATORY (R-LEO-AI-NEW). Both are
    rendered on every search-result row so a reviewer can confirm the
    correct patient even when names collide.
    """

    id: str
    display_name: Optional[str] = None
    nhs_number: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    registered_org_id: Optional[str] = None


class PatientSearchResponse(BaseModel):
    results: List[PatientSummary]
    total: int


class EncounterSummary(BaseModel):
    """Summary of an encounter shown in the SBAR record picker.

    ``text`` is a short snippet of the encounter narrative so the
    picker's free-text search can match against it client-side. The
    snippet is bounded to keep the payload light when a patient has
    hundreds of encounters; the full text is fetched on demand by
    Mission Control.
    """

    id: str
    date: Optional[str] = None
    encounter_type: Optional[str] = None
    top_concept: Optional[str] = None
    coded_count: int = 0
    text: Optional[str] = None


class DocumentReferenceSummary(BaseModel):
    """Summary of a DocumentReference shown in the SBAR record picker.

    ``text`` is a short snippet (first chunk text or the document
    description) so the picker's free-text search can match against
    document content the same way the Mission Control encounter feed
    matches against encounter narrative. Bounded to 240 chars so the
    payload stays small for patients with hundreds of letters.
    """

    id: str
    date: Optional[str] = None
    document_type: Optional[str] = None
    source: Optional[str] = None
    chunk_count: int = 0
    text: Optional[str] = None


class ChunkSummary(BaseModel):
    id: str
    ordinal: int
    preview: str


# ---------------------------------------------------------------------------
# Org gating helpers
# ---------------------------------------------------------------------------


def _scope_clause(scope: CallerScope) -> tuple[str, Dict[str, Any]]:
    """Return (where_fragment, params) restricting Patient `p` to scope.

    Platform admin -> empty fragment ("true").
    """
    if scope.is_admin or not scope.org_ids:
        return "true", {}
    return (
        "EXISTS { "
        "  MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(_gp) "
        "  WHERE _gp.id IN $scope_org_ids "
        "}",
        {"scope_org_ids": scope.org_ids},
    )


def _check_patient_in_scope(
    client: PatientGraphClient, patient_id: str, scope: CallerScope
) -> None:
    """Raise 404 if the patient is not visible to the caller.

    404 (not 403) so we do not leak the existence of out-of-scope
    patients.
    """
    if scope.is_admin:
        rows = client.run(
            "MATCH (p:Patient) WHERE toString(p.id) = $pid RETURN p.id AS id",
            pid=patient_id,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Patient not found")
        return
    rows = client.run(
        "MATCH (p:Patient) WHERE toString(p.id) = $pid "
        "AND EXISTS { MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(_gp) "
        "             WHERE _gp.id IN $scope_org_ids } "
        "RETURN p.id AS id",
        pid=patient_id,
        scope_org_ids=scope.org_ids,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Patient not found")


def _row_to_patient_summary(row: dict) -> PatientSummary:
    return PatientSummary(
        id=str(row.get("id") or ""),
        display_name=row.get("display_name") or None,
        nhs_number=row.get("nhs_number") or None,
        dob=row.get("dob") or None,
        gender=row.get("gender") or None,
        registered_org_id=row.get("gp_id") or None,
    )


_PATIENT_RETURN = (
    "RETURN toString(p.id)            AS id, "
    "       coalesce(p.name, '')      AS display_name, "
    "       coalesce(p.nhs_number, '') AS nhs_number, "
    "       toString(coalesce(p.birthDate, p.dob, '')) AS dob, "
    "       coalesce(p.gender, p.sex, '') AS gender, "
    "       head([(p)-[:HAS_GENERAL_PRACTITIONER]->(_g) | _g.id]) AS gp_id "
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/patient-finder/search", response_model=PatientSearchResponse)
def search_patients(
    q: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(20, ge=1, le=100),
    scope: CallerScope = Depends(get_caller_scope),
):
    """Typeahead by name | NHS number | date of birth | local id.

    Matches case-insensitively and tolerates partial NHS numbers (digits
    only, ignoring spaces). Always returns NHS number + DOB so the row
    can be safely confirmed in the UI.
    """
    needle = q.strip()
    if not needle:
        return PatientSearchResponse(results=[], total=0)
    digits = "".join(ch for ch in needle if ch.isdigit())
    scope_where, scope_params = _scope_clause(scope)

    client = PatientGraphClient()
    try:
        # Three-arm match: name CONTAINS, nhs_number CONTAINS digits,
        # id CONTAINS digits, dob STARTS WITH (YYYY or YYYY-MM).
        cypher = (
            "MATCH (p:Patient) "
            f"WHERE {scope_where} AND ("
            "  toLower(coalesce(p.name, '')) CONTAINS toLower($needle) "
            "  OR ($digits <> '' AND replace(coalesce(p.nhs_number, ''), ' ', '') "
            "       CONTAINS $digits) "
            "  OR ($digits <> '' AND toString(p.id) CONTAINS $digits) "
            "  OR toString(coalesce(p.birthDate, p.dob, '')) STARTS WITH $needle "
            ") "
            f"{_PATIENT_RETURN} "
            "ORDER BY display_name, id "
            "LIMIT $limit"
        )
        rows = client.run(
            cypher,
            needle=needle,
            digits=digits,
            limit=limit,
            **scope_params,
        )
        results = [_row_to_patient_summary(r) for r in rows]
        return PatientSearchResponse(results=results, total=len(results))
    finally:
        client.close()


@router.get("/patient-finder/by-filter", response_model=PatientSearchResponse)
def patients_by_filter(
    filters: str = Query(
        ...,
        description=(
            "URL-encoded JSON CohortFilter. Sent as a query string so the "
            "endpoint stays cacheable and bookmarkable."
        ),
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10000),
    scope: CallerScope = Depends(get_caller_scope),
):
    """Resolve an ad-hoc CohortFilter and return Patient summaries.

    Does NOT persist a Cohort node -- use POST /cohorts to save.
    """
    try:
        payload = json.loads(filters)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422, detail=f"filters must be valid JSON: {exc}"
        )
    try:
        cohort_filter = CohortFilter(**payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    where_clause, params = _build_where_clauses(cohort_filter)
    scope_where, scope_params = _scope_clause(scope)
    params.update(scope_params)
    params["limit"] = limit
    params["offset"] = offset

    client = PatientGraphClient()
    try:
        count_rows = client.run(
            f"MATCH (p:Patient) WHERE {where_clause} AND {scope_where} "
            f"RETURN count(p) AS cnt",
            **params,
        )
        total = int(count_rows[0]["cnt"]) if count_rows else 0
        page_rows = client.run(
            f"MATCH (p:Patient) WHERE {where_clause} AND {scope_where} "
            f"{_PATIENT_RETURN} ORDER BY id SKIP $offset LIMIT $limit",
            **params,
        )
        results = [_row_to_patient_summary(r) for r in page_rows]
        return PatientSearchResponse(results=results, total=total)
    finally:
        client.close()


@router.get(
    "/patient-finder/by-cohort/{cohort_id}",
    response_model=PatientSearchResponse,
)
def patients_by_cohort(
    cohort_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10000),
    scope: CallerScope = Depends(get_caller_scope),
):
    """List Patient summaries belonging to a saved Cohort, paged."""
    client = PatientGraphClient()
    try:
        rows = client.run(
            "MATCH (c:Cohort {cohort_id: $cid}) "
            "RETURN c.filters AS filters, "
            "       coalesce(c.source, 'user') AS source, "
            "       c.created_by_org_id AS created_by_org_id",
            cid=cohort_id,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Cohort not found")
        is_preset = rows[0].get("source") == "nhs_preset"
        owner_org = rows[0].get("created_by_org_id")
        if (
            not scope.is_admin
            and not is_preset
            and owner_org
            and owner_org not in scope.org_ids
        ):
            raise HTTPException(status_code=404, detail="Cohort not found")

        filters_raw = rows[0].get("filters", "{}")
        try:
            filters_dict = (
                json.loads(filters_raw)
                if isinstance(filters_raw, str)
                else filters_raw
            )
        except (json.JSONDecodeError, TypeError):
            filters_dict = {}
        cohort_filter = CohortFilter(**filters_dict)

        where_clause, params = _build_where_clauses(cohort_filter)
        scope_where, scope_params = _scope_clause(scope)
        params.update(scope_params)
        params["limit"] = limit
        params["offset"] = offset

        count_rows = client.run(
            f"MATCH (p:Patient) WHERE {where_clause} AND {scope_where} "
            f"RETURN count(p) AS cnt",
            **params,
        )
        total = int(count_rows[0]["cnt"]) if count_rows else 0
        page_rows = client.run(
            f"MATCH (p:Patient) WHERE {where_clause} AND {scope_where} "
            f"{_PATIENT_RETURN} ORDER BY id SKIP $offset LIMIT $limit",
            **params,
        )
        results = [_row_to_patient_summary(r) for r in page_rows]
        return PatientSearchResponse(results=results, total=total)
    finally:
        client.close()


@router.get(
    "/patient-finder/{patient_id}/encounters",
    response_model=List[EncounterSummary],
)
def list_patient_encounters(
    patient_id: str,
    limit: int = Query(100, ge=1, le=500),
    scope: CallerScope = Depends(get_caller_scope),
):
    """Chronological encounter list for a patient.

    Each row carries the top SNOMED display term (most-frequent code on
    that encounter) so a reviewer can recognise an encounter without
    opening it.
    """
    client = PatientGraphClient()
    try:
        _check_patient_in_scope(client, patient_id, scope)
        rows = client.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "OPTIONAL MATCH (e)-[r:DOCUMENTS]->(c) "
            "WITH e, count(r) AS coded_count, "
            "     head([x IN collect(c.name) WHERE x IS NOT NULL]) AS top_concept "
            "RETURN toString(e.id)        AS id, "
            "       toString(e.date)      AS date, "
            "       coalesce(e.encounter_type, e.classification_type, '') "
            "                             AS encounter_type, "
            "       coalesce(top_concept, '') AS top_concept, "
            "       coded_count           AS coded_count, "
            "       coalesce(e.text, '')  AS text "
            "ORDER BY e.date DESC "
            "LIMIT $limit",
            pid=patient_id,
            limit=limit,
        )
        out: List[EncounterSummary] = []
        for r in rows:
            text = (r.get("text") or "").strip()
            snippet = text[:240] + ("..." if len(text) > 240 else "") if text else None
            out.append(
                EncounterSummary(
                    id=str(r["id"]),
                    date=r.get("date") or None,
                    encounter_type=r.get("encounter_type") or None,
                    top_concept=r.get("top_concept") or None,
                    coded_count=int(r.get("coded_count") or 0),
                    text=snippet,
                )
            )
        return out
    finally:
        client.close()


@router.get(
    "/patient-finder/{patient_id}/document-references",
    response_model=List[DocumentReferenceSummary],
)
def list_patient_document_references(
    patient_id: str,
    limit: int = Query(100, ge=1, le=500),
    scope: CallerScope = Depends(get_caller_scope),
):
    """List DocumentReference summaries for a patient with chunk counts."""
    client = PatientGraphClient()
    try:
        _check_patient_in_scope(client, patient_id, scope)
        # We pull the first chunk's text as a search snippet. The
        # ordering relies on r.ordinal where present, falling back to
        # 0 so unordered chunks still produce a deterministic pick.
        rows = client.run(
            "MATCH (p:Patient)-[:HAS_DOCUMENT_REFERENCE]->(dr:DocumentReference) "
            "WHERE toString(p.id) = $pid "
            "OPTIONAL MATCH (dr)-[hr:HAS_CHUNK]->(c:Chunk) "
            "WITH dr, hr, c "
            "ORDER BY coalesce(hr.ordinal, 0) ASC "
            "WITH dr, "
            "     count(c) AS chunk_count, "
            "     head(collect(c.text)) AS first_chunk_text "
            "RETURN toString(dr.id)        AS id, "
            "       toString(coalesce(dr.date, dr.created_at, '')) AS date, "
            "       coalesce(dr.type, dr.category, dr.document_type, '') "
            "                              AS document_type, "
            "       coalesce(dr.source, '') AS source, "
            "       chunk_count            AS chunk_count, "
            "       coalesce(first_chunk_text, dr.description, dr.title, '') "
            "                              AS text "
            "ORDER BY date DESC "
            "LIMIT $limit",
            pid=patient_id,
            limit=limit,
        )
        out: List[DocumentReferenceSummary] = []
        for r in rows:
            text = (r.get("text") or "").strip()
            snippet = text[:240] + ("..." if len(text) > 240 else "") if text else None
            out.append(
                DocumentReferenceSummary(
                    id=str(r["id"]),
                    date=r.get("date") or None,
                    document_type=r.get("document_type") or None,
                    source=r.get("source") or None,
                    chunk_count=int(r.get("chunk_count") or 0),
                    text=snippet,
                )
            )
        return out
    finally:
        client.close()


@router.get(
    "/document-references/{document_reference_id}/chunks",
    response_model=List[ChunkSummary],
)
def list_document_reference_chunks(
    document_reference_id: str,
    limit: int = Query(500, ge=1, le=2000),
    scope: CallerScope = Depends(get_caller_scope),
):
    """Ordered chunks under a DocumentReference, with text preview.

    The document is gated: an admin sees any DR; non-admins must reach
    the parent patient via HAS_GENERAL_PRACTITIONER.
    """
    client = PatientGraphClient()
    try:
        if scope.is_admin:
            scope_where = "true"
            scope_params: Dict[str, Any] = {}
        else:
            scope_where = (
                "EXISTS { "
                "  MATCH (dr)<-[:HAS_DOCUMENT_REFERENCE]-(_p:Patient) "
                "        -[:HAS_GENERAL_PRACTITIONER]->(_gp) "
                "  WHERE _gp.id IN $scope_org_ids "
                "}"
            )
            scope_params = {"scope_org_ids": scope.org_ids}

        rows = client.run(
            "MATCH (dr:DocumentReference {id: $drid}) "
            f"WHERE {scope_where} "
            "OPTIONAL MATCH (dr)-[r:HAS_CHUNK]->(c:Chunk) "
            "WITH c, r ORDER BY coalesce(r.ordinal, 0) ASC "
            "RETURN toString(c.id)              AS id, "
            "       coalesce(r.ordinal, 0)      AS ordinal, "
            "       coalesce(c.text, '')        AS text "
            "LIMIT $limit",
            drid=document_reference_id,
            limit=limit,
            **scope_params,
        )
        out: List[ChunkSummary] = []
        for r in rows:
            chunk_id = r.get("id")
            if not chunk_id:
                continue
            text = (r.get("text") or "").strip()
            preview = text[:80] + ("..." if len(text) > 80 else "")
            out.append(
                ChunkSummary(
                    id=str(chunk_id),
                    ordinal=int(r.get("ordinal") or 0),
                    preview=preview,
                )
            )
        return out
    finally:
        client.close()
