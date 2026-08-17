"""Ontology-aware relation policy helpers.

Atlas trace:
  DO: DO-8E641A9E
  Also: DO-236545C8
  DI: DI-6ACD24D2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8E641A9E")

This module centralises relation allowlists and compatibility checks used by:
- gold review UI/API validation
- runtime relation linking
- relation training data export
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
        source=("qualifier_value",),
        target=("finding", "disorder", "procedure"),
        relation_type="qualifies",
        snomed_relationships=("METHOD", "HAS_INTERPRETATION", "ASSOCIATED_FINDING"),
        severity="warning",
    ),
    RelationRule(
        source=("finding", "disorder", "situation"),
        target=("substance", "product"),
        relation_type="causative_agent",
        snomed_relationships=("CAUSATIVE_AGENT",),
    ),
)

_POLICY_RELATION_TYPES: frozenset[str] = frozenset(
    rule.relation_type for rule in RELATION_POLICY_RULES
)
DEFAULT_RUNTIME_RELATION_TYPES: frozenset[str] = frozenset(
    {
        "finding_site",
        "interprets",
        "component_of",
        "causative_agent",
    }
)
_runtime_extra: frozenset[str] = frozenset()
_fact_link_loaded = False


def policy_relation_types() -> frozenset[str]:
    """All types gold review and extraction-check may still store."""
    return _POLICY_RELATION_TYPES


def allowed_relation_types() -> frozenset[str]:
    """Relation types the runtime linker may apply."""
    _ensure_fact_link_loaded()
    return DEFAULT_RUNTIME_RELATION_TYPES | _runtime_extra


def _fetch_fact_link_rows() -> list[dict]:
    try:
        from libs.pipeline.config_loader import _fetch_neo4j_rules

        return _fetch_neo4j_rules("fact_link_guard")
    except Exception:
        logger.warning(
            "Could not fetch Neo4j fact-link guard rules -- using defaults",
            exc_info=True,
        )
        return []


def reload_fact_link_guard() -> None:
    """Add custom allowed_relation patterns from Neo4j to the runtime set."""
    global _runtime_extra, _fact_link_loaded
    extras: set[str] = set()
    for row in _fetch_fact_link_rows():
        if not row.get("active", True):
            continue
        if str(row.get("rule_type") or "") != "allowed_relation":
            continue
        rel = _norm(str(row.get("pattern") or ""))
        if rel:
            extras.add(rel)
    _runtime_extra = frozenset(extras)
    _fact_link_loaded = True
    logger.info("Fact-link guard reloaded: %d extra types", len(_runtime_extra))


def _ensure_fact_link_loaded() -> None:
    if not _fact_link_loaded:
        reload_fact_link_guard()


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
        if rel_type not in _POLICY_RELATION_TYPES:
            continue
        if (
            not isinstance(target_idx, int)
            or target_idx < 0
            or target_idx >= entities_count
        ):
            continue
        confidence = float(raw.get("confidence") or 0.6)
        row = {
            "type": rel_type,
            "target_idx": target_idx,
            "target_text": str(raw.get("target_text") or "").strip(),
            "confidence": confidence,
        }
        method = str(raw.get("extraction_method") or "").strip()
        if method:
            row["extraction_method"] = method
        key = (rel_type, target_idx)
        prev = dedup.get(key)
        if prev is None or float(prev.get("confidence") or 0.0) < confidence:
            dedup[key] = row
    return list(dedup.values())
