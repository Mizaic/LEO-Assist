"""Coding review router -- HITL queue for candidate SNOMED codes.

Atlas trace:
  DO: DO-236545C8
  Also implements: DO-2D2CE052, DO-54397CCD, DO-6CD07544, DO-94D87FA7, DO-A35D2D57, DO-B88D4941, DO-BA2B7A99
  DI: DI-2D9F5064, DI-37B3DC71, DI-3EA60D5A, DI-54D00E21, DI-6EFD68D0, DI-A0579B64, DI-AF5A1668, DI-D2D0117E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

Extracted from services/api/app/routers/training.py (2026-07 CTO peer-review
item 2: core-api router decomposition). Pure move, no behaviour change --
existing DO/DI trace headers carried over unchanged.

Routes: coding-review queue/siblings/entity-label/assertion/grouped/tier-calibration/resolve/batch-resolve/ignore/recheck(+status)/stats, review-queue delete-all. Also attaches Ask LEO endpoints (ask_leo_coding, ask_leo_rank_candidates, ask_leo_smart) via _training_askleo.register_askleo_routes, unchanged from training.py.

Depends on app.routers.context_and_ignore_rules for _write_coding_ignore_rule and _create_surface_form_task_for_correction (co-located there with the rest of the ignore-rule / surface-form surface) -- confirmed safe during the item-2 discovery pass, one directional import, no cycle. Also depends on app.routers._training_common for _VALID_ENTITY_LABELS (shared with training_labels / training_gold_labels).
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from libs.auth.org_scope import (
    CallerScope,
    get_caller_scope,
)
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from app.deps import require_admin
from libs.cypher.coding_review_queries import (
    AUTO_RESOLVE_CODING_REVIEW,
    BATCH_RESOLVE_BY_ENTITY_TEXT,
    COUNT_CODING_REVIEW_GROUPS,
    COUNT_CODING_REVIEW_PENDING,
    DELETE_ALL_CODING_REVIEWS_UNCONDITIONAL,
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
    UPDATE_ASSERTION_FOR_REVIEW,
    UPDATE_ENTITY_LABEL_FOR_TEXT,
    GET_TIER_OVERRIDE_STATS,
    DELETE_RESOLVED_CODING_REVIEWS,
)
from libs.cypher.exclusion_queries import DELETE_ALL_HITL_TASKS
from libs.cypher.surface_form_task_queries import (
    DELETE_ALL_SURFACE_FORM_TASKS,
)
from libs.ner.schema_mapper import LABEL_TO_SNOMED_TAG
from libs.terminology.client import TerminologyClient
from libs.utils.logging import logging_context
from app.routers._training_askleo import register_askleo_routes
from app.routers.context_and_ignore_rules import (
    _write_coding_ignore_rule,
    _create_surface_form_task_for_correction,
)
from app.routers._training_common import _VALID_ENTITY_LABELS

logger = logging.getLogger(__name__)

router = APIRouter()
register_askleo_routes(router)


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
            body.entity_text,
            body.entity_label,
            body.corrected_by,
            updated,
        )
        return {
            "entity_text": body.entity_text,
            "entity_label": body.entity_label,
            "updated_count": updated,
        }
    finally:
        client.close()


_VALID_ASSERTIONS = frozenset(
    {
        "present",
        "absent",
        "refuted",
        "possible",
        "historical",
        "planned",
        "hypothetical",
        "family",
        "declined",
        "cancelled",
    }
)


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
            raise HTTPException(
                status_code=404, detail=f"Review {review_id!r} not found"
            )
        logger.info(
            "Assertion overridden: review=%s assertion=%r by %s",
            review_id[:12],
            body.assertion,
            body.corrected_by,
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

    CSO-001 two-reviewer gate:
    - When the reviewer picks a DIFFERENT concept, we fix this one record
      immediately but do NOT create a live MAPS_TO mapping. Instead we
      create a SurfaceFormTask so a second reviewer can confirm before the
      mapping goes live.
    - When the reviewer CONFIRMS the original concept (same ID), we upsert
      the SurfaceForm mapping directly because the mapping already exists
      and is simply being validated.
    """
    from services.api.app.db.neo4j_client import CodingGraphClient
    from services.api.app.models.neo4j_schema import UPSERT_SURFACE_FORM_MAPPING

    client = PatientGraphClient()
    try:
        with client.session() as session:
            cr_row = session.run(
                "MATCH (cr:CodingReview {review_id: $review_id}) "
                "RETURN cr.entity_text AS entity_text, "
                "cr.snomed_concept_id AS original_concept_id",
                review_id=review_id,
            ).single()
            entity_text = str(cr_row["entity_text"]) if cr_row else ""
            original_concept_id = (
                str(cr_row["original_concept_id"] or "") if cr_row else ""
            )
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

    concept_changed = body.resolved_concept_id != original_concept_id
    surface_form_task_created = False

    if entity_text:
        if concept_changed:
            surface_form_task_created = _create_surface_form_task_for_correction(
                entity_text=entity_text,
                original_concept_id=original_concept_id,
                resolved_concept_id=body.resolved_concept_id,
                resolved_term=body.resolved_term,
                reviewer=body.reviewer,
            )
        else:
            from libs.terminology.cache_invalidation import (
                invalidate_terminology_resolution_caches,
            )

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
                invalidate_terminology_resolution_caches(
                    reason=f"coding_review_surface_form:{normalized}"
                )
                coding_client.close()
                logger.info(
                    "Confirmed surface form mapping: %r -> %s (%s)",
                    entity_text,
                    body.resolved_concept_id,
                    body.resolved_term,
                )
            except Exception:
                logger.warning(
                    "Failed to upsert surface form mapping for %r",
                    entity_text,
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
                cascade_count = cascade_row["resolved_count"] if cascade_row else 0
        except Exception:
            logger.warning("Cascade resolve failed for %r", entity_text, exc_info=True)
        finally:
            cascade_client.close()
        if cascade_count:
            logger.info(
                "Cascade-resolved %d additional reviews for %r",
                cascade_count,
                entity_text,
            )

    return {
        "review_id": result["review_id"],
        "status": "resolved",
        "concept_changed": concept_changed,
        "surface_form_task_created": surface_form_task_created,
        "surface_form_created": not concept_changed and bool(entity_text),
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
        from libs.terminology.cache_invalidation import (
            invalidate_terminology_resolution_caches,
        )

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
        invalidate_terminology_resolution_caches(
            reason=f"batch_coding_review_surface_form:{normalized}"
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


_RECHECK_BATCH_LIMIT = 500
_RECHECK_TERM_CHUNK = int(__import__("os").getenv("RECHECK_TERM_CHUNK", "50"))
_RECHECK_THRESHOLD = float(
    __import__("os").getenv("CODING_REVIEW_SCORE_THRESHOLD", "0.70")
)
_RECHECK_ALT_LOW = float(__import__("os").getenv("CODING_ALT_THRESHOLD_LOW", "0.3"))


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
    """Resolve a chunk of terms via cached shared terminology client."""
    chunk_tags = None
    if expected_tags:
        subset = {t: expected_tags[t] for t in terms if t in expected_tags}
        if subset:
            chunk_tags = subset

    try:
        raw = TerminologyClient(timeout=60, max_retries=1).resolve_raw(
            terms=terms,
            expected_tags=chunk_tags,
        )
        normalised: dict[str, list[dict[str, Any]]] = {}
        for term, candidates in raw.items():
            term_candidates: list[dict[str, Any]] = []
            for candidate in candidates or []:
                if not isinstance(candidate, dict):
                    continue
                term_candidates.append(
                    {
                        "snomed_concept_id": (
                            candidate.get("snomed_concept_id")
                            or candidate.get("concept_id")
                            or candidate.get("conceptId")
                            or ""
                        ),
                        "snomed_term": (
                            candidate.get("snomed_term")
                            or candidate.get("term")
                            or candidate.get("preferredTerm")
                            or ""
                        ),
                        "semantic_tag": (
                            candidate.get("semantic_tag")
                            or candidate.get("semanticTag")
                            or ""
                        ),
                        "score": candidate.get("score"),
                    }
                )
            normalised[str(term)] = term_candidates
        return normalised
    except Exception:
        logger.warning(
            "Terminology chunk call failed (%d terms)", len(terms), exc_info=True
        )
        return {}


def _call_terminology_batch(
    terms: list[str],
    expected_tags: dict[str, str] | None = None,
) -> dict[str, list]:
    """POST terms to the terminology resolve endpoint in chunks to avoid timeouts."""
    merged: dict[str, list] = {}
    for i in range(0, len(terms), _RECHECK_TERM_CHUNK):
        chunk = terms[i : i + _RECHECK_TERM_CHUNK]
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
        from libs.terminology.cache_invalidation import (
            invalidate_terminology_resolution_caches,
        )

        invalidate_terminology_resolution_caches(
            reason=f"coding_review_recheck_surface_form:{normalized}"
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
            agent_task="training_alt_term_suggester",
        )
        raw_text = response.text.strip()
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if not match:
            logger.info(
                "RECHECK: [LLM_SUGGEST] term=%r label=%s -- no JSON array in response: %s",
                term,
                entity_label,
                raw_text[:120],
            )
            return []
        raw = _json.loads(match.group())
        seen = term.strip().lower()
        alts = [
            s.strip() for s in raw if isinstance(s, str) and s.strip().lower() != seen
        ][:4]
        logger.info(
            "RECHECK: [LLM_SUGGEST] term=%r label=%s -> alts=%r",
            term,
            entity_label,
            alts,
        )
        return alts
    except Exception:
        logger.warning(
            "RECHECK: [LLM_SUGGEST] LLM call failed for term=%r", term, exc_info=True
        )
        return []


def _recheck_alt_coding(term: str, entity_label: str) -> tuple[dict, str] | None:
    """Try LLM-suggested alternatives for a near-miss term.

    Returns (best_candidate, alt_term_used) if any alternative scores >= threshold,
    else None. Logs all alternatives tried and their scores for audit.
    """
    alt_terms = _recheck_suggest_alts(term, entity_label)
    if not alt_terms:
        logger.info(
            "RECHECK: [LLM_ALT] term=%r label=%s -- LLM returned no alternatives",
            term,
            entity_label,
        )
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
            term,
            alt,
            concept_id,
            snomed_term,
            score,
        )
        if score >= _RECHECK_THRESHOLD and score > best_score:
            best_score = score
            best = top
            best_alt = alt

    if best:
        logger.info(
            "RECHECK: [LLM_ALT_RESOLVED] term=%r via alt=%r -> concept=%r snomed=%r score=%.4f",
            term,
            best_alt,
            best.get("snomed_concept_id"),
            best.get("snomed_term"),
            best_score,
        )
        return best, best_alt

    logger.info(
        "RECHECK: [LLM_ALT_NO_MATCH] term=%r -- no alternative cleared threshold=%.2f",
        term,
        _RECHECK_THRESHOLD,
    )
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
            entity_text,
            entity_label,
            review_id,
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
            entity_text,
            entity_label,
            review_id,
        )
    elif score is not None and score >= _RECHECK_THRESHOLD:
        logger.info(
            "RECHECK: [DIRECT] term=%r label=%s -> concept=%r snomed=%r score=%.4f review=%s",
            entity_text,
            entity_label,
            concept_id,
            term,
            score,
            review_id,
        )
    elif try_alternatives and score is not None and score >= _RECHECK_ALT_LOW:
        logger.info(
            "RECHECK: [NEAR_MISS] term=%r label=%s score=%.4f -- trying LLM alternatives review=%s",
            entity_text,
            entity_label,
            score,
            review_id,
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
            entity_text,
            entity_label,
            f"{score:.4f}" if score is not None else "None",
            review_id,
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
            entity_text,
            concept_id,
            term,
            score,
            resolved_by,
            review_id,
            writeback_ok,
        )
        if resolved_by.startswith("llm_alt:"):
            return "resolved_llm", writeback_ok
        return "resolved_direct", writeback_ok

    # Last resort: model escalation (small -> big -> max) for unresolved items
    if try_alternatives:
        from libs.llm_client.escalation import escalate_coding

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
                entity_text,
                esc.concept_id,
                esc.model_tier,
                esc.confidence,
                review_id,
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
        entity_text,
        entity_label,
        review_id,
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
                        rows = session.run(GET_PENDING_FOR_RECHECK, limit=fetch_limit)
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
                            if outcome in {
                                "resolved_direct",
                                "resolved_llm",
                                "ignored",
                            }:
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
                        job_id,
                        total_rechecked,
                        item_limit,
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
        return (
            dict(row)
            if row
            else {
                "total": 0,
                "coded": 0,
                "uncoded": 0,
                "resolved": 0,
                "pending": 0,
                "low_confidence": 0,
                "assertion_flagged": 0,
            }
        )
    finally:
        client.close()


@router.delete("/coding-review/resolved")
def delete_resolved_coding_reviews(
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Delete resolved CodingReview queue items."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            summary = session.run(DELETE_RESOLVED_CODING_REVIEWS).consume()
        return {"deleted": summary.counters.nodes_deleted}
    finally:
        client.close()


@router.delete("/review-queue/all")
def delete_all_review_queue_items(
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Delete all review queue items (CodingReview, SurfaceFormTask, HITLTask).
    Use when clearing items from an old pipeline before running the new one."""
    pg_client = PatientGraphClient()
    kg_client = KnowledgeGraphClient()
    try:
        with pg_client.session() as session:
            cr_summary = session.run(DELETE_ALL_CODING_REVIEWS_UNCONDITIONAL).consume()
            hitl_summary = session.run(DELETE_ALL_HITL_TASKS).consume()
        with kg_client.session() as session:
            sf_summary = session.run(DELETE_ALL_SURFACE_FORM_TASKS).consume()
        return {
            "coding_reviews_deleted": cr_summary.counters.nodes_deleted,
            "surface_form_tasks_deleted": sf_summary.counters.nodes_deleted,
            "hitl_tasks_deleted": hitl_summary.counters.nodes_deleted,
            "total_deleted": (
                cr_summary.counters.nodes_deleted
                + sf_summary.counters.nodes_deleted
                + hitl_summary.counters.nodes_deleted
            ),
        }
    finally:
        pg_client.close()
        kg_client.close()
