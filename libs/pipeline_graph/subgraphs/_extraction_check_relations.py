"""Relation corrections and additions proposed by the extraction check.

Atlas trace:
  DO: DO-8620A68B
"""

from __future__ import annotations

from typing import Any

from libs.relations.policy import policy_relation_types

_ALLOWED_RELATION_TYPES = policy_relation_types()
_INDEXED_RELATION_KEYS = ("__relations", "__snomed_relations")


def _moved_relations(
    rows: list[Any], before: list[dict[str, Any]], new_index: dict[int, int]
) -> list[Any]:
    moved = []
    for rel in rows:
        target = rel.get("target_idx") if isinstance(rel, dict) else None
        if not (isinstance(target, int) and 0 <= target < len(before)):
            continue
        new_target = new_index.get(id(before[target]))
        if new_target is not None:
            moved.append({**rel, "target_idx": new_target})
    return moved


def renumber_relations(
    before: list[dict[str, Any]], after: list[dict[str, Any]]
) -> None:
    """Point relations in *after* at their targets' new places.

    *after* holds some of the same fact objects as *before*, in order, with
    others removed or appended. A relation whose target was removed is
    dropped: it cannot be pointed anywhere true.
    """
    new_index = {id(entity): i for i, entity in enumerate(after)}
    for entity in after:
        for key in _INDEXED_RELATION_KEYS:
            rows = entity.get(key)
            if isinstance(rows, list) and rows:
                entity[key] = _moved_relations(rows, before, new_index)


def _parse_relation_rows(rows: Any, entities_count: int) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return parsed
    for row in rows:
        if not isinstance(row, dict):
            continue
        relation_type = str(row.get("type") or "").strip().lower()
        target_idx = row.get("target_idx")
        if not (
            relation_type in _ALLOWED_RELATION_TYPES
            and isinstance(target_idx, int)
            and 0 <= target_idx < entities_count
        ):
            continue
        parsed.append(
            {
                "type": relation_type,
                "target_idx": target_idx,
                "target_text": str(row.get("target_text") or "").strip(),
                "confidence": float(row.get("confidence") or 0.6),
            }
        )
    return parsed


def apply_relation_updates(
    entities: list[dict[str, Any]],
    result: dict[str, Any],
    relation_changes: list[dict[str, Any]],
) -> None:
    for row in result.get("correct_relation", []):
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        if not (isinstance(idx, int) and 0 <= idx < len(entities)):
            continue
        parsed = _parse_relation_rows(row.get("relations"), len(entities))
        if not parsed:
            continue
        entities[idx]["__relations"] = parsed
        entities[idx]["_llm_check_source"] = "relation_corrected"
        relation_changes.append(
            {"type": "relation_corrected", "index": idx, "relations": parsed}
        )

    for row in result.get("add_relation", []):
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        if not (isinstance(idx, int) and 0 <= idx < len(entities)):
            continue
        parsed = _parse_relation_rows([row], len(entities))
        if not parsed:
            continue
        current = list(entities[idx].get("__relations") or [])
        rel = parsed[0]
        if rel in current:
            continue
        current.append(rel)
        entities[idx]["__relations"] = current
        entities[idx]["_llm_check_source"] = "relation_missed"
        relation_changes.append(
            {"type": "relation_missed", "index": idx, "relation": rel}
        )
