"""Confidence-gated TrainingCandidate pruning service.

Implements DI-LEO-AI-196 (UN-LEO-AI-083) -- a verdict ladder over
non-completed TrainingCandidate nodes that re-runs the SNOMED proposal
validator (DI-LEO-AI-186) over each candidate's persisted entities and
produces one of three verdicts:

  - 'keep'   -> every entity is accepted by the validator at the
                supplied confidence floors. Candidate stays for HITL
                review or training pickup.
  - 'delete' -> every entity is rejected AND no safety rail fires.
                Eligible for cascade DETACH DELETE.
  - 'review' -> any of:
                  * candidate has zero entities
                  * any entity carries an _AUTO_CODE_BLOCKED assertion
                    (absent / refuted / declined / cancelled / planned
                    / hypothetical / possible / historical / family)
                  * source startswith 'manual_gold_seed' (ground truth
                    must never be auto-pruned)
                  * mixed accept+reject across entities

Two phases are exposed: ``assess_candidates`` is read-only and returns
the verdict ladder for an explicit list of candidate rows; ``execute_prune``
takes the list of candidate IDs the caller wants to delete, re-fetches
each one to defend against TOCTOU between preview and execute, skips
anything that has reached status='completed', and cascades through to
DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS for the rest.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Sequence

from libs.coding_engine.tier_classifier import _AUTO_CODE_BLOCKED
from libs.cypher.training_candidate_queries import (
    DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS,
    GET_TRAINING_CANDIDATES_PAGE,
    GET_TRAINING_CANDIDATE_BY_ID,
)
from libs.terminology.client import TerminologyClient
from scripts.lib.gold_label_snomed_check import (
    ValidationResult,
    validate_proposal,
)

logger = logging.getLogger(__name__)

PruneVerdict = Literal["keep", "delete", "review"]

_DEFAULT_STATUSES: tuple[str, ...] = ("pending", "processing", "failed")
_MANUAL_SEED_PREFIX = "manual_gold_seed"
_DEFAULT_MAX_WORKERS = 8
_DEFAULT_LIMIT = 2000

# Safety-rail rejection-reason codes -- match these strings in tests and in
# the UI; do not reword without bumping the verification test pin.
SAFETY_RAIL_ZERO_ENTITIES = "zero_entities_safety_rail"
SAFETY_RAIL_BLOCKED_ASSERTION = "blocked_assertion_safety_rail"
SAFETY_RAIL_MANUAL_SEED = "manual_seed_safety_rail"


@dataclass(frozen=True)
class PruneParams:
    """Caller-supplied confidence floors and scope filters."""

    min_surface_match: float = 0.7
    semantic_vector_floor: float = 0.92
    semantic_min_surface: float = 0.66
    statuses: tuple[str, ...] = _DEFAULT_STATUSES
    limit: int = 500
    max_workers: int = _DEFAULT_MAX_WORKERS

    def validator_kwargs(self) -> dict[str, float]:
        return {
            "min_surface_match": float(self.min_surface_match),
            "semantic_vector_floor": float(self.semantic_vector_floor),
            "semantic_min_surface": float(self.semantic_min_surface),
        }


@dataclass
class CandidateAssessment:
    """One row of the preview / dry-run output."""

    candidate_id: str
    status: str
    source: str
    text: str
    entity_count: int
    accepted_count: int
    rejected_count: int
    blocked_assertion_count: int
    verdict: PruneVerdict
    rejection_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "status": self.status,
            "source": self.source,
            "text": self.text,
            "entity_count": self.entity_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "blocked_assertion_count": self.blocked_assertion_count,
            "verdict": self.verdict,
            "rejection_reasons": list(self.rejection_reasons),
        }


def _parse_entities(entities_json: Any) -> list[dict[str, Any]]:
    if isinstance(entities_json, list):
        return [e for e in entities_json if isinstance(e, dict)]
    if not isinstance(entities_json, str) or not entities_json.strip():
        return []
    try:
        parsed = json.loads(entities_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [e for e in parsed if isinstance(e, dict)]


def _has_blocked_assertion(entities: Sequence[dict[str, Any]]) -> int:
    """Count entities whose assertion is in _AUTO_CODE_BLOCKED."""
    n = 0
    for ent in entities:
        assertion = str(ent.get("assertion") or "").strip().lower()
        if assertion in _AUTO_CODE_BLOCKED:
            n += 1
    return n


def _entity_label(ent: dict[str, Any]) -> str:
    """Return the validator-relevant label for an entity row.

    Prefers the explicit ``label`` field; falls back to ``semantic_tag``
    (legacy rows occasionally only carry the SNOMED tag).
    """
    label = str(ent.get("label") or "").strip()
    if label:
        return label
    return str(ent.get("semantic_tag") or "").strip()


def _entity_text(ent: dict[str, Any]) -> str:
    return str(ent.get("text") or "").strip()


def _classify(
    *,
    candidate: dict[str, Any],
    validator_results: list[ValidationResult],
    blocked_assertion_count: int,
) -> CandidateAssessment:
    entities = _parse_entities(candidate.get("entities_json"))
    source = str(candidate.get("source") or "")
    candidate_id = str(candidate.get("candidate_id") or "")
    status = str(candidate.get("status") or "")
    text = str(candidate.get("text") or "")

    rejection_reasons: list[str] = []
    accepted_count = sum(1 for r in validator_results if r.accepted)
    rejected_count = sum(1 for r in validator_results if not r.accepted)
    rejection_reasons.extend(
        sorted({r.reason for r in validator_results if not r.accepted})
    )

    # Safety-rail short-circuits: any of these forces verdict='review'.
    if not entities:
        return CandidateAssessment(
            candidate_id=candidate_id,
            status=status,
            source=source,
            text=text,
            entity_count=0,
            accepted_count=0,
            rejected_count=0,
            blocked_assertion_count=0,
            verdict="review",
            rejection_reasons=[SAFETY_RAIL_ZERO_ENTITIES],
        )
    if blocked_assertion_count > 0:
        rejection_reasons.insert(0, SAFETY_RAIL_BLOCKED_ASSERTION)
        return CandidateAssessment(
            candidate_id=candidate_id,
            status=status,
            source=source,
            text=text,
            entity_count=len(entities),
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            blocked_assertion_count=blocked_assertion_count,
            verdict="review",
            rejection_reasons=rejection_reasons,
        )
    if source.startswith(_MANUAL_SEED_PREFIX):
        rejection_reasons.insert(0, SAFETY_RAIL_MANUAL_SEED)
        return CandidateAssessment(
            candidate_id=candidate_id,
            status=status,
            source=source,
            text=text,
            entity_count=len(entities),
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            blocked_assertion_count=blocked_assertion_count,
            verdict="review",
            rejection_reasons=rejection_reasons,
        )

    # Now the validator-driven verdict ladder.
    if accepted_count == 0 and rejected_count > 0:
        verdict: PruneVerdict = "delete"
    elif rejected_count == 0 and accepted_count > 0:
        verdict = "keep"
    else:
        verdict = "review"

    return CandidateAssessment(
        candidate_id=candidate_id,
        status=status,
        source=source,
        text=text,
        entity_count=len(entities),
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        blocked_assertion_count=0,
        verdict=verdict,
        rejection_reasons=rejection_reasons,
    )


def _validate_one_candidate(
    candidate: dict[str, Any],
    terminology: TerminologyClient,
    params: PruneParams,
) -> CandidateAssessment:
    entities = _parse_entities(candidate.get("entities_json"))
    blocked = _has_blocked_assertion(entities)

    if not entities:
        return _classify(
            candidate=candidate, validator_results=[], blocked_assertion_count=0
        )

    # Fast-path: a safety rail is going to fire, so we don't need to
    # spend resolver calls on this candidate's entities.
    source = str(candidate.get("source") or "")
    if blocked > 0 or source.startswith(_MANUAL_SEED_PREFIX):
        return _classify(
            candidate=candidate,
            validator_results=[],
            blocked_assertion_count=blocked,
        )

    results: list[ValidationResult] = []
    kwargs = params.validator_kwargs()
    for ent in entities:
        text = _entity_text(ent)
        label = _entity_label(ent)
        if not text or not label:
            results.append(
                ValidationResult(
                    accepted=False,
                    reason="empty_input",
                    surface_text=text,
                    proposed_label=label,
                )
            )
            continue
        try:
            results.append(
                validate_proposal(text, label, terminology, **kwargs)
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "validator failed for candidate=%s text=%r label=%s",
                candidate.get("candidate_id"),
                text[:80],
                label,
            )
            results.append(
                ValidationResult(
                    accepted=False,
                    reason="resolver_error",
                    surface_text=text,
                    proposed_label=label,
                )
            )
    return _classify(
        candidate=candidate,
        validator_results=results,
        blocked_assertion_count=blocked,
    )


def fetch_non_completed_candidates(
    client: Any,
    *,
    statuses: Iterable[str],
    limit: int,
) -> list[dict[str, Any]]:
    """Fetch candidate rows for the configured statuses.

    Always excludes ``status='completed'`` -- callers cannot accidentally
    target gold rows by passing 'completed' in ``statuses``.
    """
    safe_statuses = [s for s in statuses if s and s != "completed"]
    if not safe_statuses:
        safe_statuses = list(_DEFAULT_STATUSES)
    safe_limit = max(1, min(int(limit or _DEFAULT_LIMIT), _DEFAULT_LIMIT))
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    with client.session() as session:
        for status in safe_statuses:
            result = session.run(
                GET_TRAINING_CANDIDATES_PAGE,
                status=status,
                exclude_completed=True,
                source=None,
                search=None,
                skip=0,
                limit=safe_limit,
            )
            for row in result:
                row_dict = dict(row)
                cid = str(row_dict.get("candidate_id") or "")
                if not cid or cid in seen_ids:
                    continue
                seen_ids.add(cid)
                rows.append(row_dict)
                if len(rows) >= safe_limit:
                    return rows
    return rows


def assess_candidates(
    client: Any,
    terminology: TerminologyClient,
    params: PruneParams,
    *,
    candidates: Sequence[dict[str, Any]] | None = None,
) -> list[CandidateAssessment]:
    """Run the verdict ladder over ``candidates`` (or fetch them).

    ``client`` is a ``KnowledgeGraphClient`` used only to fetch
    candidates when ``candidates`` is None. The function never mutates.
    """
    rows = (
        list(candidates)
        if candidates is not None
        else fetch_non_completed_candidates(
            client, statuses=params.statuses, limit=params.limit
        )
    )
    if not rows:
        return []

    workers = max(1, min(int(params.max_workers), _DEFAULT_MAX_WORKERS))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_validate_one_candidate, row, terminology, params)
            for row in rows
        ]
        return [f.result() for f in futures]


@dataclass
class ExecuteOutcome:
    requested: list[str]
    deleted: list[str]
    skipped_completed: list[str]
    not_found: list[str]
    cascade_counts: dict[str, dict[str, int]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested": list(self.requested),
            "deleted": list(self.deleted),
            "skipped_completed": list(self.skipped_completed),
            "not_found": list(self.not_found),
            "cascade_counts": dict(self.cascade_counts),
        }


def execute_prune(client: Any, candidate_ids: Sequence[str]) -> ExecuteOutcome:
    """Delete the supplied candidates after a TOCTOU re-check.

    For each id:
      * fetch the current row -- if missing, append to ``not_found``;
      * if status='completed', append to ``skipped_completed`` and
        do NOT delete (gold record protection);
      * otherwise call DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS and
        record the cascade counts.
    """
    requested = [str(c) for c in candidate_ids if c]
    deleted: list[str] = []
    skipped_completed: list[str] = []
    not_found: list[str] = []
    cascade_counts: dict[str, dict[str, int]] = {}

    if not requested:
        return ExecuteOutcome(
            requested=[],
            deleted=[],
            skipped_completed=[],
            not_found=[],
            cascade_counts={},
        )

    with client.session() as session:
        for cid in requested:
            row = session.run(
                GET_TRAINING_CANDIDATE_BY_ID, candidate_id=cid
            ).single()
            if not row:
                not_found.append(cid)
                continue
            current_status = str(dict(row).get("status") or "")
            if current_status == "completed":
                skipped_completed.append(cid)
                continue
            del_row = session.run(
                DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS, candidate_id=cid
            ).single()
            if not del_row:
                not_found.append(cid)
                continue
            del_payload = dict(del_row)
            cascade_counts[cid] = {
                "gold_labels_deleted": int(
                    del_payload.get("gold_labels_deleted") or 0
                ),
                "surface_form_tasks_deleted": int(
                    del_payload.get("surface_form_tasks_deleted") or 0
                ),
            }
            deleted.append(cid)

    return ExecuteOutcome(
        requested=requested,
        deleted=deleted,
        skipped_completed=skipped_completed,
        not_found=not_found,
        cascade_counts=cascade_counts,
    )


def summarise(assessments: Iterable[CandidateAssessment]) -> dict[str, Any]:
    """Aggregate counts by verdict for a preview response payload."""
    by_verdict: dict[str, int] = {"keep": 0, "delete": 0, "review": 0}
    by_rejection: dict[str, int] = {}
    total_entities = 0
    total_accepted = 0
    total_rejected = 0
    n = 0
    for a in assessments:
        n += 1
        by_verdict[a.verdict] = by_verdict.get(a.verdict, 0) + 1
        total_entities += a.entity_count
        total_accepted += a.accepted_count
        total_rejected += a.rejected_count
        for reason in a.rejection_reasons:
            by_rejection[reason] = by_rejection.get(reason, 0) + 1
    return {
        "candidate_count": n,
        "by_verdict": by_verdict,
        "by_rejection_reason": by_rejection,
        "entity_total": total_entities,
        "entity_accepted": total_accepted,
        "entity_rejected": total_rejected,
    }
