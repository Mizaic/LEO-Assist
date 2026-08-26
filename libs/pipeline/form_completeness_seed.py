"""Seed completeness groups from a detected 2WW-style letter.

Atlas trace: DI-A0E69E38, DI-26546721, UN-3B25A20E
"""

from __future__ import annotations

import re
from typing import Any


def _leaf(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "optional",
        "required": False,
        "semantic_categories": [],
        "concept_ids": [],
    }


def _one_of(name: str, members: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "one_of",
        "required": True,
        "semantic_categories": [],
        "concept_ids": [],
        "members": [_leaf(item) for item in members],
    }


def _mandatory(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "mandatory",
        "required": True,
        "semantic_categories": [],
        "concept_ids": [],
    }


def _if_then(if_name: str, then_name: str) -> dict[str, Any]:
    return {
        "name": f"If {if_name} then {then_name}",
        "kind": "if_then",
        "required": True,
        "semantic_categories": [],
        "concept_ids": [],
        "if_group": _leaf(if_name),
        "then_group": _leaf(then_name),
    }


def seed_completeness_groups(
    text: str, sections: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Propose completeness groups from letter text and detected sections."""
    groups: list[dict[str, Any]] = []
    section_a = next((s for s in sections if s.get("section_id") == "A"), None)
    sites = [
        str(item.get("pattern") or "")
        for item in (section_a or {}).get("items") or []
        if item.get("pattern")
    ]
    if sites:
        groups.append(_one_of("Section A suspected sites", sites))
    section_b = next((s for s in sections if s.get("section_id") == "B"), None)
    criteria: list[str] = []
    for item in (section_b or {}).get("items") or []:
        raw = str(item.get("pattern") or "")
        match = re.search(r"B\d+", raw, re.I)
        criteria.append(match.group(0) if match else raw)
    if criteria:
        groups.append(_one_of("Section B referral criteria", criteria))
    if re.search(r"endometr", text, re.I) and re.search(
        r"tvus|transvaginal", text, re.I
    ):
        groups.append(_if_then("Endometrium", "TVUS"))
    if re.search(r"ovar", text, re.I) and re.search(r"ca\s*125", text, re.I):
        groups.append(_if_then("Ovary", "Ca125"))
    if re.search(r"mandatory|bloods done today|fbc|lft", text, re.I):
        groups.append(_mandatory("Section D mandatory bloods"))
    if re.search(r"\bBP\b|\bblood pressure\b", text, re.I):
        groups.append(_mandatory("Blood pressure"))
    if re.search(r"\bHR\b|\bheart rate\b", text, re.I):
        groups.append(_mandatory("Heart rate"))
    return groups
