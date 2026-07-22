"""Evidence provenance endpoints for coded problem-list entries.

Lets a clinician check a problem-list chip against source text: every
dated encounter mention of the concept, and (on request) the evidence
sentence and assertion recorded for one of those mentions.

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


class ConceptMention(BaseModel):
    encounter_id: str
    encounter_date: Optional[str] = None
    assertion: Optional[str] = None
    confidence: Optional[float] = None


class ConceptMentionDetail(BaseModel):
    encounter_id: str
    encounter_date: Optional[str] = None
    concept_id: str
    name: Optional[str] = None
    read_code: Optional[str] = None
    assertion: Optional[str] = None
    confidence: Optional[float] = None
    evidence: Optional[str] = None
    evidence_sentence: Optional[str] = None


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


@router.get(
    "/patients/{patient_id}/coded-entities/{concept_id}/mentions",
    response_model=list[ConceptMention],
)
def get_concept_mentions(
    patient_id: str,
    concept_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> list[ConceptMention]:
    """Dated encounter mentions for one coded concept (no sentence text).

    Deliberately lightweight so opening a problem-list chip stays fast;
    the evidence sentence for a given date is fetched separately, only
    when the clinician expands that date.
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
            encounter_id=r["encounter_id"],
            encounter_date=_date_only(r.get("encounter_date")),
            assertion=_assertion_from_context(r.get("context_json")),
            confidence=(
                float(r["confidence"]) if r.get("confidence") is not None else None
            ),
        )
        for r in rows
        if r.get("encounter_id")
    ]


@router.get(
    "/patients/{patient_id}/coded-entities/{concept_id}/mentions/{encounter_id}",
    response_model=ConceptMentionDetail,
)
def get_concept_mention_detail(
    patient_id: str,
    concept_id: str,
    encounter_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> ConceptMentionDetail:
    """Full evidence sentence and assertion for one dated mention."""
    query = _pick_query(
        scope, GET_CONCEPT_MENTION_DETAIL_ADMIN, GET_CONCEPT_MENTION_DETAIL_SCOPED
    )
    params = _cypher_params(
        scope, patient_id, concept_id=concept_id, encounter_id=encounter_id
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
        encounter_id=r.get("encounter_id", encounter_id),
        encounter_date=_date_only(r.get("encounter_date")),
        concept_id=concept_id,
        name=r.get("name"),
        read_code=r.get("read_code"),
        assertion=_assertion_from_context(r.get("context_json")),
        confidence=(
            float(r["confidence"]) if r.get("confidence") is not None else None
        ),
        evidence=r.get("evidence"),
        evidence_sentence=r.get("evidence_sentence"),
    )
