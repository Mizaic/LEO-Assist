"""Turn the model's proposed completeness rules into editable groups.

A rule is only as strong as the form wording behind it. A rule with no
quote, a quote that is not in the letter, or a quote with a date in it is
proposed as optional and marked for review, so it can never block a
referral until a person checks it. Rules point at taught sections and
tick-box items, never at hard-coded SNOMED codes.

Atlas trace: DI-9BF69EC9, DO-F120628C, R-A3BD3AC7
"""

from __future__ import annotations

import re
from typing import Any

from libs.pipeline.form_pattern_dates import contains_date

RULE_KINDS = frozenset({"mandatory", "optional", "one_of", "n_of", "if_then"})
MAX_RULES = 12
_MAX_TARGETS = 30
_MAX_NAME = 120
_MAX_EVIDENCE = 300
_LAYOUT = re.compile(r"[|*_`#]+")
_SPACE = re.compile(r"\s+")

Target = tuple[str, str]
Known = dict[str, dict[str, str]]


def parse_rules(raw: Any) -> list[dict[str, Any]]:
    """Keep the model's rules that are objects, with every field a string."""
    if not isinstance(raw, list):
        return []
    return [_parse_rule(r) for r in raw[: MAX_RULES * 2] if isinstance(r, dict)]


def section_id_map(
    detected: list[dict[str, Any]], merged: list[dict[str, Any]]
) -> dict[str, str]:
    """Map each detected section id to the id it has after borrowing."""
    by_heading = {_heading_key(s): str(s.get("section_id") or "") for s in merged}
    return {
        str(s.get("section_id") or ""): by_heading.get(_heading_key(s), "")
        or str(s.get("section_id") or "")
        for s in detected
    }


def build_completeness_groups(
    rules: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    letter: str,
    id_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Return editable completeness groups for the rules the form supports."""
    known = _known_targets(sections)
    page = _flatten(letter)
    groups: list[dict[str, Any]] = []
    for rule in rules:
        group = _build_group(rule, known, page, id_map or {})
        if group is not None:
            groups.append(group)
        if len(groups) >= MAX_RULES:
            break
    return groups


def _parse_rule(raw: dict[str, Any]) -> dict[str, Any]:
    targets = raw.get("targets") if isinstance(raw.get("targets"), list) else []
    return {
        "name": _text(raw.get("name"))[:_MAX_NAME],
        "kind": _text(raw.get("kind")),
        "targets": [
            {
                "section_id": _text(t.get("section_id")),
                "item_pattern": _text(t.get("item_pattern")),
            }
            for t in targets[:_MAX_TARGETS]
            if isinstance(t, dict)
        ],
        "min_count": _as_int(raw.get("min_count"), 1),
        "evidence": _text(raw.get("evidence"))[:_MAX_EVIDENCE],
    }


def _build_group(
    rule: dict[str, Any], known: Known, page: str, id_map: dict[str, str]
) -> dict[str, Any] | None:
    kind = str(rule.get("kind") or "")
    if kind not in RULE_KINDS:
        return None
    targets = _resolve_targets(rule.get("targets") or [], known, id_map)
    if not targets:
        return None
    evidence = str(rule.get("evidence") or "").strip()
    supported = _quote_supported(evidence, page)
    if kind == "if_then":
        if len(targets) != 2 or not supported:
            return None
        return _if_then_group(rule, targets, known, evidence)
    if not supported:
        kind = "optional"
    group = _base_group(rule, kind, evidence, needs_review=not supported)
    _attach_targets(group, kind, targets, known, rule)
    return group


def _resolve_targets(
    raw: list[dict[str, Any]], known: Known, id_map: dict[str, str]
) -> list[Target]:
    targets: list[Target] = []
    for target in raw:
        section_id = str(target.get("section_id") or "")
        section_id = id_map.get(section_id, section_id)
        items = known.get(section_id)
        if items is None:
            continue
        wanted = str(target.get("item_pattern") or "").strip()
        item = items.get(wanted.casefold(), None) if wanted else ""
        if item is None or (section_id, item) in targets:
            continue
        targets.append((section_id, item))
    return targets


def _attach_targets(
    group: dict[str, Any],
    kind: str,
    targets: list[Target],
    known: Known,
    rule: dict[str, Any],
) -> None:
    if len(targets) == 1 and kind in ("mandatory", "optional"):
        group["section_id"], group["item_pattern"] = targets[0]
        return
    group["members"] = [_member(t, known) for t in targets]
    if kind == "n_of":
        group["min_count"] = max(
            1, min(_as_int(rule.get("min_count"), 1), len(targets))
        )


def _if_then_group(
    rule: dict[str, Any], targets: list[Target], known: Known, evidence: str
) -> dict[str, Any]:
    group = _base_group(rule, "if_then", evidence, needs_review=False)
    group["if_group"] = _member(targets[0], known)
    group["then_group"] = _member(targets[1], known)
    return group


def _base_group(
    rule: dict[str, Any], kind: str, evidence: str, *, needs_review: bool
) -> dict[str, Any]:
    return {
        "name": str(rule.get("name") or "").strip() or "Proposed rule",
        "kind": kind,
        "required": kind != "optional",
        "min_count": 1,
        "semantic_categories": [],
        "concept_ids": [],
        "members": [],
        "if_group": None,
        "then_group": None,
        "section_id": "",
        "item_pattern": "",
        "evidence": evidence,
        "needs_review": needs_review,
    }


def _member(target: Target, known: Known) -> dict[str, Any]:
    section_id, item = target
    label = known.get(section_id, {}).get("", section_id)
    return {
        "name": item or label,
        "kind": "optional",
        "required": False,
        "semantic_categories": [],
        "concept_ids": [],
        "section_id": section_id,
        "item_pattern": item,
    }


def _known_targets(sections: list[dict[str, Any]]) -> Known:
    """Section id -> {casefolded item pattern -> item pattern}; '' -> label."""
    known: Known = {}
    for section in sections:
        section_id = str(section.get("section_id") or "").strip()
        if not section_id:
            continue
        items = {"": str(section.get("label") or section_id)}
        for item in section.get("items") or []:
            pattern = str((item or {}).get("pattern") or "").strip()
            if pattern:
                items.setdefault(pattern.casefold(), pattern)
        known[section_id] = items
    return known


def _quote_supported(evidence: str, page: str) -> bool:
    quote = _flatten(evidence)
    if not quote or contains_date(evidence):
        return False
    return quote in page


def _flatten(text: str) -> str:
    """Casefold and drop table layout so a quote can span cells."""
    return _SPACE.sub(" ", _LAYOUT.sub(" ", text or "")).strip().casefold()


def _heading_key(section: dict[str, Any]) -> str:
    return str(section.get("start_pattern") or "").lower().strip()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "MAX_RULES",
    "RULE_KINDS",
    "build_completeness_groups",
    "parse_rules",
    "section_id_map",
]
