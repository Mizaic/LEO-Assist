"""Filtering and span-realignment helpers for the GoldLabel export pipeline.

Atlas trace:
  DO: DO-16CE412B
  DI: DI-FE1BC901
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-16CE412B")

Shared between the training worker (label_exporter.py) and the read-only
API diagnostics endpoint so dropped entities can be inspected on demand
without triggering a full training export.

No spaCy dependency -- only the lightweight span_finder regex helper.
"""

from __future__ import annotations

import json
import os
from typing import Any

# Empty by default.
#
# The spancat model is trained on span boundaries + entity label only
# (start, end, label).  Assertions (negated / hypothetical / etc.) are NOT
# part of the training signal -- they are applied by the ConText engine
# post-extraction.  Filtering by assertion therefore removes training
# examples without any benefit to the model, reducing recall.
#
# Set the TRAINING_EXCLUDE_ASSERTIONS env var (comma-separated) if you
# explicitly want to hold out specific assertion values.
DEFAULT_EXCLUDED_ASSERTIONS: frozenset[str] = frozenset()


def get_excluded_assertions() -> set[str]:
    """Return assertion values to exclude, from env or defaults."""
    raw = os.getenv("TRAINING_EXCLUDE_ASSERTIONS", "")
    if raw.strip():
        return {a.strip().lower() for a in raw.split(",") if a.strip()}
    return set(DEFAULT_EXCLUDED_ASSERTIONS)


def realign_entity(text: str, ent: dict[str, Any]) -> dict[str, Any] | None:
    """Re-derive start/end from the entity surface text.

    Returns a corrected entity dict, or None if the surface text is not found.
    """
    from libs.ner.span_finder import find_span

    surface = str(ent.get("text", "")).strip()
    if not surface:
        return None
    result = find_span(text, surface)
    if result is None:
        return None
    start, end = result
    return {**ent, "text": text[start:end], "start": start, "end": end}


def repair_entity_spans(
    text: str,
    entities: list[dict[str, Any]],
    *,
    drop_unrepairable: bool = False,
) -> dict[str, Any]:
    """Repair entity spans without silently losing unresolved entities."""

    repaired_entities: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "repaired": [],
        "unchanged": [],
        "unrepairable": [],
        "ambiguous": [],
        "entities": repaired_entities,
    }
    for index, ent in enumerate(entities):
        decision = _repair_one_entity(text, ent, index)
        report[decision["status"]].append(decision)
        if decision["status"] == "repaired":
            repaired_entities.append(decision["entity"])
            continue
        if decision["status"] == "unrepairable" and drop_unrepairable:
            continue
        repaired_entities.append(ent)
    return report


def _repair_one_entity(
    text: str,
    ent: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    from libs.ner.span_finder import find_span, find_span_candidates

    surface = str(ent.get("text", "")).strip()
    base = _repair_entry(index, ent)
    if not surface:
        return {**base, "status": "unrepairable", "reason": "empty_surface"}

    if _current_span_matches(text, ent):
        return {**base, "status": "unchanged", "reason": "current_span_valid"}

    candidates = find_span_candidates(text, surface)
    if len(candidates) > 1:
        return {
            **base,
            "status": "ambiguous",
            "reason": "multiple_candidates",
            "candidate_count": len(candidates),
            "candidates": [_span_entry(text, start, end) for start, end in candidates],
        }

    result = find_span(text, surface)
    if result is None:
        return {**base, "status": "unrepairable", "reason": "surface_not_found"}

    start, end = result
    repaired = {**ent, "text": text[start:end], "start": start, "end": end}
    return {
        **base,
        "status": "repaired",
        "reason": "realigned",
        "new_start": start,
        "new_end": end,
        "new_text": repaired["text"],
        "entity": repaired,
    }


def _repair_entry(index: int, ent: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": index,
        "label": ent.get("label") or ent.get("semantic_tag") or "",
        "entity_text": ent.get("text", ""),
        "old_start": ent.get("start"),
        "old_end": ent.get("end"),
    }


def _current_span_matches(text: str, ent: dict[str, Any]) -> bool:
    try:
        start = int(ent.get("start", 0))
        end = int(ent.get("end", 0))
    except (TypeError, ValueError):
        return False
    surface = str(ent.get("text", ""))
    return 0 <= start < end <= len(text) and text[start:end] == surface


def _span_entry(text: str, start: int, end: int) -> dict[str, Any]:
    return {"start": start, "end": end, "text": text[start:end]}


def filter_and_realign(
    text: str,
    entities: list[dict[str, Any]],
    excluded_assertions: set[str],
    *,
    diagnostics: list[dict[str, Any]] | None = None,
    label_id: str = "",
    source: str = "",
) -> tuple[list[dict[str, Any]], int, int]:
    """Filter by assertion and realign spans for one record.

    Args:
        text: The sentence text for the record.
        entities: Raw entity dicts from entities_json.
        excluded_assertions: Set of assertion values to drop.
        diagnostics: If provided, append a dict for each dropped entity.
        label_id: Owning GoldLabel node ID (written to diagnostics).
        source: Source field of the GoldLabel (written to diagnostics).

    Returns:
        (kept_entities, assertion_filtered_count, span_misaligned_count)
    """
    assertion_filtered = 0
    span_misaligned = 0
    result = []

    for ent in entities:
        assertion = str(ent.get("assertion", "present")).strip().lower()
        if assertion in excluded_assertions:
            assertion_filtered += 1
            if diagnostics is not None:
                diagnostics.append(
                    _drop_entry(
                        label_id,
                        source,
                        ent,
                        assertion,
                        "assertion_filtered",
                        text=text,
                    )
                )
            continue

        realigned = realign_entity(text, ent)
        if realigned is None:
            span_misaligned += 1
            if diagnostics is not None:
                diagnostics.append(
                    _drop_entry(
                        label_id,
                        source,
                        ent,
                        assertion,
                        "span_misaligned",
                        text=text,
                    )
                )
            continue

        result.append(realigned)

    return result, assertion_filtered, span_misaligned


def _drop_entry(
    label_id: str,
    source: str,
    ent: dict[str, Any],
    assertion: str,
    reason: str,
    *,
    text: str,
) -> dict[str, Any]:
    return {
        "label_id": label_id,
        "source": source,
        "text": text,
        "entity_text": ent.get("text", ""),
        "label": ent.get("label") or ent.get("semantic_tag") or "",
        "assertion": assertion,
        "reason": reason,
    }


def compute_export_diagnostics() -> dict[str, Any]:
    """Replay the GoldLabel export filter path and return per-entity diagnostics.

    Connects to Neo4j, fetches all exportable GoldLabels, applies
    post-processor rules, assertion filtering, and span realignment --
    identical to the training export path but without writing DocBins.

    Returns a dict with:
        assertion_filtered: list of dropped entity dicts (reason=assertion_filtered)
        span_misaligned:    list of dropped entity dicts (reason=span_misaligned)
        total_records:      total GoldLabel records fetched
        total_entities:     total entity spans across all records
        excluded_assertions: the set of assertions that were filtered
    """
    from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
    from libs.cypher.gold_label_queries import GET_ALL_GOLD_LABELS_FOR_EXPORT
    from libs.cypher.post_processor_rule_queries import GET_ACTIVE_POST_PROCESSOR_RULES
    from libs.ner.post_processor_rules import apply_rules_to_entities, parse_rules

    excluded = get_excluded_assertions()
    diagnostics: list[dict[str, Any]] = []
    total_records = 0
    total_entities = 0

    rules = _load_rules()

    kg_client = KnowledgeGraphClient()
    try:
        with kg_client.session() as session:
            rows = session.run(GET_ALL_GOLD_LABELS_FOR_EXPORT)
            for row in rows:
                total_records += 1
                text = str(row["text"] or "")
                entities = json.loads(row["entities_json"] or "[]")
                label_id = str(row.get("label_id") or "")
                source = str(row.get("source") or "")

                if rules:
                    entities = apply_rules_to_entities(text, entities, rules)

                total_entities += len(entities)
                filter_and_realign(
                    text,
                    entities,
                    excluded,
                    diagnostics=diagnostics,
                    label_id=label_id,
                    source=source,
                )
    finally:
        kg_client.close()

    assertion_filtered = [d for d in diagnostics if d["reason"] == "assertion_filtered"]
    span_misaligned = [d for d in diagnostics if d["reason"] == "span_misaligned"]

    return {
        "total_records": total_records,
        "total_entities": total_entities,
        "excluded_assertions": sorted(excluded),
        "assertion_filtered": assertion_filtered,
        "span_misaligned": span_misaligned,
        "summary": {
            "assertion_filtered_count": len(assertion_filtered),
            "span_misaligned_count": len(span_misaligned),
        },
    }


def _load_rules() -> list:
    """Load active post-processor rules from the patient graph, or return []."""
    try:
        from libs.neo4j_client.client import PatientGraphClient
        from libs.cypher.post_processor_rule_queries import (
            GET_ACTIVE_POST_PROCESSOR_RULES,
        )
        from libs.ner.post_processor_rules import parse_rules

        client = PatientGraphClient()
        try:
            with client.session() as session:
                rows = [dict(r) for r in session.run(GET_ACTIVE_POST_PROCESSOR_RULES)]
            return parse_rules(rows)
        finally:
            client.close()
    except Exception:
        return []
