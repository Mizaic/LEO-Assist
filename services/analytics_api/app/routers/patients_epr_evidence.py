"""Evidence provenance endpoints for coded problem-list entries.

Lets a clinician check a problem-list chip against source text: every
dated mention of the concept -- from an encounter, a document/chunk, or
a communication thread -- and (on request) the evidence sentence and
assertion recorded for one of those mentions.

Atlas trace:
  DO: DO-5D3EA371
  DI: DI-7DE8E8ED
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient

from .patients_epr_evidence_queries import (
    GET_CONCEPT_MENTION_DETAIL_ADMIN,
    GET_CONCEPT_MENTION_DETAIL_SCOPED,
    GET_CONCEPT_MENTIONS_ADMIN,
    GET_CONCEPT_MENTIONS_SCOPED,
)

router = APIRouter()

_VALID_SOURCE_TYPES = {"encounter", "document", "communication"}


class ConceptMention(BaseModel):
    source_id: str
    source_type: str
    source_date: Optional[str] = None
    assertion: Optional[str] = None
    confidence: Optional[float] = None
    value: Optional[str] = None
    unit: Optional[str] = None
    observed_at: Optional[str] = None


class ConceptMentionDetail(BaseModel):
    source_id: str
    source_type: str
    source_date: Optional[str] = None
    concept_id: str
    name: Optional[str] = None
    read_code: Optional[str] = None
    assertion: Optional[str] = None
    confidence: Optional[float] = None
    evidence: Optional[str] = None
    evidence_sentence: Optional[str] = None
    value: Optional[str] = None
    unit: Optional[str] = None
    observed_at: Optional[str] = None


def _cypher_params(scope: CallerScope, patient_id: str, **extra: Any) -> dict[str, Any]:
    params: dict[str, Any] = {"patient_id": patient_id, **extra}
    if not scope.is_admin:
        params["scope_org_ids"] = scope.org_ids
    return params


def _pick_query(scope: CallerScope, admin_q: str, scoped_q: str) -> str:
    return admin_q if scope.is_admin else scoped_q


def _assertion_from_context(context_json: Optional[str]) -> Optional[str]:
    """Extract the assertion string from the :DOCUMENTS r.context JSON blob."""
    if not context_json:
        return None
    try:
        return json.loads(context_json).get("assertion")
    except (TypeError, ValueError):
        return None


def _date_only(raw: Optional[str]) -> Optional[str]:
    return raw[:10] if raw else None


def _optional_str(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


@router.get(
    "/patients/{patient_id}/coded-entities/{concept_id}/mentions",
    response_model=list[ConceptMention],
)
def get_concept_mentions(
    patient_id: str,
    concept_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> list[ConceptMention]:
    """Dated mentions for one coded concept (no sentence text).

    Walks all three :DOCUMENTS source types (encounter, document/chunk,
    communication) -- see patients_epr_evidence_queries.py. Deliberately
    lightweight so opening a problem-list chip stays fast; the evidence
    sentence for a given mention is fetched separately, only when the
    clinician expands that mention.
    """
    query = _pick_query(scope, GET_CONCEPT_MENTIONS_ADMIN, GET_CONCEPT_MENTIONS_SCOPED)
    params = _cypher_params(scope, patient_id, concept_id=concept_id)
    client = PatientGraphClient()
    try:
        rows = client.run(query, **params)
    finally:
        client.close()
    return [
        ConceptMention(
            source_id=r["source_id"],
            source_type=r["source_type"],
            source_date=_date_only(r.get("source_date")),
            assertion=_assertion_from_context(r.get("context_json")),
            confidence=(
                float(r["confidence"]) if r.get("confidence") is not None else None
            ),
            value=_optional_str(r.get("value")),
            unit=_optional_str(r.get("unit")),
            observed_at=_date_only(_optional_str(r.get("observed_at"))),
        )
        for r in rows
        if r.get("source_id")
    ]


@router.get(
    "/patients/{patient_id}/coded-entities/{concept_id}/mentions/{source_type}/{source_id}",
    response_model=ConceptMentionDetail,
)
def get_concept_mention_detail(
    patient_id: str,
    concept_id: str,
    source_type: str,
    source_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> ConceptMentionDetail:
    """Full evidence sentence and assertion for one dated mention."""
    if source_type not in _VALID_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"source_type must be one of {sorted(_VALID_SOURCE_TYPES)}.",
        )
    query = _pick_query(
        scope, GET_CONCEPT_MENTION_DETAIL_ADMIN, GET_CONCEPT_MENTION_DETAIL_SCOPED
    )
    params = _cypher_params(
        scope,
        patient_id,
        concept_id=concept_id,
        source_type=source_type,
        source_id=source_id,
    )
    client = PatientGraphClient()
    try:
        rows = client.run(query, **params)
    finally:
        client.close()
    if not rows:
        raise HTTPException(status_code=404, detail="Mention not found.")
    r = rows[0]
    return ConceptMentionDetail(
        source_id=r.get("source_id", source_id),
        source_type=r.get("source_type", source_type),
        source_date=_date_only(r.get("source_date")),
        concept_id=concept_id,
        name=r.get("name"),
        read_code=r.get("read_code"),
        assertion=_assertion_from_context(r.get("context_json")),
        confidence=(
            float(r["confidence"]) if r.get("confidence") is not None else None
        ),
        evidence=r.get("evidence"),
        evidence_sentence=r.get("evidence_sentence"),
        value=_optional_str(r.get("value")),
        unit=_optional_str(r.get("unit")),
        observed_at=_date_only(_optional_str(r.get("observed_at"))),
    )
