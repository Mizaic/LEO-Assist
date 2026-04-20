"""Ontology-aware relation policy helpers.

Atlas trace:
  DO: DO-236545C8
  DI: DI-2D9F5064
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

This module centralises relation allowlists and compatibility checks used by:
- gold review UI/API validation
- runtime relation linking
- relation training data export
"""

from __future__ import annotations

from dataclasses import dataclass


def _norm(value: str | None) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


@dataclass(frozen=True)
class RelationRule:
    source: tuple[str, ...]
    target: tuple[str, ...]
    relation_type: str
    snomed_relationships: tuple[str, ...]
    severity: str = "error"


RELATION_POLICY_RULES: tuple[RelationRule, ...] = (
    RelationRule(
        source=("finding", "disorder", "situation", "procedure"),
        target=("body_structure",),
        relation_type="finding_site",
        snomed_relationships=("FINDING_SITE", "PROCEDURE_SITE"),
    ),
    RelationRule(
        source=("finding",),
        target=("observable_entity",),
        relation_type="interprets",
        snomed_relationships=("INTERPRETS",),
    ),
    RelationRule(
        source=("observable_entity",),
        target=("procedure",),
        relation_type="component_of",
        snomed_relationships=("HAS_COMPONENT",),
        severity="warning",
    ),
    RelationRule(
        source=("finding",),
        target=("disorder", "finding"),
        relation_type="associated_finding",
        snomed_relationships=("HAS_ASSOCIATED_FINDING",),
    ),
    RelationRule(
        source=("qualifier_value", "finding"),
        target=("finding", "disorder", "procedure"),
        relation_type="qualifies",
        snomed_relationships=("METHOD", "HAS_INTERPRETATION", "ASSOCIATED_FINDING"),
        severity="warning",
    ),
)

_ALLOWED_RELATION_TYPES: frozenset[str] = frozenset(
    rule.relation_type for rule in RELATION_POLICY_RULES
)


def allowed_relation_types() -> frozenset[str]:
    """Return relation types accepted by policy."""
    return _ALLOWED_RELATION_TYPES


def _match_label(label: str, candidates: tuple[str, ...]) -> bool:
    label_norm = _norm(label)
    return label_norm in {_norm(item) for item in candidates}


def is_relation_allowed(
    *,
    source_label: str | None,
    target_label: str | None,
    relation_type: str | None,
) -> tuple[bool, str]:
    """Validate relation against semantic-tag policy.

    Returns (allowed, severity) where severity is "error" or "warning".
    """
    rel = _norm(relation_type)
    src = _norm(source_label)
    tgt = _norm(target_label)
    if not rel or not src or not tgt:
        return False, "error"
    for rule in RELATION_POLICY_RULES:
        if rel != _norm(rule.relation_type):
            continue
        if _match_label(src, rule.source) and _match_label(tgt, rule.target):
            return True, rule.severity
    return False, "error"


def canonicalise_relations(
    relations: list[dict] | None,
    entities_count: int,
) -> list[dict]:
    """Normalise and deduplicate relation rows by (type, target_idx)."""
    if not relations:
        return []
    dedup: dict[tuple[str, int], dict] = {}
    for raw in relations:
        if not isinstance(raw, dict):
            continue
        rel_type = _norm(raw.get("type"))
        target_idx = raw.get("target_idx")
        if rel_type not in _ALLOWED_RELATION_TYPES:
            continue
        if not isinstance(target_idx, int) or target_idx < 0 or target_idx >= entities_count:
            continue
        confidence = float(raw.get("confidence") or 0.6)
        row = {
            "type": rel_type,
            "target_idx": target_idx,
            "target_text": str(raw.get("target_text") or "").strip(),
            "confidence": confidence,
        }
        key = (rel_type, target_idx)
        prev = dedup.get(key)
        if prev is None or float(prev.get("confidence") or 0.0) < confidence:
            dedup[key] = row
    return list(dedup.values())
