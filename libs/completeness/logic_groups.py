"""Guideline-aligned completeness group kinds.

Reuses the guideline builder kinds AND / OR / AT_LEAST and adds if-then.
Legacy groups with only a required flag still evaluate as mandatory or optional.

Atlas trace:
  UN: UN-3B25A20E
  DI: DI-A0E69E38
  DO: DO-020C7B5C
  VT: VT-940267F9
"""

from __future__ import annotations

from typing import Any, Callable

KIND_ALIASES = {
    "AND": "mandatory",
    "OR": "one_of",
    "AT_LEAST": "n_of",
    "IF_THEN": "if_then",
    "mandatory": "mandatory",
    "optional": "optional",
    "one_of": "one_of",
    "n_of": "n_of",
    "if_then": "if_then",
}

LeafEvaluator = Callable[[dict[str, Any]], dict[str, Any]]


def resolve_kind(group: dict[str, Any]) -> str:
    """Map a stored group to a canonical completeness kind."""
    raw = str(group.get("kind") or "").strip()
    if raw:
        mapped = KIND_ALIASES.get(raw) or KIND_ALIASES.get(raw.upper())
        if mapped:
            return mapped
    return "mandatory" if group.get("required", True) else "optional"


def group_is_blocking(group: dict[str, Any]) -> bool:
    """True when a failed group should mark the dataset incomplete."""
    return resolve_kind(group) != "optional"


def min_count_for(group: dict[str, Any], default: int = 1) -> int:
    """Read n-of threshold from min_count or guideline-style min."""
    raw = group.get("min_count", group.get("min", default))
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def collect_concept_ids(schema: list[dict[str, Any]]) -> set[int]:
    """Walk groups, members, and if-then arms for SNOMED ids."""
    ids: set[int] = set()
    for group in schema:
        _collect_from_group(group, ids)
    return ids


def evaluate_logic_group(
    group: dict[str, Any],
    evaluate_leaf: LeafEvaluator,
) -> dict[str, Any]:
    """Evaluate one group, including logic wrappers."""
    kind = resolve_kind(group)
    if kind == "one_of":
        return _evaluate_n_of(group, evaluate_leaf, min_needed=1)
    if kind == "n_of":
        return _evaluate_n_of(group, evaluate_leaf, min_needed=min_count_for(group, 2))
    if kind == "if_then":
        return _evaluate_if_then(group, evaluate_leaf)
    if kind == "mandatory" and group.get("members"):
        return _evaluate_n_of(
            group,
            evaluate_leaf,
            min_needed=len(list(group.get("members") or [])),
        )
    row = evaluate_leaf(group)
    row["kind"] = kind
    row["required"] = kind != "optional"
    row.setdefault("matched_member_names", [])
    return row


def _evaluate_n_of(
    group: dict[str, Any],
    evaluate_leaf: LeafEvaluator,
    min_needed: int,
) -> dict[str, Any]:
    members = [m for m in (group.get("members") or []) if isinstance(m, dict)]
    rows = [evaluate_leaf(member) for member in members]
    matched_names = [row["name"] for row in rows if row["matched"]]
    matched = len(matched_names) >= min_needed
    kind = resolve_kind(group)
    return {
        "name": str(group.get("name") or ""),
        "kind": kind,
        "required": kind != "optional",
        "matched": matched,
        "matched_member_names": matched_names,
        "matched_concept_ids": _merge_ids(rows, "matched_concept_ids"),
        "missing_concept_ids": _merge_ids(rows, "missing_concept_ids"),
        "matched_semantic_category": any(row.get("matched_semantic_category") for row in rows),
    }


def _evaluate_if_then(
    group: dict[str, Any],
    evaluate_leaf: LeafEvaluator,
) -> dict[str, Any]:
    if_row = evaluate_leaf(_as_group(group.get("if_group")))
    if not if_row["matched"]:
        return {
            "name": str(group.get("name") or ""),
            "kind": "if_then",
            "required": False,
            "matched": True,
            "matched_member_names": [],
            "matched_concept_ids": if_row.get("matched_concept_ids") or [],
            "missing_concept_ids": [],
            "matched_semantic_category": bool(if_row.get("matched_semantic_category")),
        }
    then_row = evaluate_leaf(_as_group(group.get("then_group")))
    return {
        "name": str(group.get("name") or ""),
        "kind": "if_then",
        "required": True,
        "matched": bool(then_row["matched"]),
        "matched_member_names": [then_row["name"]] if then_row["matched"] else [],
        "matched_concept_ids": then_row.get("matched_concept_ids") or [],
        "missing_concept_ids": then_row.get("missing_concept_ids") or [],
        "matched_semantic_category": bool(then_row.get("matched_semantic_category")),
    }


def _as_group(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _merge_ids(rows: list[dict[str, Any]], key: str) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for row in rows:
        for cid in row.get(key) or []:
            parsed = int(cid)
            if parsed not in seen:
                seen.add(parsed)
                out.append(parsed)
    return out


def _collect_from_group(group: dict[str, Any], ids: set[int]) -> None:
    for cid in group.get("concept_ids") or []:
        parsed = _parse_id(cid)
        if parsed:
            ids.add(parsed)
    for member in group.get("members") or []:
        if isinstance(member, dict):
            _collect_from_group(member, ids)
    for arm in (group.get("if_group"), group.get("then_group")):
        if isinstance(arm, dict):
            _collect_from_group(arm, ids)


def _parse_id(value: Any) -> int:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0
