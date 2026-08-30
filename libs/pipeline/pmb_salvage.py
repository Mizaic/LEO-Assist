"""Lift menopause plus vaginal bleed to one PMB code.

When the letter or current entities show a postmenopausal setting
and a vaginal bleed, add present 76742009. Do not invent bleed from
a negated PVB phrase.

Atlas: DI-8BAC9BB3, DO-ABE2AE61, VT-E053BB7C.
"""

from __future__ import annotations

import re
from typing import Any

PMB_CONCEPT_ID = "76742009"
POSTMENOPAUSAL_STATE_ID = "76498008"
PV_BLEEDING_ID = "289530006"
HEAVY_PV_BLEED_ID = "315224006"
PMB_TERM = "Postmenopausal bleeding (finding)"

_ABSENT = frozenset({"absent", "negated", "denied"})
_MENO = re.compile(
    r"(?i)\b(post[-\s]?menopausal|menopause|amenorrhoe?a|"
    r"hrt|hormone replacement)\b"
)
_AMENO_YEARS = re.compile(
    r"(?i)\bamenorrhoe?a\b.{0,40}\byears?\b|\bno periods?\b.{0,40}\byears?\b"
)
_BLEED = (
    re.compile(r"(?i)\bpv\s*bleed(?:ing)?\b"),
    re.compile(r"(?i)\bvaginal\s+bleed(?:ing)?\b"),
    re.compile(r"(?i)\bhas been bleeding\b"),
    re.compile(r"(?i)\bworsening\s+bleed(?:ing)?\b"),
)
_NO_BEFORE = re.compile(r"(?i)\bno\b")


def _present_ids(entities: list[dict[str, Any]]) -> set[str]:
    found: set[str] = set()
    for ent in entities or []:
        if str(ent.get("assertion") or "present").lower() in _ABSENT:
            continue
        for key in ("snomed_concept_id", "concept_id"):
            raw = ent.get(key)
            if raw:
                found.add(str(raw))
    return found


def _has_meno(text: str, ids: set[str]) -> bool:
    if POSTMENOPAUSAL_STATE_ID in ids:
        return True
    if _AMENO_YEARS.search(text or ""):
        return True
    return bool(_MENO.search(text or ""))


def _phrase_is_negated(text: str, start: int) -> bool:
    window = text[max(0, start - 24) : start]
    return bool(_NO_BEFORE.search(window))


def _has_bleed_words(text: str) -> bool:
    body = text or ""
    for pat in _BLEED:
        for match in pat.finditer(body):
            if not _phrase_is_negated(body, match.start()):
                return True
    return False


def _has_bleed(text: str, ids: set[str]) -> bool:
    if PV_BLEEDING_ID in ids or HEAVY_PV_BLEED_ID in ids:
        return True
    return _has_bleed_words(text)


def _pmb_entity() -> dict[str, Any]:
    return {
        "text": "postmenopausal bleeding",
        "label": "finding",
        "semantic_tag": "finding",
        "assertion": "present",
        "confidence": 0.0,
        "snomed_concept_id": PMB_CONCEPT_ID,
        "concept_id": PMB_CONCEPT_ID,
        "snomed_term": PMB_TERM,
        "lookup_term": "postmenopausal bleeding",
        "_recovered_pmb": True,
    }


def salvage_pmb(
    encounter_text: str, entities: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Add present 76742009 when menopause or HRT sits with a vaginal bleed."""
    current = list(entities or [])
    ids = _present_ids(current)
    if PMB_CONCEPT_ID in ids:
        return current
    if not _has_meno(encounter_text, ids):
        return current
    if not _has_bleed(encounter_text, ids):
        return current
    return current + [_pmb_entity()]


__all__ = ["PMB_CONCEPT_ID", "salvage_pmb"]
