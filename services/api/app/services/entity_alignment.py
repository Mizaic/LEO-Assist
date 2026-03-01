"""Multi-model entity alignment and consensus confidence scoring.

After each model independently extracts entities and resolves them to SNOMED,
this module aligns entities across models and computes composite confidence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AlignedEntity:
    """A single entity with consensus scores from multiple models."""
    sentence_id: str
    snomed_concept_id: str | None
    snomed_term: str | None
    text: str
    lookup_term: str
    semantic_tag: str
    assertion: str
    read_code: str | None = None
    coding_source: str | None = None
    coding_score: float = 0.0

    extraction_agreement: float = 0.0
    coding_margin: float = 0.0
    disambiguation_agreement: float = 0.0
    read_code_corroboration: float = 0.0
    consensus_confidence: float = 0.0

    model_extractions: list[dict[str, Any]] = field(default_factory=list)
    model_count: int = 0
    total_models: int = 0


@dataclass
class ConsensusResult:
    """Result of multi-model consensus for an encounter."""
    encounter_id: str
    aligned_entities: list[AlignedEntity] = field(default_factory=list)
    encounter_confidence: float = 0.0
    model_ids: list[str] = field(default_factory=list)


def _jaccard_tokens(a: str, b: str) -> float:
    """Token-level Jaccard similarity."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _compute_entity_confidence(
    entity: AlignedEntity,
    has_inline_read_code: bool = False,
) -> float:
    """Composite confidence per configured weighting."""
    read_corr = 1.0 if has_inline_read_code else entity.read_code_corroboration
    return (
        0.35 * entity.extraction_agreement
        + 0.30 * entity.coding_margin
        + 0.20 * entity.disambiguation_agreement
        + 0.15 * read_corr
    )


def _compute_encounter_confidence(entities: list[AlignedEntity]) -> float:
    """10th-percentile confidence."""
    if not entities:
        return 0.0
    scores = sorted(e.consensus_confidence for e in entities)
    idx = max(0, len(scores) // 10)
    return scores[idx]


def align_extractions(
    model_results: list[dict[str, Any]],
    encounter_id: str = "",
    model_ids: list[str] | None = None,
) -> ConsensusResult:
    """Align entities from multiple models into a consensus set."""
    total_models = len(model_results)
    model_ids = model_ids or [f"model_{i}" for i in range(total_models)]

    entity_map: dict[str, AlignedEntity] = {}

    for model_idx, result in enumerate(model_results):
        terms = result.get("terms", [])
        for term in terms:
            sid = term.get("sentence_id", "")
            coding = term.get("coding", {})
            concept_id = coding.get("snomed_concept_id")

            if concept_id:
                key = f"{sid}::{concept_id}"
            else:
                key = None

            if key and key in entity_map:
                entity_map[key].model_extractions.append(
                    {"model_idx": model_idx, "model_id": model_ids[model_idx], **term}
                )
                entity_map[key].model_count += 1
                continue

            if not key:
                key = _find_text_match(entity_map, sid, term)

            if key and key in entity_map:
                entity_map[key].model_extractions.append(
                    {"model_idx": model_idx, "model_id": model_ids[model_idx], **term}
                )
                entity_map[key].model_count += 1
                continue

            if not key:
                text_norm = term.get("text", "").lower().replace(" ", "_")[:30]
                key = f"{sid}::{text_norm}_{model_idx}"

            entity_map[key] = AlignedEntity(
                sentence_id=sid,
                snomed_concept_id=concept_id,
                snomed_term=coding.get("snomed_term"),
                text=term.get("text", ""),
                lookup_term=term.get("lookup_term", ""),
                semantic_tag=term.get("semantic_tag", ""),
                assertion=term.get("assertion", "present"),
                read_code=coding.get("read_code"),
                coding_source=coding.get("source"),
                coding_score=float(coding.get("score", 0)),
                model_extractions=[
                    {"model_idx": model_idx, "model_id": model_ids[model_idx], **term}
                ],
                model_count=1,
                total_models=total_models,
            )

    entities = list(entity_map.values())
    for entity in entities:
        entity.total_models = total_models
        entity.extraction_agreement = entity.model_count / total_models

        if entity.coding_score > 0:
            entity.coding_margin = min(1.0, entity.coding_score)
        else:
            entity.coding_margin = 0.0

        assertions = [e.get("assertion", "present") for e in entity.model_extractions]
        if assertions:
            most_common = max(set(assertions), key=assertions.count)
            entity.assertion = most_common
            entity.disambiguation_agreement = assertions.count(most_common) / len(assertions)

        has_read_code = bool(entity.read_code)
        entity.consensus_confidence = _compute_entity_confidence(entity, has_read_code)

    encounter_confidence = _compute_encounter_confidence(entities)

    logger.info(
        "Consensus for %s: %d entities, encounter_confidence=%.2f",
        encounter_id, len(entities), encounter_confidence,
    )

    return ConsensusResult(
        encounter_id=encounter_id,
        aligned_entities=entities,
        encounter_confidence=encounter_confidence,
        model_ids=model_ids,
    )


def _find_text_match(
    entity_map: dict[str, AlignedEntity],
    sentence_id: str,
    term: dict[str, Any],
) -> str | None:
    """Fall back to text-level matching when SNOMED is unavailable."""
    text = term.get("text", "")
    tag = term.get("semantic_tag", "")

    best_key: str | None = None
    best_score = 0.0

    for key, entity in entity_map.items():
        if entity.sentence_id != sentence_id:
            continue
        if entity.semantic_tag != tag:
            continue
        score = _jaccard_tokens(text, entity.text)
        if score > 0.6 and score > best_score:
            best_score = score
            best_key = key

    return best_key
