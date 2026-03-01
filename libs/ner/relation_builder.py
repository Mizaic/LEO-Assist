"""Rule-based relation extraction for NER training records.

Extracts relations between entities in a single sentence using:
- Negation cue proximity rules  → negates
- Temporal modifier proximity   → temporal_of
- Finding/disorder co-occurrence → associated_finding
- Body-structure/disorder pairs → location_of
- Pathway milestone triggers    → triggers

Relations are added to canonical records produced by schema_mapper.
"""
from __future__ import annotations

import re
from typing import Any

from libs.ner.schema_mapper import (
    VALID_RELATION_TYPES,
    _stable_relation_id,
)

# ---------------------------------------------------------------------------
# Proximity window (in characters) for relation candidacy
# ---------------------------------------------------------------------------
_PROXIMITY_CHARS = 120

# Negation cue patterns (surface forms that negate the nearest clinical entity)
_NEGATION_CUE_LABELS: frozenset[str] = frozenset(
    {"X_NEGATION_CUE"}
)

_TEMPORAL_LABELS: frozenset[str] = frozenset(
    {"X_TEMPORAL"}
)

_CLINICAL_ENTITY_LABELS: frozenset[str] = frozenset(
    {
        "disorder",
        "finding",
        "procedure",
        "observable_entity",
        "substance",
        "situation",
    }
)

_BODY_STRUCTURE_LABELS: frozenset[str] = frozenset({"body_structure"})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity_mid(ent: dict[str, Any]) -> int:
    return (int(ent["start"]) + int(ent["end"])) // 2


def _proximity(a: dict[str, Any], b: dict[str, Any]) -> int:
    """Character distance between two entity spans (gap, 0 if overlapping)."""
    a_start, a_end = int(a["start"]), int(a["end"])
    b_start, b_end = int(b["start"]), int(b["end"])
    if a_end <= b_start:
        return b_start - a_end
    if b_end <= a_start:
        return a_start - b_end
    return 0


def _nearest_clinical(
    trigger: dict[str, Any],
    candidates: list[dict[str, Any]],
    max_dist: int = _PROXIMITY_CHARS,
) -> dict[str, Any] | None:
    """Return the closest clinical entity to `trigger` within `max_dist` chars."""
    best: dict[str, Any] | None = None
    best_dist = max_dist + 1
    for c in candidates:
        d = _proximity(trigger, c)
        if d < best_dist:
            best_dist = d
            best = c
    return best


# ---------------------------------------------------------------------------
# Relation builders
# ---------------------------------------------------------------------------


def _build_negation_relations(
    entities: list[dict[str, Any]],
    document_id: str,
) -> list[dict[str, Any]]:
    """Link each X_NEGATION_CUE to the nearest clinical entity."""
    rels: list[dict[str, Any]] = []
    negation_cues = [e for e in entities if e["label"] in _NEGATION_CUE_LABELS]
    clinical = [e for e in entities if e["label"] in _CLINICAL_ENTITY_LABELS]

    for cue in negation_cues:
        target = _nearest_clinical(cue, clinical, max_dist=80)
        if target:
            rid = _stable_relation_id(document_id, cue["entity_id"], target["entity_id"], "negates")
            rels.append(
                {
                    "relation_id": rid,
                    "type": "negates",
                    "head": cue["entity_id"],
                    "tail": target["entity_id"],
                }
            )
    return rels


def _build_temporal_relations(
    entities: list[dict[str, Any]],
    document_id: str,
) -> list[dict[str, Any]]:
    """Link each X_TEMPORAL modifier to its nearest clinical entity."""
    rels: list[dict[str, Any]] = []
    temporals = [e for e in entities if e["label"] in _TEMPORAL_LABELS]
    clinical = [e for e in entities if e["label"] in _CLINICAL_ENTITY_LABELS]

    for temp in temporals:
        target = _nearest_clinical(temp, clinical, max_dist=_PROXIMITY_CHARS)
        if target:
            rid = _stable_relation_id(document_id, temp["entity_id"], target["entity_id"], "temporal_of")
            rels.append(
                {
                    "relation_id": rid,
                    "type": "temporal_of",
                    "head": temp["entity_id"],
                    "tail": target["entity_id"],
                }
            )
    return rels


def _build_location_relations(
    entities: list[dict[str, Any]],
    document_id: str,
) -> list[dict[str, Any]]:
    """Link body_structure entities to adjacent disorders/findings."""
    rels: list[dict[str, Any]] = []
    body_parts = [e for e in entities if e["label"] in _BODY_STRUCTURE_LABELS]
    clinical = [
        e for e in entities
        if e["label"] in ("disorder", "finding") and e["label"] not in _BODY_STRUCTURE_LABELS
    ]

    seen: set[tuple[str, str]] = set()
    for bp in body_parts:
        target = _nearest_clinical(bp, clinical, max_dist=60)
        if target:
            key = (bp["entity_id"], target["entity_id"])
            if key not in seen:
                seen.add(key)
                rid = _stable_relation_id(document_id, bp["entity_id"], target["entity_id"], "location_of")
                rels.append(
                    {
                        "relation_id": rid,
                        "type": "location_of",
                        "head": bp["entity_id"],
                        "tail": target["entity_id"],
                    }
                )
    return rels


def _build_associated_finding_relations(
    entities: list[dict[str, Any]],
    document_id: str,
) -> list[dict[str, Any]]:
    """Link findings/observables to the nearest disorder in the sentence."""
    rels: list[dict[str, Any]] = []
    findings = [e for e in entities if e["label"] in ("finding", "observable_entity")]
    disorders = [e for e in entities if e["label"] == "disorder"]

    seen: set[tuple[str, str]] = set()
    for finding in findings:
        target = _nearest_clinical(finding, disorders, max_dist=_PROXIMITY_CHARS)
        if target:
            key = (finding["entity_id"], target["entity_id"])
            if key not in seen:
                seen.add(key)
                rid = _stable_relation_id(document_id, finding["entity_id"], target["entity_id"], "associated_finding")
                rels.append(
                    {
                        "relation_id": rid,
                        "type": "associated_finding",
                        "head": finding["entity_id"],
                        "tail": target["entity_id"],
                    }
                )
    return rels


def _build_trigger_relations(
    entities: list[dict[str, Any]],
    document_id: str,
) -> list[dict[str, Any]]:
    """Link findings/disorders to nearby pathway milestones as triggers."""
    rels: list[dict[str, Any]] = []
    milestones = [e for e in entities if e["label"] == "X_PATHWAY_MILESTONE"]
    triggers = [e for e in entities if e["label"] in ("finding", "disorder", "observable_entity")]

    seen: set[tuple[str, str]] = set()
    for ms in milestones:
        best = _nearest_clinical(ms, triggers, max_dist=_PROXIMITY_CHARS)
        if best:
            key = (best["entity_id"], ms["entity_id"])
            if key not in seen:
                seen.add(key)
                rid = _stable_relation_id(document_id, best["entity_id"], ms["entity_id"], "triggers")
                rels.append(
                    {
                        "relation_id": rid,
                        "type": "triggers",
                        "head": best["entity_id"],
                        "tail": ms["entity_id"],
                    }
                )
    return rels


# ---------------------------------------------------------------------------
# De-duplication of relations
# ---------------------------------------------------------------------------


def _dedupe_relations(
    relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove duplicate relations by (type, head, tail)."""
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for r in relations:
        key = (r["type"], r["head"], r["tail"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_relations(record: dict[str, Any]) -> dict[str, Any]:
    """Add inferred relations to a canonical record.

    Existing relations (e.g. from seed data) are preserved and merged with
    newly inferred ones.  Duplicate (type, head, tail) triplets are removed.

    Returns a new dict (does not mutate input).
    """
    record = dict(record)
    entities = list(record.get("entities") or [])
    doc_id = str(record.get("document_id") or "")
    existing = list(record.get("relations") or [])

    inferred: list[dict[str, Any]] = []
    inferred.extend(_build_negation_relations(entities, doc_id))
    inferred.extend(_build_temporal_relations(entities, doc_id))
    inferred.extend(_build_location_relations(entities, doc_id))
    inferred.extend(_build_associated_finding_relations(entities, doc_id))
    inferred.extend(_build_trigger_relations(entities, doc_id))

    all_relations = _dedupe_relations(existing + inferred)
    # Keep only valid relation types (safety guard)
    all_relations = [r for r in all_relations if r.get("type") in VALID_RELATION_TYPES]
    record["relations"] = all_relations
    return record
