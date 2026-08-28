"""Seed completeness groups from a detected 2WW-style letter.

Atlas trace: DI-A0E69E38, DI-26546721, UN-3B25A20E

All SNOMED concept IDs are verified active in the UK SNOMED release loaded
into the knowledge graph (ecca11a1.databases.neo4j.io). IS_A expansion in
the evaluator means any descendant concept also satisfies a group.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Concept ID registry
# Each key is the canonical name used by _leaf() / _codes_for().
# Keep names lowercase for lookup.
# ---------------------------------------------------------------------------

_CONCEPT_IDS: dict[str, list[int]] = {
    # Minimum Dataset vitals
    "blood pressure": [75367002],       # Blood pressure (observable entity)
    "heart rate": [364075005],          # Heart rate (observable entity)

    # Procedures required by 2WW rules
    "tvus": [426491001],                # Transvaginal ultrasound examination of female genital tract
    "transvaginal": [426491001],
    "ca125": [80529009],                # CA 125 measurement (procedure)
    "ca 125": [80529009],

    # Section A suspected cancer sites
    # IS_A expansion covers 'suspected' and 'primary' descendants automatically.
    "cervix": [
        363354003,   # Malignant neoplasm of cervix uteri (disorder)
        315266007,   # Malignant neoplasm of cervix uteri suspected (situation)
    ],
    "endometrium": [
        254878006,   # Endometrial carcinoma (disorder)
        93781006,    # Primary malignant neoplasm of endometrium (disorder)
        123844007,   # Neoplasm of endometrium (disorder)
    ],
    "ovary": [
        363443007,   # Malignant neoplasm of ovary (disorder)
        762997004,   # Malignant neoplasm of ovary suspected (situation)
        93934004,    # Primary malignant neoplasm of ovary (disorder)
    ],
    "vagina": [
        363445000,   # Malignant neoplasm of vagina (disorder)
        372025005,   # Primary malignant neoplasm of vagina (disorder)
    ],
    "vulva": [
        363367000,   # Malignant neoplasm of vulva (disorder)
        762996008,   # Malignant neoplasm of vulva suspected (situation)
        94143002,    # Primary malignant neoplasm of vulva (disorder)
    ],

    # Section B referral criteria
    "b1": [
        363354003,   # Malignant neoplasm of cervix uteri -- a suspicious cervical lesion
        315266007,
    ],
    "b3": [163367002],   # On examination - pelvic mass palpated (finding)
    "b4": [163367002],   # Same -- suspicious pelvic mass on USS overlaps
    "b5": [76742009],    # Postmenopausal bleeding (finding)
    "b6": [48880000],    # Postcoital bleeding (finding)
    "b9": [
        363443007,   # Malignant neoplasm of ovary
        80529009,    # CA 125 measurement -- both together required for B9
    ],

    # Section D mandatory blood results
    "fbc": [26604007],          # Complete blood count (procedure)
    "lft": [26958001],          # Hepatic function panel (procedure)
    "ue": [252167001],          # Measurement of urea and electrolytes (procedure)
    "calcium": [390963002],     # Plasma calcium level (procedure)

    # Performance status
    "ecog": [423740007],        # Eastern Cooperative Oncology Group performance status
    "clinical frailty": [763264000],  # Canadian Study of Health and Aging Clinical Frailty Scale score
}

_SEMANTIC_TAGS: dict[str, list[str]] = {
    "blood pressure": ["observable_entity"],
    "heart rate": ["observable_entity"],
    "tvus": ["procedure"],
    "transvaginal": ["procedure"],
    "ca125": ["procedure"],
    "ca 125": ["procedure"],
    # Cancer site arms match by specific concept IDs -- no broad tags.
    "cervix": [],
    "endometrium": [],
    "ovary": [],
    "vagina": [],
    "vulva": [],
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


def _mandatory_n_of(name: str, members: list[str], min_count: int = 1) -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Section B label -> canonical key mapping.
# The form uses patterns like "B1", "B5" etc. from the splitter.
# We map them to the lookup key so _leaf() finds the right codes.
# ---------------------------------------------------------------------------
_SECTION_B_KEY: dict[str, str] = {
    "b1": "b1",
    "b2": "vulva",   # B2: suspicious vulval lesion -> vulval cancer
    "b3": "b3",
    "b4": "b4",
    "b5": "b5",
    "b6": "b6",
    "b9": "b9",
}


def _section_b_leaf(label: str) -> dict[str, Any]:
    """Create a leaf for a Section B criterion, looking up codes by label."""
    key = _SECTION_B_KEY.get(label.strip().lower(), label.lower())
    concept_ids, semantic_categories = _codes_for(key)
    return {
        "name": label,
        "kind": "optional",
        "required": False,
        "semantic_categories": semantic_categories,
        "concept_ids": concept_ids,
    }


def seed_completeness_groups(
    text: str, sections: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Propose completeness groups from letter text and detected sections."""
    groups: list[dict[str, Any]] = []

    # Section A: suspected cancer site (at least one must be extracted)
    section_a = next((s for s in sections if s.get("section_id") == "A"), None)
    sites = [
        str(item.get("pattern") or "")
        for item in (section_a or {}).get("items") or []
        if item.get("pattern")
    ]
    if sites:
        groups.append(_one_of("Section A suspected sites", sites))

    # Section B: at least one 14-day-rule criterion must be extracted
    section_b = next((s for s in sections if s.get("section_id") == "B"), None)
    criteria: list[str] = []
    for item in (section_b or {}).get("items") or []:
        raw = str(item.get("pattern") or "")
        m = re.search(r"B\d+", raw, re.I)
        criteria.append(m.group(0) if m else raw)
    if criteria:
        # Build members with codes via _section_b_leaf
        members = [_section_b_leaf(c) for c in criteria]
        groups.append({
            "name": "Section B referral criteria",
            "kind": "one_of",
            "required": True,
            "semantic_categories": [],
            "concept_ids": [],
            "members": members,
        })

    # If-then rules driven by the form's own instructions
    if re.search(r"endometr", text, re.I) and re.search(
        r"tvus|transvaginal", text, re.I
    ):
        groups.append(_if_then("Endometrium", "TVUS"))
    if re.search(r"ovar", text, re.I) and re.search(r"ca\s*125", text, re.I):
        groups.append(_if_then("Ovary", "Ca125"))

    # Section D mandatory bloods (require at least one result present)
    if re.search(r"mandatory|bloods done today|fbc|lft", text, re.I):
        groups.append(
            _mandatory_n_of(
                "Section D mandatory bloods",
                ["FBC", "LFT", "UE", "Calcium"],
                min_count=1,
            )
        )

    # Minimum Dataset vitals
    if re.search(r"\bBP\b|\bblood pressure\b", text, re.I):
        groups.append(_mandatory("Blood pressure"))
    if re.search(r"\bHR\b|\bheart rate\b", text, re.I):
        groups.append(_mandatory("Heart rate"))

    # Performance status (ECOG / Clinical Frailty Scale)
    if re.search(r"ecog|performance status|frailty", text, re.I):
        groups.append(
            {
                "name": "Performance status",
                "kind": "one_of",
                "required": True,
                "semantic_categories": [],
                "concept_ids": [],
                "members": [_leaf("ECOG"), _leaf("Clinical frailty")],
            }
        )

    return groups
