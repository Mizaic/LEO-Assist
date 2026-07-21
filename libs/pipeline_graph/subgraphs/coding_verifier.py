"""Coding verifier subgraph: LLM semantic gate after SNOMED resolution.

Atlas trace:
  UN: UN-BF51F752
  DI: DI-0EC8620E
  Risk: R-EB42EB45

Runs after the terminology subgraph and before persist. For each entity that
has a resolved SNOMED code (terminology_unresolved=False), it asks an LLM
whether the code is clinically appropriate for the entity in context.

Surface-form exact matches bypass this gate: they are curated by a human
knowledge administrator and do not need LLM re-verification.

Verdicts applied per entity:
  accept       -- keep resolved code as-is
  not_codeable -- drop code, mark terminology_unresolved=True so persist
                  skips the DOCUMENTS write
  retry        -- re-resolve with the LLM's suggested cleaner term; accept
                  only if new score >= confidence threshold
  gate_failed  -- LLM call failed; keep code but force tier=1 (human review)
                  and stamp coding_verifier_verdict=gate_failed in entity
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.llm_client.coding_verifier import verify_coding_batch
from libs.terminology.client import TerminologyClient

logger = logging.getLogger(__name__)

_DEFAULT_MIN_SCORE = 0.55

_EXACT_MATCH_SIGNALS = frozenset(
    {"had_exact_match", "surface_form_status"}
)


class CodingVerifierState(TypedDict, total=False):
    entities: list[dict[str, Any]]
    encounter_text: str
    confidence_threshold: float
    errors: list[str]


def _is_exact_match(entity: dict[str, Any]) -> bool:
    """Return True when the entity was resolved via a curated surface form."""
    if entity.get("had_exact_match"):
        return True
    if str(entity.get("surface_form_status") or "").lower() in {"approved", "active"}:
        status_flag = entity.get("score", 0.0) >= 1.0
        if status_flag:
            return True
    return False


def _apply_accept(entity: dict[str, Any]) -> dict[str, Any]:
    result = dict(entity)
    result["coding_verifier_verdict"] = "accept"
    return result


def _apply_not_codeable(entity: dict[str, Any]) -> dict[str, Any]:
    result = dict(entity)
    result["terminology_unresolved"] = True
    result["concept_id"] = None
    result["term"] = None
    result["read_code"] = None
    result["score"] = 0.0
    result["coding_verifier_verdict"] = "not_codeable"
    return result


def _apply_gate_failed(entity: dict[str, Any]) -> dict[str, Any]:
    result = dict(entity)
    result["coding_verifier_verdict"] = "gate_failed"
    # Force tier=1: the caller (tier classifier / persist) should use
    # coding_verifier_verdict to route this entity to mandatory human review.
    result["verifier_tier_override"] = 1
    return result


def _apply_retry(
    entity: dict[str, Any],
    better_term: str | None,
    min_score: float,
) -> dict[str, Any]:
    if not better_term:
        logger.info(
            "CodingVerifier retry for %r: no better_term supplied, marking unresolved",
            entity.get("text"),
        )
        result = _apply_not_codeable(entity)
        result["coding_verifier_verdict"] = "retry_no_term"
        return result

    try:
        results = TerminologyClient().resolve(
            [better_term],
            expected_tags={better_term: str(entity.get("semantic_tag") or "")},
        )
        candidates = results.get(better_term, [])
        if not candidates or candidates[0].score < min_score:
            logger.info(
                "CodingVerifier retry for %r with %r: no adequate match (score=%.4f)",
                entity.get("text"),
                better_term,
                candidates[0].score if candidates else 0.0,
            )
            result = _apply_not_codeable(entity)
            result["coding_verifier_verdict"] = "retry_no_match"
            return result
        best = candidates[0]
        result = dict(entity)
        result.update(
            concept_id=best.concept_id,
            term=best.term,
            semantic_tag=best.semantic_tag,
            score=round(best.score, 4),
            read_code=best.read_code,
            terminology_unresolved=False,
            coding_verifier_verdict="retry_accepted",
            lookup_term=better_term,
        )
        logger.info(
            "CodingVerifier retry for %r: %r -> %r (score %.4f)",
            entity.get("text"),
            better_term,
            best.term,
            best.score,
        )
        return result
    except Exception as exc:
        logger.exception("CodingVerifier retry resolution failed for %r", entity.get("text"))
        result = _apply_gate_failed(entity)
        result["coding_verifier_verdict"] = f"retry_error:{exc}"
        return result


def _verify_entities(state: CodingVerifierState) -> dict[str, Any]:
    entities = list(state.get("entities") or [])
    encounter_text = str(state.get("encounter_text") or "")
    errors: list[str] = list(state.get("errors") or [])
    min_score = float(state.get("confidence_threshold") or _DEFAULT_MIN_SCORE)

    if not entities:
        return {"entities": entities, "errors": errors}

    eligible_indices: list[int] = []
    eligible_entities: list[dict[str, Any]] = []

    for i, ent in enumerate(entities):
        if ent.get("terminology_unresolved") or not ent.get("concept_id"):
            continue
        if _is_exact_match(ent):
            continue
        eligible_indices.append(i)
        eligible_entities.append(ent)

    if not eligible_entities:
        return {"entities": entities, "errors": errors}

    verdicts = verify_coding_batch(eligible_entities, encounter_text)

    updated = list(entities)
    not_codeable_count = 0
    retry_count = 0
    gate_failed_count = 0

    for v, ent, orig_idx in zip(verdicts, eligible_entities, eligible_indices):
        verdict = v.get("verdict", "gate_failed")
        if verdict == "accept":
            updated[orig_idx] = _apply_accept(ent)
        elif verdict == "not_codeable":
            updated[orig_idx] = _apply_not_codeable(ent)
            not_codeable_count += 1
        elif verdict == "retry":
            updated[orig_idx] = _apply_retry(ent, v.get("better_term"), min_score)
            retry_count += 1
        else:
            updated[orig_idx] = _apply_gate_failed(ent)
            gate_failed_count += 1

    if not_codeable_count:
        errors.append(
            f"coding_verifier: {not_codeable_count} entity/entities classified not_codeable"
        )
    if gate_failed_count:
        errors.append(
            f"coding_verifier: {gate_failed_count} entity/entities gate_failed (human review required)"
        )

    logger.info(
        "CodingVerifier: %d eligible, not_codeable=%d retry=%d gate_failed=%d",
        len(eligible_entities),
        not_codeable_count,
        retry_count,
        gate_failed_count,
    )

    return {"entities": updated, "errors": errors}


def build_coding_verifier_subgraph() -> CompiledStateGraph:
    graph = StateGraph(CodingVerifierState)
    graph.add_node("verify_entities", _verify_entities)
    graph.add_edge(START, "verify_entities")
    graph.add_edge("verify_entities", END)
    return graph.compile()
