"""Anchor domain review API endpoints.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")

Mirrors the pattern of routers/pipeline.py classification-review endpoints.

Routes
------
GET  /anchor-review/disagreements   — AnchorReview nodes where models disagreed
GET  /anchor-review/non-cancer      — Records flagged NON_CANCER by either model
POST /anchor-review/vote            — Record a human reviewer's domain verdict
GET  /anchor-review/scorecard       — Aggregate accuracy stats for both models
GET  /anchor-review/distribution    — Domain distribution across all reviewed records
GET  /anchor-review/target-rules    — Deduplicated TargetRules grouped by domain
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.deps import require_admin
from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/anchor-review", tags=["anchor-review"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class AnchorVoteRequest(BaseModel):
    encounter_id: str
    milestone_type: str
    correct_domain: str
    model_a_domain: str
    model_b_domain: str
    notes: str = ""
    reviewer: str = "unknown"


# ---------------------------------------------------------------------------
# GET /anchor-review/disagreements
# ---------------------------------------------------------------------------


@router.get("/disagreements")
async def get_anchor_disagreements(
    scope: CallerScope = Depends(require_admin),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=500),
) -> dict[str, Any]:
    """Return AnchorReview records where Haiku and GPT-5-mini disagreed on domain.

    Sorted with NON_CANCER flags first so the most clinically urgent records
    surface at the top.  Also returns pending count (no human vote yet).
    """
    from libs.cypher.anchor_review_queries import (
        GET_ALL_ANCHOR_DISAGREEMENTS,
        COUNT_ANCHOR_DISAGREEMENTS_PENDING,
    )

    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_ALL_ANCHOR_DISAGREEMENTS, skip=skip, limit=limit)
            disagreements = [dict(r) for r in rows]

            pending_result = session.run(COUNT_ANCHOR_DISAGREEMENTS_PENDING)
            pending_row = pending_result.single()
            pending_count = pending_row["pending_count"] if pending_row else 0

        return {
            "disagreements": disagreements,
            "total_returned": len(disagreements),
            "pending_review": pending_count,
            "skip": skip,
            "limit": limit,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# GET /anchor-review/non-cancer
# ---------------------------------------------------------------------------


@router.get("/non-cancer")
async def get_non_cancer_flags(
    scope: CallerScope = Depends(require_admin),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, le=500),
) -> dict[str, Any]:
    """Return all records flagged NON_CANCER by either model.

    These are records where label=1 in the training data but the LLM
    assigned NON_CANCER — indicating the upstream anchor detector is
    leaking non-cancer events into the cancer pathway (a precision problem).
    """
    from libs.cypher.anchor_review_queries import (
        GET_NON_CANCER_FLAGS,
        COUNT_NON_CANCER_PENDING,
    )

    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_NON_CANCER_FLAGS, skip=skip, limit=limit)
            flags = [dict(r) for r in rows]

            pending_result = session.run(COUNT_NON_CANCER_PENDING)
            pending_row = pending_result.single()
            pending_count = pending_row["pending_count"] if pending_row else 0

        return {
            "non_cancer_flags": flags,
            "total_returned": len(flags),
            "pending_review": pending_count,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# POST /anchor-review/vote
# ---------------------------------------------------------------------------


@router.post("/vote")
async def submit_anchor_vote(
    payload: AnchorVoteRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Record a human reviewer's verdict on an anchor domain disagreement.

    Writes an AnchorVote node and sets human_domain / human_corrected on
    the AnchorReview node so it no longer appears in the pending queue.
    """
    from libs.cypher.anchor_review_queries import UPSERT_ANCHOR_VOTE

    model_a_correct = payload.model_a_domain == payload.correct_domain
    model_b_correct = payload.model_b_domain == payload.correct_domain

    client = PatientGraphClient()
    try:
        with client.session() as session:
            result = session.run(
                UPSERT_ANCHOR_VOTE,
                encounter_id=payload.encounter_id,
                milestone_type=payload.milestone_type,
                correct_domain=payload.correct_domain,
                model_a_was_correct=model_a_correct,
                model_b_was_correct=model_b_correct,
                reviewer=payload.reviewer,
                notes=payload.notes,
                model_a_domain=payload.model_a_domain,
                model_b_domain=payload.model_b_domain,
            )
            row = result.single()

        return {
            "encounter_id": row["encounter_id"],
            "correct_domain": row["correct_domain"],
            "model_a_was_correct": model_a_correct,
            "model_b_was_correct": model_b_correct,
        }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# GET /anchor-review/scorecard
# ---------------------------------------------------------------------------


@router.get("/scorecard")
async def get_anchor_scorecard(
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Aggregate accuracy stats: how often each model was correct per human vote."""
    from libs.cypher.anchor_review_queries import GET_ANCHOR_SCORECARD

    client = PatientGraphClient()
    try:
        with client.session() as session:
            result = session.run(GET_ANCHOR_SCORECARD)
            row = result.single()
            if not row or row["total_votes"] == 0:
                return {
                    "model_a_label": "Claude Haiku (AWS)",
                    "model_b_label": "GPT-5-mini (Azure)",
                    "model_a_correct": 0,
                    "model_b_correct": 0,
                    "both_wrong": 0,
                    "total_votes": 0,
                    "model_a_accuracy_pct": 0.0,
                    "model_b_accuracy_pct": 0.0,
                }
            total = row["total_votes"]
            return {
                "model_a_label": "Claude Haiku (AWS)",
                "model_b_label": "GPT-5-mini (Azure)",
                "model_a_correct": row["model_a_correct"],
                "model_b_correct": row["model_b_correct"],
                "both_wrong": row["both_wrong"],
                "total_votes": total,
                "model_a_accuracy_pct": round(row["model_a_correct"] / total * 100, 1),
                "model_b_accuracy_pct": round(row["model_b_correct"] / total * 100, 1),
            }
    finally:
        client.close()


# ---------------------------------------------------------------------------
# GET /anchor-review/distribution
# ---------------------------------------------------------------------------


@router.get("/distribution")
async def get_domain_distribution(
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Domain distribution across all reviewed records, grouped by milestone."""
    from libs.cypher.anchor_review_queries import GET_ANCHOR_DOMAIN_DISTRIBUTION

    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_ANCHOR_DOMAIN_DISTRIBUTION)
            distribution = [dict(r) for r in rows]
        return {"distribution": distribution}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# GET /anchor-review/target-rules
# ---------------------------------------------------------------------------


@router.get("/target-rules")
async def get_target_rules(
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Return deduplicated medspaCy TargetRules from agreed/voted records.

    Rules are grouped by domain.  Only includes records where both models
    agreed OR a human vote has been recorded.  NON_CANCER and AMBIGUOUS
    domains are excluded (they produce no useful TargetRules).
    """
    from libs.cypher.anchor_review_queries import GET_REVIEWED_TARGET_RULES

    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_REVIEWED_TARGET_RULES)
            by_domain: dict[str, list[str]] = {}
            for row in rows:
                domain = row["domain"]
                rules: set[str] = set()
                for rule in (row.get("rules_a") or []) + (row.get("rules_b") or []):
                    if rule and rule.strip():
                        rules.add(rule.strip())
                by_domain[domain] = sorted(rules)

        return {
            "target_rules_by_domain": by_domain,
            "total_domains": len(by_domain),
            "total_rules": sum(len(v) for v in by_domain.values()),
        }
    finally:
        client.close()
