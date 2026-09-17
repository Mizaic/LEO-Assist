"""Propose soft-gate and FIT policy tags from recommendation wording.

Writes nothing. A caller may apply only the allow-list after review.

Atlas trace: DI-C136E4B7, DI-55CCC312
"""

from __future__ import annotations

from typing import Any

ALLOW_APPLY = frozenset({"1.5.13", "1.3.1", "1.3.5", "1.3.6"})


def propose_soft_gate(rec_number: str, verbatim: str) -> dict[str, Any]:
    """Return proposed tags. Does not write to the graph."""
    text = (verbatim or "").lower()
    kinds: list[str] = []
    if rec_number == "1.5.13" or "first presentation" in text or "first time" in text:
        kinds.append("first_presentation")
    if "unexplained" in text and "first_presentation" not in kinds:
        kinds.append("unexplained")
    policy = None
    if rec_number == "1.3.1" or ("faecal immunochemical" in text and "offer" in text):
        policy = "required"
    if rec_number in {"1.3.5", "1.3.6"}:
        policy = "not_required"
    return {
        "rec_number": rec_number,
        "soft_kinds": kinds,
        "investigation_policy": policy,
    }


def _source_text(node: dict[str, Any]) -> str:
    criterion = node.get("criterion") or {}
    return " ".join(
        [
            str(node.get("source_row_text") or ""),
            str(node.get("source_text") or ""),
            str(criterion.get("source_text") or ""),
        ]
    ).lower()


def _append_qualifier(quals: list[dict[str, Any]], kind: str, enforcement: str) -> None:
    if any(q.get("kind") == kind for q in quals):
        return
    quals.append({"kind": kind, "enforcement": enforcement})


def tag_first_presentation_leaves(node: dict[str, Any]) -> dict[str, Any]:
    """Add source-text qualifier checks on matching CONCEPT leaves."""
    kind = str(node.get("kind") or "").upper()
    if kind == "CONCEPT":
        row = _source_text(node)
        criterion = dict(node.get("criterion") or {})
        quals = list(criterion.get("soft_qualifiers") or [])
        if "first time" in row or "first presentation" in row:
            _append_qualifier(quals, "first_presentation", "soft")
        if "unexplained" in row:
            _append_qualifier(quals, "unexplained", "hard")
        if "persistent" in row or "persisting" in row:
            _append_qualifier(quals, "persistent", "hard")
        if quals == list(criterion.get("soft_qualifiers") or []):
            return node
        criterion["soft_qualifiers"] = quals
        return {**node, "criterion": criterion}
    children = node.get("children")
    if not children:
        return node
    return {**node, "children": [tag_first_presentation_leaves(c) for c in children]}


def filter_apply_list(proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the allow-list rows for --apply."""
    return [p for p in proposals if p.get("rec_number") in ALLOW_APPLY]
