"""Packaged ConText cues for the Knowledge Context Rules list.

Atlas: DI-DA60AC55 / DO-7E9AD55B / VT-AEA5D045
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_UK_RULES_PATH = (
    Path(__file__).parent / "resources" / "uk_primary_care_context_rules.json"
)
_CONTEXT_RULE_KEYS = frozenset(
    {
        "pattern",
        "category",
        "max_scope",
        "metadata",
        "max_targets",
        "literal",
        "excluded_types",
        "direction",
    }
)


def packaged_rule_id(pack: str, literal: str) -> str:
    return f"{pack}:{literal.strip().lower()}"


def is_packaged_rule_id(rule_id: str | None) -> bool:
    if not rule_id:
        return False
    return rule_id.startswith("default:") or rule_id.startswith("uk:")


def _medspacy_default_path() -> Path:
    import medspacy.context.context as ctx_mod

    return (
        Path(ctx_mod.__file__).resolve().parents[2]
        / "resources"
        / "en"
        / "context_rules.json"
    )


def _load_json_rules(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        logger.warning("ConText rules file not found at %s", path)
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.error("Failed to load ConText rules from %s", path, exc_info=True)
        return []
    return list(raw.get("context_rules") or [])


def _as_list_row(pack: str, raw: dict[str, Any]) -> dict[str, Any] | None:
    literal = str(raw.get("literal") or "").strip()
    if not literal:
        return None
    return {
        "rule_id": packaged_rule_id(pack, literal),
        "literal": literal,
        "category": raw.get("category") or "",
        "direction": raw.get("direction") or "FORWARD",
        "max_scope": raw.get("max_scope") or 10,
        "description": raw.get("description") or "",
        "example": raw.get("example") or "",
        "created_by": "system",
        "active": True,
        "created_at": None,
        "updated_at": None,
        "source": "builtin",
        "org_id": None,
    }


def list_packaged_context_rules() -> list[dict[str, Any]]:
    """Default medspaCy cues first, then UK extras. One row per literal."""
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    packs = (("default", _medspacy_default_path()), ("uk", _UK_RULES_PATH))
    for pack, path in packs:
        for raw in _load_json_rules(path):
            row = _as_list_row(pack, raw)
            if row is None:
                continue
            key = row["literal"].lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def suppressed_literals(rows: list[dict[str, Any]]) -> set[str]:
    found: set[str] = set()
    for row in rows:
        if row.get("active", True):
            continue
        lit = str(row.get("literal") or "").strip().lower()
        if lit:
            found.add(lit)
    return found


def merge_context_rule_list(
    packaged: list[dict[str, Any]],
    custom: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    off = suppressed_literals(custom)
    merged: list[dict[str, Any]] = []
    for row in packaged:
        item = dict(row)
        if item["literal"].strip().lower() in off:
            item["active"] = False
        merged.append(item)
    for row in custom:
        if is_packaged_rule_id(row.get("rule_id")):
            continue
        merged.append({**row, "source": row.get("source") or "custom"})
    return merged


def packaged_nlp_entries(suppressed: set[str]) -> list[dict[str, Any]]:
    """Raw ConTextRule kwargs for default + UK, minus turned-off literals."""
    entries: list[dict[str, Any]] = []
    for path in (_medspacy_default_path(), _UK_RULES_PATH):
        for raw in _load_json_rules(path):
            lit = str(raw.get("literal") or "").strip().lower()
            if not lit or lit in suppressed:
                continue
            clean = {k: v for k, v in raw.items() if k in _CONTEXT_RULE_KEYS}
            if clean.get("literal"):
                entries.append(clean)
    return entries


def find_packaged_rule(rule_id: str) -> dict[str, Any] | None:
    for row in list_packaged_context_rules():
        if row["rule_id"] == rule_id:
            return row
    return None
