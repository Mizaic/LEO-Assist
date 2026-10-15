"""Coding verifier subgraph: LLM semantic gate after SNOMED resolution.

Atlas trace:
  UN: UN-BF51F752
  DI: DI-0EC8620E
  Risk: R-EB42EB45

Runs after the terminology subgraph and before persist. For each entity that
has a resolved SNOMED code (terminology_unresolved=False), it asks an LLM
which shortlist entry is clinically appropriate, or to refuse every entry.

Surface-form exact matches bypass this gate: they are curated by a human
knowledge administrator and do not need LLM re-verification.

Verdicts applied per entity:
  accept       -- apply coding_candidates[selected_index]
  not_codeable -- drop code, mark terminology_unresolved=True so persist
                  skips the DOCUMENTS write
  reject_all   -- drop code; none of the shortlist entries are safe
  gate_failed  -- LLM call failed; keep code but force tier=1 (human review)
                  and stamp coding_verifier_verdict=gate_failed in entity
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.llm_client.coding_verifier import verify_coding_batch
from libs.pipeline.coding_candidate_gate import (
    apply_draft_from_shortlist,
    filter_coding_candidates,
)
from libs.pipeline.form_checkbox_seed import is_taught_checkbox
from libs.pipeline.form_schema_seeding import carries_taught_test_row_code
from libs.pipeline_graph.subgraphs.terminology import _is_blocked_mapping

logger = logging.getLogger(__name__)


class CodingVerifierState(TypedDict, total=False):
    entities: list[dict[str, Any]]
    encounter_text: str
    confidence_threshold: float
    errors: list[str]
    warnings: list[str]


def _is_exact_match(entity: dict[str, Any]) -> bool:
    """Return True when the entity was resolved via a curated surface form."""
    if entity.get("had_exact_match"):
        return True
    if str(entity.get("surface_form_status") or "").lower() in {"approved", "active"}:
        status_flag = entity.get("score", 0.0) >= 1.0
        if status_flag:
            return True
    return False


def _is_protected_coding(entity: dict[str, Any]) -> bool:
    """Taught form codes and remapped vulval ulcer must not be dropped."""
    if is_taught_checkbox(entity):
        return True
    if carries_taught_test_row_code(entity):
        return True
    return bool(entity.get("_vulval_ulcer_remapped"))


def _shortlist_for(entity: dict[str, Any]) -> list[dict[str, Any]]:
    if "coding_candidates" in entity:
        return [
            c for c in (entity.get("coding_candidates") or []) if isinstance(c, dict)
        ]
    if not entity.get("concept_id"):
        return []
    return [
        {
            "concept_id": entity.get("concept_id"),
            "term": entity.get("term"),
            "semantic_tag": entity.get("semantic_tag"),
            "score": entity.get("score"),
            "read_code": entity.get("read_code"),
            "had_exact_match": bool(entity.get("had_exact_match")),
        }
    ]


def _cheap_filter_entity(entity: dict[str, Any]) -> dict[str, Any]:
    filtered = filter_coding_candidates(
        entity,
        _shortlist_for(entity),
        is_blocked=_is_blocked_mapping,
    )
    drafted = apply_draft_from_shortlist(entity, filtered)
    if not filtered:
        drafted["coding_verifier_verdict"] = "cheap_reject"
    return drafted


def _apply_accept(
    entity: dict[str, Any],
    selected_index: int | None = None,
) -> dict[str, Any]:
    shortlist = _shortlist_for(entity)
    index = 0 if selected_index is None else selected_index
    if index < 0 or index >= len(shortlist):
        return _apply_reject_all(entity)
    drafted = apply_draft_from_shortlist(entity, shortlist)
    chosen = apply_draft_from_shortlist(drafted, [shortlist[index]])
    chosen["coding_candidates"] = shortlist
    chosen["coding_verifier_verdict"] = "accept"
    return chosen


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


def _apply_reject_all(entity: dict[str, Any]) -> dict[str, Any]:
    result = _apply_not_codeable(entity)
    result["coding_verifier_verdict"] = "reject_all"
    return result


def _apply_retry(
    entity: dict[str, Any],
    better_term: str | None,
    min_score: float,
) -> dict[str, Any]:
    """Legacy helper: retry re-resolve is retired. Leave the fact uncoded."""
    del better_term, min_score
    result = _apply_reject_all(entity)
    result["coding_verifier_verdict"] = "retry_retired"
    return result


def _prepare_for_verify(
    entities: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[int], list[dict[str, Any]]]:
    updated: list[dict[str, Any]] = []
    eligible_indices: list[int] = []
    eligible: list[dict[str, Any]] = []
    for i, ent in enumerate(entities):
        if ent.get("terminology_unresolved") and "coding_candidates" not in ent:
            updated.append(ent)
            continue
        filtered = _cheap_filter_entity(ent)
        updated.append(filtered)
        if filtered.get("terminology_unresolved") or not filtered.get("concept_id"):
            continue
        if _is_exact_match(filtered) or _is_protected_coding(filtered):
            continue
        eligible_indices.append(i)
        eligible.append(filtered)
    return updated, eligible_indices, eligible


def _apply_verdict(
    entity: dict[str, Any], verdict_row: dict[str, Any]
) -> dict[str, Any]:
    verdict = str(verdict_row.get("verdict") or "gate_failed")
    if verdict == "accept":
        return _apply_accept(entity, verdict_row.get("selected_index"))
    if verdict == "not_codeable":
        return _apply_not_codeable(entity)
    if verdict in {"reject_all", "retry"}:
        return _apply_reject_all(entity)
    return _apply_gate_failed(entity)


def _count_verdicts(updated: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"not_codeable": 0, "reject_all": 0, "cheap_reject": 0, "gate_failed": 0}
    for ent in updated:
        key = str(ent.get("coding_verifier_verdict") or "")
        if key in counts:
            counts[key] += 1
    return counts


def _verify_entities(state: CodingVerifierState) -> dict[str, Any]:
    entities = list(state.get("entities") or [])
    encounter_text = str(state.get("encounter_text") or "")
    errors: list[str] = list(state.get("errors") or [])
    warnings: list[str] = list(state.get("warnings") or [])
    if not entities:
        return {"entities": entities, "errors": errors, "warnings": warnings}

    updated, eligible_indices, eligible = _prepare_for_verify(entities)
    if eligible:
        verdicts = verify_coding_batch(eligible, encounter_text)
        for row, orig_idx in zip(verdicts, eligible_indices):
            updated[orig_idx] = _apply_verdict(updated[orig_idx], row)

    counts = _count_verdicts(updated)
    if counts["not_codeable"]:
        noun = "entity" if counts["not_codeable"] == 1 else "entities"
        warnings.append(
            f"coding_verifier: {counts['not_codeable']} {noun} classified not_codeable"
        )
    if counts["reject_all"] or counts["cheap_reject"]:
        dropped = counts["reject_all"] + counts["cheap_reject"]
        noun = "entity" if dropped == 1 else "entities"
        warnings.append(f"coding_verifier: {dropped} {noun} classified reject_all")
    if counts["gate_failed"]:
        noun = "entity" if counts["gate_failed"] == 1 else "entities"
        errors.append(
            f"coding_verifier: {counts['gate_failed']} {noun} gate_failed "
            f"(human review required)"
        )
    logger.info(
        "CodingVerifier: eligible=%d not_codeable=%d reject_all=%d gate_failed=%d",
        len(eligible),
        counts["not_codeable"],
        counts["reject_all"] + counts["cheap_reject"],
        counts["gate_failed"],
    )
    return {"entities": updated, "errors": errors, "warnings": warnings}


def build_coding_verifier_subgraph() -> CompiledStateGraph:
    graph = StateGraph(CodingVerifierState)
    graph.add_node("verify_entities", _verify_entities)
    graph.add_edge(START, "verify_entities")
    graph.add_edge("verify_entities", END)
    return graph.compile()
