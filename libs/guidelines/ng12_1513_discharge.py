"""Reshape NG12 1.5.13 discharge into first time OR platelets OR haematuria.

NICE is unexplained vaginal discharge plus one of: first presentation,
thrombocytosis, or haematuria. The extracted tree ANDs first presentation
with platelets or blood in the urine. This copy keeps the haematuria arm.

Atlas: UN-5F3BF083, DI-8BAC9BB3, DI-DE8B125E
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DISCHARGE_ID = "271939006"
THROMBOCYTOSIS_ID = "6631009"
HAEMATURIA_ID = "34436003"


def reshape_1513_discharge_or(tree: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with the discharge arm as NICE OR wording."""
    out = deepcopy(tree)
    arm = _discharge_arm(out)
    if arm is None:
        return out
    first = _leaf_with_source(arm, "first time")
    unexplained = _leaf_with_source(arm, "unexplained")
    thrombo = _leaf_with_concept(arm, THROMBOCYTOSIS_ID)
    haem = _leaf_with_source(arm, "report haematuria")
    if not all((first, unexplained, thrombo, haem)):
        return out
    _set_soft(
        unexplained,
        {"kind": "unexplained", "enforcement": "soft"},
    )
    _set_soft(
        first,
        {
            "kind": "first_presentation",
            "enforcement": "soft",
            "concept_id": DISCHARGE_ID,
            "within_days": 90,
        },
    )
    arm["children"] = [
        unexplained,
        {"kind": "OR", "children": [first, thrombo, haem]},
    ]
    return out


def _top_or(tree: dict[str, Any]) -> dict[str, Any] | None:
    for child in tree.get("children") or []:
        if not isinstance(child, dict):
            continue
        if str(child.get("kind") or "").upper() == "OR":
            return child
    return None


def _discharge_arm(tree: dict[str, Any]) -> dict[str, Any] | None:
    group = _top_or(tree)
    if group is None:
        return None
    for child in group.get("children") or []:
        if not isinstance(child, dict):
            continue
        if str(child.get("kind") or "").upper() != "AND":
            continue
        if _leaf_with_source(child, "unexplained"):
            return child
    return None


def _walk_concepts(node: dict[str, Any]) -> list[dict[str, Any]]:
    kind = str(node.get("kind") or "").upper()
    if kind == "CONCEPT":
        return [node]
    found: list[dict[str, Any]] = []
    for child in node.get("children") or []:
        if isinstance(child, dict):
            found.extend(_walk_concepts(child))
    return found


def _leaf_with_source(node: dict[str, Any], needle: str) -> dict[str, Any] | None:
    for leaf in _walk_concepts(node):
        if needle in str(leaf.get("source_row_text") or "").lower():
            return leaf
    return None


def _leaf_with_concept(node: dict[str, Any], concept_id: str) -> dict[str, Any] | None:
    for leaf in _walk_concepts(node):
        crit = leaf.get("criterion") or {}
        if str(crit.get("snomed_concept_id") or "") == concept_id:
            return leaf
    return None


def _set_soft(leaf: dict[str, Any], spec: dict[str, Any]) -> None:
    criterion = dict(leaf.get("criterion") or {})
    quals = [
        q
        for q in list(criterion.get("soft_qualifiers") or [])
        if isinstance(q, dict) and q.get("kind") != spec["kind"]
    ]
    quals.append(spec)
    criterion["soft_qualifiers"] = quals
    leaf["criterion"] = criterion
