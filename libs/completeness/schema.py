"""Normalise completeness schema groups for store and preview.

Atlas trace:
  UN: UN-3B25A20E
  DI: DI-A0E69E38
  DO: DO-020C7B5C
"""

from __future__ import annotations

from typing import Any

from libs.completeness.logic_groups import group_is_blocking, resolve_kind


def normalise_completeness_groups(groups: list[Any]) -> list[dict[str, Any]]:
    """Copy groups into the stored JSON shape, keeping logic fields."""
    rows = [_normalise_one(group) for group in groups]
    if not any(group_is_blocking(row) for row in rows):
        raise ValueError("Completeness schema needs at least one required group")
    return rows


def _normalise_one(group: Any) -> dict[str, Any]:
    data = _as_dict(group)
    kind = resolve_kind(data)
    members = [_normalise_member(item) for item in data.get("members") or []]
    return {
        "name": str(data.get("name") or "").strip(),
        "required": kind != "optional",
        "kind": kind,
        "min_count": _as_int(data.get("min_count", data.get("min")), 1),
        "semantic_categories": [
            str(tag).strip() for tag in (data.get("semantic_categories") or []) if str(tag).strip()
        ],
        "concept_ids": _concept_ids(data.get("concept_ids")),
        "members": members,
        "if_group": _optional_nested(data.get("if_group")),
        "then_group": _optional_nested(data.get("then_group")),
    }


def _normalise_member(item: Any) -> dict[str, Any]:
    data = _as_dict(item)
    return {
        "name": str(data.get("name") or "").strip(),
        "required": False,
        "kind": "optional",
        "semantic_categories": [
            str(tag).strip() for tag in (data.get("semantic_categories") or []) if str(tag).strip()
        ],
        "concept_ids": _concept_ids(data.get("concept_ids")),
    }


def _optional_nested(value: Any) -> dict[str, Any] | None:
    if not value:
        return None
    return _normalise_member(value)


def _as_dict(group: Any) -> dict[str, Any]:
    if hasattr(group, "model_dump"):
        return group.model_dump()
    if isinstance(group, dict):
        return group
    return {}


def _concept_ids(raw: Any) -> list[int]:
    ids: list[int] = []
    for cid in raw or []:
        parsed = _as_int(cid, 0)
        if parsed > 0:
            ids.append(parsed)
    return ids


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
