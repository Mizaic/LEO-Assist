"""Phrase mappings inbox: draft, submit, two-person publish.

Atlas trace:
  DI: DI-D90542E5, DI-6BD7B681, DI-B00BD595
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B00BD595")
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from libs.auth.break_glass import require_second_person
from libs.cypher.uncoded_phrase_queries import (
    CLOSE_UNCODED_PHRASE,
    COUNT_MY_DRAFTS,
    COUNT_UNCODED_BY_STATUS,
    COUNT_UNCODED_PHRASES,
    GET_UNCODED_PHRASE,
    LIST_UNCODED_PHRASES,
    SAVE_UNCODED_DRAFT,
    SEND_BACK_UNCODED_PHRASE,
    ENSURE_UNCODED_PHRASE,
    SUBMIT_ONE_UNCODED_DRAFT,
    SUBMIT_UNCODED_DRAFTS,
)
from libs.pipeline.uncoded_phrase import normalise_phrase, sanitize_sample_sentence

logger = logging.getLogger(__name__)

_VALID_STATUSES = {"inbox", "draft", "review", "closed"}
_VALID_ACTIONS = {"map", "exclude"}


def _actor(email: str) -> str:
    return (email or "").strip().lower()


def _sanitize_phrase_row(row: dict[str, Any]) -> dict[str, Any]:
    sample = str(row.get("sample_sentence") or "")
    if not sample:
        return row
    out = dict(row)
    out["sample_sentence"] = sanitize_sample_sentence(sample)
    return out


def _kg_client():
    from libs.neo4j_client.client import KnowledgeGraphClient

    return KnowledgeGraphClient()


def counts(author: str) -> dict[str, int]:
    client = _kg_client()
    try:
        rows = client.run(COUNT_UNCODED_BY_STATUS)
        out = {"inbox": 0, "draft": 0, "review": 0, "closed": 0, "my_drafts": 0}
        for row in rows:
            status = str(row.get("status") or "")
            if status in out:
                out[status] = int(row.get("total") or 0)
        me = _actor(author)
        if me:
            mine = client.run(COUNT_MY_DRAFTS, author=me)
            out["my_drafts"] = int(mine[0]["total"]) if mine else 0
        return out
    finally:
        client.close()


def list_phrases(
    status: str,
    *,
    author: str = "",
    skip: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    if status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown queue status")
    client = _kg_client()
    try:
        items = [
            _sanitize_phrase_row(row)
            for row in client.run(
                LIST_UNCODED_PHRASES,
                status=status,
                author=_actor(author) if status == "draft" else "",
                skip=skip,
                limit=limit,
            )
        ]
        if status == "draft" and author:
            total_rows = client.run(COUNT_MY_DRAFTS, author=_actor(author))
        else:
            total_rows = client.run(COUNT_UNCODED_PHRASES, status=status)
        total = int(total_rows[0]["total"]) if total_rows else 0
        return {"items": items, "total": total, "skip": skip, "limit": limit}
    finally:
        client.close()


def save_draft(
    phrase_key: str,
    *,
    action: str,
    actor: str,
    concept_id: str = "",
    concept_term: str = "",
    reason: str = "",
) -> dict[str, Any]:
    key = normalise_phrase(phrase_key)
    if not key:
        raise HTTPException(status_code=400, detail="Phrase is empty")
    if action not in _VALID_ACTIONS:
        raise HTTPException(status_code=400, detail="Choose map or exclude")
    if action == "map" and not (concept_id or "").strip():
        raise HTTPException(status_code=400, detail="Pick a SNOMED code to map")
    if action == "exclude" and not (reason or "").strip():
        raise HTTPException(status_code=400, detail="Exclude needs a reason")
    client = _kg_client()
    try:
        rows = client.run(
            SAVE_UNCODED_DRAFT,
            phrase_key=key,
            draft_action=action,
            draft_concept_id=(concept_id or "").strip(),
            draft_concept_term=(concept_term or "").strip(),
            draft_reason=(reason or "").strip(),
            draft_author=_actor(actor),
        )
        if not rows:
            raise HTTPException(
                status_code=404,
                detail="Phrase not found or already submitted",
            )
        return rows[0]
    finally:
        client.close()


def get_phrase(phrase_key: str) -> dict[str, Any]:
    key = normalise_phrase(phrase_key)
    if not key:
        raise HTTPException(status_code=400, detail="Phrase is empty")
    client = _kg_client()
    try:
        rows = client.run(GET_UNCODED_PHRASE, phrase_key=key)
        if not rows:
            raise HTTPException(status_code=404, detail="Phrase not found")
        return _sanitize_phrase_row(rows[0])
    finally:
        client.close()


def ensure_phrase(
    phrase_key: str,
    *,
    extracted_tag: str = "",
    extracted_source: str = "",
    sample_span: str = "",
    sample_sentence: str = "",
) -> dict[str, Any]:
    key = normalise_phrase(phrase_key)
    if not key:
        raise HTTPException(status_code=400, detail="Phrase is empty")
    span = (sample_span or phrase_key).strip()
    client = _kg_client()
    try:
        rows = client.run(
            ENSURE_UNCODED_PHRASE,
            phrase_key=key,
            normalized=key,
            extracted_tag=(extracted_tag or "").strip(),
            extracted_source=(extracted_source or "").strip(),
            sample_span=span,
            sample_sentence=sanitize_sample_sentence(
                (sample_sentence or "").strip()
            ),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Phrase not found")
        return _sanitize_phrase_row(rows[0])
    finally:
        client.close()


def submit_one(phrase_key: str, author: str) -> dict[str, Any]:
    key = normalise_phrase(phrase_key)
    if not key:
        raise HTTPException(status_code=400, detail="Phrase is empty")
    client = _kg_client()
    try:
        rows = client.run(
            SUBMIT_ONE_UNCODED_DRAFT,
            phrase_key=key,
            author=_actor(author),
        )
        if not rows:
            raise HTTPException(
                status_code=409,
                detail="Save a draft first, then submit this phrase",
            )
        return rows[0]
    finally:
        client.close()


def submit_drafts(author: str) -> dict[str, Any]:
    client = _kg_client()
    try:
        rows = client.run(SUBMIT_UNCODED_DRAFTS, author=_actor(author))
        submitted = int(rows[0]["submitted"]) if rows else 0
        return {"submitted": submitted}
    finally:
        client.close()


def send_back(phrase_key: str) -> dict[str, Any]:
    key = normalise_phrase(phrase_key)
    client = _kg_client()
    try:
        rows = client.run(SEND_BACK_UNCODED_PHRASE, phrase_key=key)
        if not rows:
            raise HTTPException(status_code=404, detail="Phrase is not in review")
        return rows[0]
    finally:
        client.close()


def _publish_map(row: dict[str, Any], actor: str) -> None:
    from libs.terminology.cache_invalidation import (
        invalidate_terminology_resolution_caches,
    )
    from services.api.app.db.neo4j_client import CodingGraphClient
    from services.api.app.models.neo4j_schema import UPSERT_SURFACE_FORM_MAPPING
    from services.terminology_api.app.services.surface_form_admin import (
        approve_surface_form_mapping,
    )

    normalized = str(row.get("normalized") or "")
    form = str(row.get("sample_span") or row.get("normalized") or "")
    concept_id = str(row.get("draft_concept_id") or "").strip()
    coding = CodingGraphClient()
    try:
        written = coding.run(
            UPSERT_SURFACE_FORM_MAPPING,
            normalized=normalized,
            form=form,
            concept_id=concept_id,
            confidence=1.0,
            source="phrase_mappings",
            provenance="phrase_mappings_publish",
            created_by=str(row.get("draft_author") or actor),
            actor=actor,
        )
        if not written:
            raise HTTPException(status_code=404, detail="SNOMED concept not found")
        approve_surface_form_mapping(
            coding,
            normalized=normalized,
            reviewer=actor,
            concept_id=concept_id,
        )
        invalidate_terminology_resolution_caches(
            reason=f"phrase_mappings_publish:{normalized}"
        )
    finally:
        coding.close()


def _publish_exclude(row: dict[str, Any], actor: str) -> None:
    from app.routers.context_and_ignore_rules import _write_coding_ignore_rule

    reason = str(row.get("draft_reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Exclude needs a reason")
    _write_coding_ignore_rule(
        entity_text=str(row.get("normalized") or ""),
        entity_label=str(row.get("extracted_tag") or ""),
        reason=reason,
        created_by=actor,
    )


def publish(
    phrase_key: str,
    actor: str,
    *,
    is_platform_admin: bool = False,
    break_glass_reason: str = "",
) -> dict[str, Any]:
    key = normalise_phrase(phrase_key)
    who = _actor(actor)
    if not who:
        raise HTTPException(status_code=401, detail="Sign in to publish")
    client = _kg_client()
    try:
        found = client.run(GET_UNCODED_PHRASE, phrase_key=key)
        if not found:
            raise HTTPException(status_code=404, detail="Phrase not found")
        row = found[0]
        if str(row.get("status") or "") != "review":
            raise HTTPException(
                status_code=409,
                detail="Only a submitted draft can be published",
            )
        author = _actor(str(row.get("draft_author") or ""))
        require_second_person(
            author=author,
            actor=who,
            is_platform_admin=is_platform_admin,
            reason=break_glass_reason,
            gate="phrase_publish",
            resource_id=key,
        )
        action = str(row.get("draft_action") or "")
        if action == "map":
            _publish_map(row, who)
        elif action == "exclude":
            _publish_exclude(row, who)
        else:
            raise HTTPException(status_code=400, detail="Draft has no map or exclude")
        closed = client.run(CLOSE_UNCODED_PHRASE, phrase_key=key, published_by=who)
        if not closed:
            raise HTTPException(status_code=409, detail="Could not close the phrase")
        return closed[0]
    finally:
        client.close()
