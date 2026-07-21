"""TrainingCandidate router -- dedupe, prune, active-learning queue.

Atlas trace:
  DO: DO-236545C8
  Also implements: DO-2D2CE052, DO-54397CCD, DO-6CD07544, DO-94D87FA7, DO-A35D2D57, DO-B88D4941, DO-BA2B7A99
  DI: DI-2D9F5064, DI-37B3DC71, DI-3EA60D5A, DI-54D00E21, DI-6EFD68D0, DI-A0579B64, DI-AF5A1668, DI-D2D0117E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

Extracted from services/api/app/routers/training.py (2026-07 CTO peer-review
item 2: core-api router decomposition). Pure move, no behaviour change --
existing DO/DI trace headers carried over unchanged.

Routes: candidates dedupe preview/apply, find-similar-by-entity, stats/list/get/delete, active-learning-queue + score, prune preview/execute, mark-completed. Also attaches AI-first-pass job endpoints (/candidates/ai-first-pass/jobs*) via _training_ai_first_pass.register_ai_first_pass_routes -- moved here (not coding_review) because those routes are candidates-domain, confirmed during the item-2 discovery pass.

Depends on app.routers.training_gold_labels for _apply_gold_granularity_metadata (mark_training_candidate_completed shares this helper with the gold-label endpoints; one directional import, no cycle). Also depends on app.routers._training_common for _enrich_items_entities_with_pt_cache (shared with training_gold_labels).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from libs.auth.org_scope import (
    CallerScope,
    get_caller_scope,
)
from libs.neo4j_client.client import KnowledgeGraphClient
from app.deps import require_admin
from libs.cypher.training_candidate_queries import (
    COUNT_TRAINING_CANDIDATES_PAGE,
    DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS,
    GET_TRAINING_CANDIDATE_BY_ID,
    GET_TRAINING_CANDIDATE_STATS,
    GET_TRAINING_CANDIDATES_PAGE,
    MARK_TRAINING_CANDIDATE_DUPLICATES,
    UPDATE_TRAINING_CANDIDATE_STATUS,
)
from libs.cypher.gold_label_queries import (
    GET_GOLD_LABEL_BY_CANDIDATE_ID,
    UPSERT_GOLD_LABEL,
)
from libs.search.term_expansion import expand_search_terms
from libs.terminology.client import TerminologyClient
from app.routers._training_ai_first_pass import register_ai_first_pass_routes
from app.routers.training_gold_labels import (
    _apply_gold_granularity_metadata,
)
from app.routers._training_common import _enrich_items_entities_with_pt_cache

logger = logging.getLogger(__name__)

router = APIRouter()
register_ai_first_pass_routes(router)


class CandidateDedupeRequest(BaseModel):
    status: str | None = "completed"
    source: str | None = None
    search: str | None = None
    max_candidates: int = Field(default=1200, ge=50, le=3000)
    similarity_threshold: float = Field(default=0.85, ge=0.5, le=0.99)


class SimilarCandidatesByEntityRequest(BaseModel):
    candidate_id: str
    limit: int = Field(default=20, ge=1, le=100)
    similarity_threshold: float = Field(default=0.65, ge=0.3, le=0.99)


_DEDUPE_STOP_WORDS = {
    "and",
    "the",
    "with",
    "from",
    "that",
    "this",
    "have",
    "has",
    "for",
    "into",
    "was",
    "were",
    "are",
    "had",
    "not",
    "you",
    "your",
    "their",
    "they",
    "she",
    "him",
    "her",
    "his",
}


def _normalise_candidate_text(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", str(text).lower())
    return " ".join(cleaned.split())


def _tokenise_candidate_text(text: str) -> set[str]:
    tokens = _normalise_candidate_text(text).split()
    return {t for t in tokens if len(t) > 2 and t not in _DEDUPE_STOP_WORDS}


def _candidate_similarity(left: str, right: str) -> float:
    left_norm = _normalise_candidate_text(left)
    right_norm = _normalise_candidate_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0

    left_tokens = _tokenise_candidate_text(left_norm)
    right_tokens = _tokenise_candidate_text(right_norm)
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    jaccard = (intersection / union) if union else 0.0
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    containment = min(len(left_tokens), len(right_tokens)) / max(
        1, max(len(left_tokens), len(right_tokens))
    )
    overlap = intersection / max(1, min(len(left_tokens), len(right_tokens)))
    substring_bonus = 0.0
    if left_norm in right_norm or right_norm in left_norm:
        substring_bonus = 0.10
    score = (
        (0.40 * jaccard)
        + (0.25 * sequence)
        + (0.20 * containment)
        + (0.15 * overlap)
        + substring_bonus
    )
    score = min(1.0, score)
    return round(float(score), 6)


def _candidate_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": row.get("candidate_id"),
        "status": row.get("status"),
        "source": row.get("source"),
        "updated_at": row.get("updated_at"),
        "text_preview": str(row.get("text") or "")[:220],
    }


def _find_root(parent: dict[int, int], node: int) -> int:
    while parent[node] != node:
        parent[node] = parent[parent[node]]
        node = parent[node]
    return node


def _union_roots(parent: dict[int, int], left: int, right: int) -> None:
    root_left = _find_root(parent, left)
    root_right = _find_root(parent, right)
    if root_left != root_right:
        parent[root_right] = root_left


def _build_candidate_pairs(rows: list[dict[str, Any]]) -> set[tuple[int, int]]:
    """Build likely duplicate pairs using token-overlap canopies.

    Previous fixed-prefix blocking missed obvious near-duplicates when one row had
    an extra prefix fragment (for example "Seen in 2WW clinic: ...").
    """
    token_index: dict[str, set[int]] = defaultdict(set)
    token_sets: list[set[str]] = []

    for idx, row in enumerate(rows):
        tokens = _tokenise_candidate_text(str(row.get("text") or ""))
        token_sets.append(tokens)
        for token in tokens:
            token_index[token].add(idx)

    pairs: set[tuple[int, int]] = set()
    for left_idx, left_tokens in enumerate(token_sets):
        if not left_tokens:
            continue
        neighbour_overlap: dict[int, int] = defaultdict(int)
        for token in left_tokens:
            for right_idx in token_index[token]:
                if right_idx <= left_idx:
                    continue
                neighbour_overlap[right_idx] += 1
        min_overlap = 1 if len(left_tokens) < 4 else 2
        for right_idx, overlap in neighbour_overlap.items():
            if overlap >= min_overlap:
                pairs.add((left_idx, right_idx))

    # Small candidate pools can afford exhaustive comparison.
    if len(rows) <= 250:
        for left_idx in range(len(rows)):
            for right_idx in range(left_idx + 1, len(rows)):
                pairs.add((left_idx, right_idx))
    return pairs


def _cluster_candidates(
    rows: list[dict[str, Any]], threshold: float
) -> tuple[dict[int, list[int]], dict[tuple[int, int], float]]:
    parent: dict[int, int] = {i: i for i in range(len(rows))}
    edge_scores: dict[tuple[int, int], float] = {}
    for left_idx, right_idx in _build_candidate_pairs(rows):
        score = _candidate_similarity(
            str(rows[left_idx].get("text") or ""),
            str(rows[right_idx].get("text") or ""),
        )
        if score < threshold:
            continue
        pair = tuple(sorted((left_idx, right_idx)))
        edge_scores[pair] = max(score, edge_scores.get(pair, 0.0))
        _union_roots(parent, left_idx, right_idx)
    grouped: dict[int, list[int]] = defaultdict(list)
    for idx in range(len(rows)):
        grouped[_find_root(parent, idx)].append(idx)
    return grouped, edge_scores


def _build_candidate_similarity_groups(
    rows: list[dict[str, Any]], threshold: float
) -> list[dict[str, Any]]:
    if len(rows) < 2:
        return []
    grouped, edge_scores = _cluster_candidates(rows, threshold)
    groups: list[dict[str, Any]] = []
    for members in grouped.values():
        if len(members) < 2:
            continue
        sorted_members = sorted(
            members,
            key=lambda i: (
                -len(str(rows[i].get("text") or "")),
                str(rows[i].get("updated_at") or ""),
                str(rows[i].get("candidate_id") or ""),
            ),
        )
        canonical_idx = sorted_members[0]
        duplicates: list[dict[str, Any]] = []
        for member_idx in sorted_members[1:]:
            pair = tuple(sorted((canonical_idx, member_idx)))
            similarity = edge_scores.get(
                pair,
                _candidate_similarity(
                    str(rows[canonical_idx].get("text") or ""),
                    str(rows[member_idx].get("text") or ""),
                ),
            )
            payload = _candidate_payload(rows[member_idx])
            payload["similarity"] = round(float(similarity), 6)
            duplicates.append(payload)
        groups.append(
            {
                "canonical": _candidate_payload(rows[canonical_idx]),
                "duplicates": duplicates,
            }
        )
    groups.sort(key=lambda g: len(g.get("duplicates", [])), reverse=True)
    return groups


def _extract_candidate_entity_terms(entities_json: Any) -> set[str]:
    if not entities_json:
        return set()
    try:
        parsed = json.loads(entities_json)
    except Exception:
        return set()
    if not isinstance(parsed, list):
        return set()
    terms: set[str] = set()
    for row in parsed:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        normalised = _normalise_candidate_text(text)
        if normalised:
            terms.add(normalised)
    return terms


def _entity_similarity(left_terms: set[str], right_terms: set[str]) -> float:
    if not left_terms or not right_terms:
        return 0.0
    exact = len(left_terms & right_terms)
    if exact:
        return min(1.0, 0.7 + (exact / max(1, len(left_terms))))
    best = 0.0
    for left in left_terms:
        for right in right_terms:
            best = max(best, _candidate_similarity(left, right))
    return round(float(best), 6)


def _fetch_dedupe_candidates(
    *,
    status: str | None,
    source: str | None,
    search: str | None,
    max_candidates: int,
) -> list[dict[str, Any]]:
    terms = expand_search_terms(search)
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                GET_TRAINING_CANDIDATES_PAGE,
                skip=0,
                limit=max_candidates,
                status=status,
                exclude_completed=False,
                source=source,
                search=search,
                terms=terms,
            )
            return [dict(r) for r in rows]
    finally:
        client.close()


@router.post("/candidates/dedupe/preview")
def preview_training_candidate_dedupe(
    body: CandidateDedupeRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    rows = _fetch_dedupe_candidates(
        status=body.status,
        source=body.source,
        search=body.search,
        max_candidates=body.max_candidates,
    )
    groups = _build_candidate_similarity_groups(rows, body.similarity_threshold)
    duplicate_count = sum(len(g.get("duplicates", [])) for g in groups)
    return {
        "candidate_pool_size": len(rows),
        "group_count": len(groups),
        "duplicate_count": duplicate_count,
        "similarity_threshold": body.similarity_threshold,
        "groups": groups,
    }


@router.post("/candidates/dedupe/apply")
def apply_training_candidate_dedupe(
    body: CandidateDedupeRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    rows = _fetch_dedupe_candidates(
        status=body.status,
        source=body.source,
        search=body.search,
        max_candidates=body.max_candidates,
    )
    groups = _build_candidate_similarity_groups(rows, body.similarity_threshold)
    updates: list[dict[str, Any]] = []
    for group in groups:
        canonical_id = str(group["canonical"]["candidate_id"])
        for duplicate in group.get("duplicates", []):
            duplicate_id = str(duplicate.get("candidate_id") or "")
            if not duplicate_id or duplicate_id == canonical_id:
                continue
            updates.append(
                {
                    "canonical_id": canonical_id,
                    "duplicate_id": duplicate_id,
                    "score": float(duplicate.get("similarity") or 0.0),
                    "method": "token_jaccard+sequence",
                }
            )

    if not updates:
        return {
            "candidate_pool_size": len(rows),
            "duplicates_marked": 0,
            "group_count": 0,
            "run_id": None,
            "message": "No duplicates met the similarity threshold.",
        }

    run_id = f"dedupe-{uuid.uuid4().hex}"
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            result_row = session.run(
                MARK_TRAINING_CANDIDATE_DUPLICATES,
                updates=updates,
                run_id=run_id,
            ).single()
        duplicates_marked = int(result_row["duplicates_marked"] if result_row else 0)
    finally:
        client.close()

    logger.info(
        "TrainingCandidate dedupe apply run=%s groups=%s duplicates=%s actor=%s",
        run_id,
        len(groups),
        duplicates_marked,
        getattr(scope, "email", "unknown"),
    )
    return {
        "candidate_pool_size": len(rows),
        "duplicates_marked": duplicates_marked,
        "group_count": len(groups),
        "run_id": run_id,
        "similarity_threshold": body.similarity_threshold,
    }


@router.post("/candidates/find-similar-by-entity")
def find_similar_candidates_by_entity(
    body: SimilarCandidatesByEntityRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    # Fetch all candidates (no status filter) so the source candidate is found
    # regardless of its current status (it may not be "pending" any more).
    rows = _fetch_dedupe_candidates(
        status=None,
        source=None,
        search=None,
        max_candidates=3000,
    )
    source_row = next(
        (
            row
            for row in rows
            if str(row.get("candidate_id") or "") == body.candidate_id
        ),
        None,
    )
    if not source_row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    source_terms = _extract_candidate_entity_terms(source_row.get("entities_json"))
    if not source_terms:
        return {"source_candidate_id": body.candidate_id, "count": 0, "items": []}

    matches: list[dict[str, Any]] = []
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        if not candidate_id or candidate_id == body.candidate_id:
            continue
        # Only surface pending candidates as bulk-labelling targets.
        if str(row.get("status") or "") != "pending":
            continue
        terms = _extract_candidate_entity_terms(row.get("entities_json"))
        similarity = _entity_similarity(source_terms, terms)
        if similarity < body.similarity_threshold:
            continue
        matches.append(
            {
                "candidate_id": candidate_id,
                "text": str(row.get("text") or ""),
                "source": row.get("source"),
                "status": row.get("status"),
                "updated_at": row.get("updated_at"),
                "entities_json": row.get("entities_json"),
                "similarity": similarity,
            }
        )
    matches.sort(key=lambda row: row.get("similarity", 0.0), reverse=True)
    limited = matches[: body.limit]
    return {
        "source_candidate_id": body.candidate_id,
        "count": len(limited),
        "items": limited,
    }


@router.get("/candidates/stats")
def get_training_candidate_stats(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_TRAINING_CANDIDATE_STATS).single()
        return (
            dict(row)
            if row
            else {
                "total": 0,
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
            }
        )
    finally:
        client.close()


@router.get("/candidates")
def list_training_candidates(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    status: str | None = None,
    source: str | None = None,
    search: str | None = None,
    exclude_completed: bool = Query(False),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    skip = (page - 1) * page_size
    # DI-LEO-AI-526 -- expand the reviewer's free-text query into the
    # same typo-corrected, synonym-expanded term list used by the host
    # encounter search so the dry-run review queue surfaces matching
    # rows for "lump" via "mass" / "swelling" / "nodule" too. Empty list
    # means the cypher falls back to the legacy `search` substring.
    terms = expand_search_terms(search)
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                GET_TRAINING_CANDIDATES_PAGE,
                skip=skip,
                limit=page_size,
                status=status,
                exclude_completed=exclude_completed,
                source=source,
                search=search,
                terms=terms,
            )
            items = [dict(r) for r in rows]
            _enrich_items_entities_with_pt_cache(session, items)
            count_row = session.run(
                COUNT_TRAINING_CANDIDATES_PAGE,
                status=status,
                exclude_completed=exclude_completed,
                source=source,
                search=search,
                terms=terms,
            ).single()
        total = count_row["total"] if count_row else 0
        return {"items": items, "page": page, "page_size": page_size, "total": total}
    finally:
        client.close()


@router.get("/candidates/active-learning-queue")
def active_learning_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return pending TrainingCandidates ranked by a blended priority score.

    priority_score = 0.6 * rarity_score + 0.4 * normalised_uncertainty

    rarity_score is derived from the current gold label distribution: labels
    with fewer gold examples produce a higher score so the reviewer is guided
    toward filling dataset gaps.  This works even before the first model is
    promoted because it reads entities_json directly from each candidate node.

    MUST be declared before /candidates/{candidate_id} so FastAPI does not
    treat the literal path segment as a candidate_id parameter.
    """
    from libs.cypher.training_candidate_queries import (
        GET_ALL_PENDING_FOR_RANKING,
        COUNT_ACTIVE_LEARNING_QUEUE,
    )

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            all_rows = [dict(r) for r in session.run(GET_ALL_PENDING_FOR_RANKING)]
            count_row = session.run(COUNT_ACTIVE_LEARNING_QUEUE).single()
        total = count_row["total"] if count_row else 0
    finally:
        client.close()

    label_counts = _fetch_label_counts_for_scoring()
    _enrich_and_sort(all_rows, label_counts)

    skip = (page - 1) * page_size
    items = all_rows[skip : skip + page_size]
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def _enrich_and_sort(
    rows: list[dict],
    label_counts: dict[str, int],
) -> None:
    """Mutate rows in-place: add rarity/priority fields and sort DESC."""
    for row in rows:
        r_score, r_labels = _rarity_for_candidate(
            row.get("entities_json"), label_counts
        )
        u_raw = float(row.get("uncertainty_score") or 0.0)
        norm_u = min(u_raw / 3.0, 1.0)
        row["rarity_score"] = r_score
        row["rare_labels"] = r_labels
        row["priority_score"] = round(0.6 * r_score + 0.4 * norm_u, 4)
    rows.sort(key=lambda r: r["priority_score"], reverse=True)


@router.post("/candidates/score")
def score_candidates_for_active_learning(
    scope: CallerScope = Depends(get_caller_scope),
    _admin=Depends(require_admin),
) -> dict[str, Any]:
    """Score pending candidates by NER uncertainty and store on the node.

    Runs in a background thread. Returns immediately with job metadata.
    Uncertainty = sum of -p*log(p) across token NER label distributions,
    using the currently promoted model from the registry.
    """
    job_id = str(uuid.uuid4())
    t = threading.Thread(
        target=_run_active_learning_scoring,
        args=(job_id,),
        daemon=True,
        name=f"al-score-{job_id[:8]}",
    )
    t.start()
    return {"job_id": job_id, "status": "started"}


@router.get("/candidates/{candidate_id}")
def get_training_candidate(
    candidate_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                GET_TRAINING_CANDIDATE_BY_ID, candidate_id=candidate_id
            ).single()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"Candidate {candidate_id!r} not found"
            )
        return dict(row)
    finally:
        client.close()


@router.delete("/candidates/{candidate_id}")
def delete_training_candidate(
    candidate_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS,
                candidate_id=candidate_id,
            ).single()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"Candidate {candidate_id!r} not found"
            )
        payload = dict(row)
        logger.info(
            "TrainingCandidate deleted id=%s gold_labels=%s surface_form_tasks=%s actor=%s",
            candidate_id[:12],
            payload.get("gold_labels_deleted", 0),
            payload.get("surface_form_tasks_deleted", 0),
            getattr(scope, "email", "unknown"),
        )
        return payload
    finally:
        client.close()


class PrunePreviewRequest(BaseModel):
    min_surface_match: float = Field(default=0.7, ge=0.0, le=1.0)
    semantic_vector_floor: float = Field(default=0.92, ge=0.0, le=1.0)
    semantic_min_surface: float = Field(default=0.66, ge=0.0, le=1.0)
    statuses: list[str] = Field(
        default_factory=lambda: ["pending", "processing", "failed"]
    )
    limit: int = Field(default=500, ge=1, le=2000)


class PruneExecuteRequest(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list)


@router.post("/candidates/prune/preview")
def prune_training_candidates_preview(
    body: PrunePreviewRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Dry-run the verdict ladder over non-completed TrainingCandidates.

    Returns a per-candidate assessment plus aggregate summary so the
    reviewer can sample before invoking ``/prune/execute`` with the
    explicit candidate_ids returned here.
    """
    from app.services.candidate_prune import (
        PruneParams,
        assess_candidates,
        summarise,
    )

    params = PruneParams(
        min_surface_match=float(body.min_surface_match),
        semantic_vector_floor=float(body.semantic_vector_floor),
        semantic_min_surface=float(body.semantic_min_surface),
        statuses=tuple(body.statuses or []),
        limit=int(body.limit),
    )

    kg = KnowledgeGraphClient()
    terminology = TerminologyClient()
    try:
        assessments = assess_candidates(kg, terminology, params)
    finally:
        kg.close()

    summary = summarise(assessments)
    payload = {
        "params": {
            "min_surface_match": params.min_surface_match,
            "semantic_vector_floor": params.semantic_vector_floor,
            "semantic_min_surface": params.semantic_min_surface,
            "statuses": list(params.statuses),
            "limit": params.limit,
        },
        "summary": summary,
        "candidates": [a.to_dict() for a in assessments],
    }
    logger.info(
        "candidate_prune.preview actor=%s scanned=%d delete=%d review=%d keep=%d",
        getattr(scope, "email", "unknown"),
        summary["candidate_count"],
        summary["by_verdict"].get("delete", 0),
        summary["by_verdict"].get("review", 0),
        summary["by_verdict"].get("keep", 0),
    )
    return payload


@router.post("/candidates/prune/execute")
def prune_training_candidates_execute(
    body: PruneExecuteRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Delete the explicitly-supplied TrainingCandidate IDs.

    Re-fetches each candidate before deletion and skips
    ``status='completed'`` to defend against TOCTOU drift between a
    prior preview and this execute call.
    """
    from app.services.candidate_prune import execute_prune

    if not body.candidate_ids:
        raise HTTPException(
            status_code=400,
            detail="candidate_ids must be non-empty",
        )

    kg = KnowledgeGraphClient()
    try:
        outcome = execute_prune(kg, body.candidate_ids)
    finally:
        kg.close()

    logger.info(
        "candidate_prune.execute actor=%s requested=%d deleted=%d "
        "skipped_completed=%d not_found=%d",
        getattr(scope, "email", "unknown"),
        len(outcome.requested),
        len(outcome.deleted),
        len(outcome.skipped_completed),
        len(outcome.not_found),
    )
    return {
        "requested": len(outcome.requested),
        "deleted": len(outcome.deleted),
        "skipped_completed": len(outcome.skipped_completed),
        "not_found": len(outcome.not_found),
        "deleted_ids": outcome.deleted,
        "skipped_completed_ids": outcome.skipped_completed,
        "not_found_ids": outcome.not_found,
        "cascade_counts": outcome.cascade_counts,
    }


@router.post("/candidates/{candidate_id}/mark-completed")
def mark_training_candidate_completed(
    candidate_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            candidate_row = session.run(
                GET_TRAINING_CANDIDATE_BY_ID,
                candidate_id=candidate_id,
            ).single()
            if not candidate_row:
                raise HTTPException(
                    status_code=404, detail=f"Candidate {candidate_id!r} not found"
                )

            gold_row = session.run(
                GET_GOLD_LABEL_BY_CANDIDATE_ID,
                candidate_id=candidate_id,
            ).single()
            if not gold_row:
                raise HTTPException(
                    status_code=409,
                    detail="Cannot mark completed until a linked gold label exists.",
                )

            text = gold_row.get("text", "") or candidate_row.get("text", "")
            entities_json = (
                gold_row.get("entities_json")
                or candidate_row.get("entities_json")
                or "[]"
            )
            label_id = gold_row.get("label_id") or f"manual-{uuid.uuid4().hex}"
            session.run(
                UPSERT_GOLD_LABEL,
                label_id=label_id,
                text=text,
                entities_json=entities_json,
                quality_score=gold_row.get("quality_score"),
                source="manual_gold_editor",
                verified_by=getattr(scope, "email", "operations_ui"),
                candidate_id=candidate_id,
                schema_version=gold_row.get("schema_version")
                or candidate_row.get("schema_version")
                or "v4",
            )
            _apply_gold_granularity_metadata(
                session,
                candidate_id=candidate_id,
                label_id=label_id,
                text=text,
                entities_json=entities_json,
            )
            update_row = session.run(
                UPDATE_TRAINING_CANDIDATE_STATUS,
                candidate_id=candidate_id,
                status="completed",
            ).single()
            if not update_row:
                raise HTTPException(
                    status_code=500, detail="Failed to update candidate status"
                )

        logger.info(
            "TrainingCandidate marked completed id=%s label=%s actor=%s",
            candidate_id[:12],
            str(gold_row.get("label_id", ""))[:12],
            getattr(scope, "email", "unknown"),
        )
        return {
            "candidate_id": update_row["candidate_id"],
            "status": update_row["status"],
            "gold_label_id": gold_row.get("label_id"),
        }
    finally:
        client.close()


def _run_active_learning_scoring(job_id: str) -> None:
    """Background: score pending candidates and write uncertainty_score."""
    import logging as _log

    log = _log.getLogger(__name__)
    log.info("[active-learning] Scoring job %s started", job_id)

    try:
        import spacy
        from libs.model_registry import ModelRegistry
        from libs.neo4j_client.client import KnowledgeGraphClient
        from libs.cypher.training_candidate_queries import (
            GET_PENDING_CANDIDATES_FOR_SCORING,
            SET_UNCERTAINTY_SCORE,
        )

        registry = ModelRegistry()
        promoted = registry.get_promoted_version()
        if not promoted:
            log.warning("[active-learning] No promoted model — skipping scoring")
            return

        from libs.model_store import ModelStore

        store = ModelStore()
        model_dir = store.download(promoted)
        nlp = spacy.load(str(model_dir))

        kg = KnowledgeGraphClient()
        try:
            with kg.session() as session:
                rows = list(session.run(GET_PENDING_CANDIDATES_FOR_SCORING))
        finally:
            kg.close()

        log.info("[active-learning] Scoring %d candidates", len(rows))

        for row in rows:
            text = str(row.get("text") or "")
            cid = str(row.get("candidate_id") or "")
            if not text or not cid:
                continue
            doc = nlp(text)
            score = _token_entropy(doc)
            kg2 = KnowledgeGraphClient()
            try:
                with kg2.session() as session:
                    session.run(SET_UNCERTAINTY_SCORE, candidate_id=cid, score=score)
            finally:
                kg2.close()

        log.info("[active-learning] Scoring job %s complete", job_id)
    except Exception as exc:
        log.exception("[active-learning] Scoring job %s failed: %s", job_id, exc)


def _token_entropy(doc) -> float:
    """Compute mean per-token NER entropy as an uncertainty measure."""
    import math

    if not doc or not hasattr(doc, "_"):
        return 0.0

    total = 0.0
    count = 0
    for token in doc:
        probs = getattr(token, "_.trf_data", None)
        if probs is None:
            continue
        for p in probs:
            if p > 0:
                total -= p * math.log(p + 1e-12)
            count += 1

    return round(total / count, 6) if count else 0.0


def _fetch_label_counts_for_scoring() -> dict[str, int]:
    """Return {LABEL: count} from verified gold labels for rarity scoring."""
    import json as _json
    from collections import Counter

    counter: Counter = Counter()
    kg = KnowledgeGraphClient()
    try:
        with kg.session() as session:
            rows = session.run(
                """
                MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
                WHERE c.status = 'completed' AND g.entities_json IS NOT NULL
                RETURN g.entities_json AS entities_json
                """
            )
            for row in rows:
                for ent in _json.loads(row["entities_json"] or "[]"):
                    raw = str(ent.get("label") or ent.get("semantic_tag") or "").upper()
                    if raw:
                        counter[raw] += 1
    finally:
        kg.close()
    return dict(counter)


def _rarity_for_candidate(
    entities_json: str | None,
    label_counts: dict[str, int],
) -> tuple[float, list[str]]:
    """Compute a [0,1] rarity score and list of rare labels for one candidate.

    Rarity = 1 / (1 + gold_count) for each entity label.  Labels with fewer
    gold examples produce a higher score.  A label never seen in gold gets
    the maximum score of 1.0.
    """
    import json as _json

    if not entities_json:
        return 0.0, []
    best = 0.0
    rare: list[str] = []
    for ent in _json.loads(entities_json or "[]"):
        label = str(ent.get("label") or ent.get("semantic_tag") or "").upper()
        if not label:
            continue
        count = label_counts.get(label, 0)
        r = 1.0 / (1.0 + count)
        if r > 0.1:
            rare.append(label)
        best = max(best, r)
    return round(best, 4), sorted(set(rare))
