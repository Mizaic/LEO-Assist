"""Seed completeness groups from a detected 2WW-style letter.

Atlas trace: DI-A0E69E38, DI-26546721, UN-3B25A20E

The seed proposes named groups from form structure. It only attaches
SNOMED codes for measurements that mean the same thing on every form
(blood pressure, heart rate, standard bloods, TVUS, Ca125, ECOG).
Form-specific sites and criteria (Cervix, B1, ...) stay as names so a
knowledge-base author can wire codes in the Teach this form UI.
"""

from __future__ import annotations

import re
from typing import Any

# Universal clinical measurements only. Verified active in the UK SNOMED
# release on the knowledge graph. Form-specific sites and criteria are
# not listed here -- the UI attaches those codes per form.
_CONCEPT_IDS: dict[str, list[int]] = {
    "blood pressure": [75367002],  # Blood pressure (observable entity)
    "heart rate": [364075005],  # Heart rate (observable entity)
    "tvus": [426491001],  # Transvaginal ultrasound examination
    "transvaginal": [426491001],
    "ca125": [80529009],  # CA 125 measurement (procedure)
    "ca 125": [80529009],
    "fbc": [26604007],  # Complete blood count (procedure)
    "lft": [26958001],  # Hepatic function panel (procedure)
    "ue": [252167001],  # Measurement of urea and electrolytes
    "calcium": [390963002],  # Plasma calcium level (procedure)
    "ecog": [423740007],  # ECOG performance status
    "clinical frailty": [763264000],  # Clinical Frailty Scale score
}

_SEMANTIC_TAGS: dict[str, list[str]] = {
    "blood pressure": ["observable_entity"],
    "heart rate": ["observable_entity"],
    "tvus": ["procedure"],
    "transvaginal": ["procedure"],
    "ca125": ["procedure"],
    "ca 125": ["procedure"],
    "fbc": ["procedure"],
    "lft": ["procedure"],
    "ue": ["procedure"],
    "calcium": ["procedure"],
    "ecog": ["observable_entity"],
    "clinical frailty": ["observable_entity"],
}


def _codes_for(name: str) -> tuple[list[int], list[str]]:
    """Return (concept_ids, semantic_categories) for a well-known name."""
    key = name.strip().lower()
    return _CONCEPT_IDS.get(key, []), _SEMANTIC_TAGS.get(key, [])


def _leaf(name: str) -> dict[str, Any]:
    concept_ids, semantic_categories = _codes_for(name)
    return {
        "name": name,
        "kind": "optional",
        "required": False,
        "semantic_categories": semantic_categories,
        "concept_ids": concept_ids,
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
    concept_ids, semantic_categories = _codes_for(name)
    return {
        "name": name,
        "kind": "mandatory",
        "required": True,
        "semantic_categories": semantic_categories,
        "concept_ids": concept_ids,
    }


def _mandatory_n_of(
    name: str, members: list[str], min_count: int = 1
) -> dict[str, Any]:
    """A group that requires at least min_count of its members to be present."""
    return {
        "name": name,
        "kind": "n_of",
        "required": True,
        "min_count": min_count,
        "semantic_categories": [],
        "concept_ids": [],
        "members": [_leaf(m) for m in members],
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
    _add_section_groups(groups, sections)
    _add_if_then_groups(groups, text)
    _add_dataset_groups(groups, text)
    return groups


def _add_section_groups(
    groups: list[dict[str, Any]], sections: list[dict[str, Any]]
) -> None:
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


def _add_if_then_groups(groups: list[dict[str, Any]], text: str) -> None:
    if re.search(r"endometr", text, re.I) and re.search(
        r"tvus|transvaginal", text, re.I
    ):
        groups.append(_if_then("Endometrium", "TVUS"))
    if re.search(r"ovar", text, re.I) and re.search(r"ca\s*125", text, re.I):
        groups.append(_if_then("Ovary", "Ca125"))


def _add_dataset_groups(groups: list[dict[str, Any]], text: str) -> None:
    if re.search(r"mandatory|bloods done today|fbc|lft", text, re.I):
        groups.append(
            _mandatory_n_of(
                "Section D mandatory bloods",
                ["FBC", "LFT", "UE", "Calcium"],
                min_count=1,
            )
        )
    if re.search(r"\bBP\b|\bblood pressure\b", text, re.I):
        groups.append(_mandatory("Blood pressure"))
    if re.search(r"\bHR\b|\bheart rate\b", text, re.I):
        groups.append(_mandatory("Heart rate"))
    if re.search(r"ecog|performance status|frailty", text, re.I):
        groups.append(_one_of("Performance status", ["ECOG", "Clinical frailty"]))
