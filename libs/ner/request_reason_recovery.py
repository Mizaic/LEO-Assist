"""Recover clinically meaningful reasons embedded in lab request text.

Atlas trace:
  DO: DO-8EF2EC20
  DI: DI-2F963FC6
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8EF2EC20")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

LABEL_FINDING = "finding"
LABEL_SITUATION = "situation"
_RECOVERY_MARKER = "_recovered_request_reason"

_REASON_BLOCK_RE = re.compile(
    r"\bReasons?\s+for\s+Request:\s*(?P<reason>[^\n\r]{1,160})",
    re.IGNORECASE,
)
_REASON_FINDING_RE = re.compile(
    r"\b(?:abdo(?:minal)?|tummy|stomach|epigastric)\s+pain\b",
    re.IGNORECASE,
)
_TWO_WEEK_WAIT_RE = re.compile(
    r"\b(?:2\s*ww|tww|two\s+week\s+wait|2\s*week\s+wait)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SuspectedCancerSituation:
    """Gold-derived suspected-cancer situation mapping."""

    concept_id: str
    snomed_term: str


_SUSPECTED_CANCER_BY_SITE = {
    "generic": SuspectedCancerSituation(
        "162572001", "Malignant neoplastic disease suspected (situation)"
    ),
    "breast": SuspectedCancerSituation(
        "134405005", "Malignant neoplasm of breast suspected (situation)"
    ),
    "lower_gi": SuspectedCancerSituation(
        "315274008",
        "Malignant neoplasm of lower gastrointestinal tract suspected (situation)",
    ),
    "upper_gi": SuspectedCancerSituation(
        "315273002",
        "Malignant neoplasm of upper gastrointestinal tract suspected (situation)",
    ),
    "urology": SuspectedCancerSituation(
        "397657005", "Malignant neoplasm of urinary system suspected (situation)"
    ),
    "prostate": SuspectedCancerSituation(
        "315268008", "Malignant neoplasm of prostate suspected (situation)"
    ),
    "gynae": SuspectedCancerSituation(
        "397682005",
        "Malignant neoplasm of female genital organ suspected (situation)",
    ),
    "skin": SuspectedCancerSituation(
        "315276005", "Malignant neoplasm of skin suspected (situation)"
    ),
    "head_neck": SuspectedCancerSituation(
        "315277001", "Malignant neoplasm of head and/or neck suspected (situation)"
    ),
    "lung": SuspectedCancerSituation(
        "162573006", "Malignant neoplasm of lung suspected (situation)"
    ),
    "haematology": SuspectedCancerSituation(
        "315275009", "Hematological malignancy suspected (situation)"
    ),
    "lymphoma": SuspectedCancerSituation(
        "315264005", "Malignant lymphoma suspected (situation)"
    ),
}

_SITE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("prostate", re.compile(r"\b(?:prostate|psa)\b", re.IGNORECASE)),
    (
        "lower_gi",
        re.compile(r"\b(?:lgi|lower\s+gi|bowel|colorectal|colon|fit)\b", re.IGNORECASE),
    ),
    (
        "upper_gi",
        re.compile(
            r"\b(?:ugi|upper\s+gi|oesophag|esophag|gastric|stomach)\b", re.IGNORECASE
        ),
    ),
    ("breast", re.compile(r"\bbreast\b", re.IGNORECASE)),
    (
        "gynae",
        re.compile(
            r"\b(?:gynae|gynaecology|gyne|vulva|vaginal|ovarian|uterine)\b",
            re.IGNORECASE,
        ),
    ),
    ("skin", re.compile(r"\b(?:skin|derm(?:atology)?|melanoma)\b", re.IGNORECASE)),
    (
        "head_neck",
        re.compile(
            r"\b(?:head\s+and\s+neck|ent|neck|throat|oral|mouth|tongue)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "lung",
        re.compile(
            r"\b(?:lung|chest|respiratory|cough|haemoptysis|hemoptysis)\b",
            re.IGNORECASE,
        ),
    ),
    ("lymphoma", re.compile(r"\blymphoma\b", re.IGNORECASE)),
    (
        "haematology",
        re.compile(
            r"\b(?:haematology|hematology|haematological|hematological|blood\s+cancer)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "urology",
        re.compile(
            r"\b(?:urology|uro|urinary|bladder|renal|kidney|testicular|testis)\b",
            re.IGNORECASE,
        ),
    ),
)

_TWW_TARGET_SITE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "head_neck",
        re.compile(
            r"\b(?:2\s*ww|tww|two\s+week\s+wait)\s+"
            r"(?:head\s+and\s+neck|neck|ent|throat|oral|mouth|tongue)\b|"
            r"\b(?:head\s+and\s+neck|neck|ent|throat|oral|mouth|tongue)"
            r"\s+(?:2\s*ww|tww|two\s+week\s+wait)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "skin",
        re.compile(
            r"\b(?:2\s*ww|tww|two\s+week\s+wait)\s+"
            r"(?:skin|derm(?:atology)?|melanoma)\b|"
            r"\b(?:skin|derm(?:atology)?|melanoma)\s+"
            r"(?:2\s*ww|tww|two\s+week\s+wait)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "breast",
        re.compile(
            r"\b(?:2\s*ww|tww|two\s+week\s+wait)\s+breast\b|"
            r"\bbreast\s+(?:2\s*ww|tww|two\s+week\s+wait)\b",
            re.IGNORECASE,
        ),
    ),
)


def recover_request_reason_findings(
    encounter_text: str,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add deterministic finding spans from ``Reasons for Request`` text."""

    return _recover_request_reason_entities(encounter_text, entities, {LABEL_FINDING})


def recover_request_reason_entities(
    encounter_text: str,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add deterministic entities from ``Reasons for Request`` text."""

    return _recover_request_reason_entities(
        encounter_text, entities, {LABEL_FINDING, LABEL_SITUATION}
    )


def _recover_request_reason_entities(
    encounter_text: str,
    entities: list[dict[str, Any]],
    labels: set[str],
) -> list[dict[str, Any]]:
    """Add selected deterministic entities from ``Reasons for Request`` text."""

    if not encounter_text:
        return list(entities)
    existing = _existing_regions(entities)
    additions: list[dict[str, Any]] = []
    for match in _REASON_BLOCK_RE.finditer(encounter_text):
        reason_start = match.start("reason")
        reason_text = match.group("reason")
        if LABEL_FINDING in labels:
            additions.extend(
                _reason_findings(encounter_text, reason_start, reason_text, existing)
            )
        if LABEL_SITUATION in labels:
            situation = _reason_situation(
                encounter_text, reason_start, reason_text, existing
            )
            if situation is not None:
                additions.append(situation)
    if not additions:
        return list(entities)
    return [*entities, *additions]


def propose_request_reason_entities(encounter_text: str) -> list[dict[str, Any]]:
    """Return request-reason entity proposals without considering existing entities."""

    return [
        entity
        for entity in recover_request_reason_entities(encounter_text, [])
        if entity.get(_RECOVERY_MARKER)
    ]


def propose_request_reason_findings(encounter_text: str) -> list[dict[str, Any]]:
    """Return request-reason finding proposals without considering existing entities."""

    return [
        entity
        for entity in recover_request_reason_findings(encounter_text, [])
        if entity.get(_RECOVERY_MARKER)
    ]


def _existing_regions(entities: list[dict[str, Any]]) -> set[tuple[str, int, int]]:
    regions: set[tuple[str, int, int]] = set()
    for entity in entities:
        label = str(entity.get("label") or entity.get("semantic_tag") or "").lower()
        try:
            start = int(entity.get("start", 0))
            end = int(entity.get("end", 0))
        except (TypeError, ValueError):
            continue
        regions.add((label, start, end))
    return regions


def _reason_findings(
    text: str,
    reason_start: int,
    reason_text: str,
    existing: set[tuple[str, int, int]],
) -> list[dict[str, Any]]:
    entities = []
    for finding in _REASON_FINDING_RE.finditer(reason_text):
        start = reason_start + finding.start()
        end = reason_start + finding.end()
        if _overlaps_existing(existing, LABEL_FINDING, start, end):
            continue
        entities.append(_build_finding(text, start, end))
        existing.add((LABEL_FINDING, start, end))
    return entities


def _reason_situation(
    text: str,
    reason_start: int,
    reason_text: str,
    existing: set[tuple[str, int, int]],
) -> dict[str, Any] | None:
    if not _TWO_WEEK_WAIT_RE.search(reason_text):
        return None
    start, end = _trim_reason_span(reason_start, reason_text)
    if _overlaps_existing(existing, LABEL_SITUATION, start, end):
        return None
    site = _infer_suspected_cancer_site(reason_text)
    situation = _SUSPECTED_CANCER_BY_SITE[site]
    existing.add((LABEL_SITUATION, start, end))
    return _build_situation(text, start, end, situation)


def _trim_reason_span(reason_start: int, reason_text: str) -> tuple[int, int]:
    stripped = reason_text.strip(" \t.;,")
    leading = len(reason_text) - len(reason_text.lstrip(" \t"))
    return reason_start + leading, reason_start + leading + len(stripped)


def _infer_suspected_cancer_site(reason_text: str) -> str:
    lower = reason_text.lower()
    if re.search(r"\b(?:nss|non[-\s]?site[-\s]?specific)\b", lower):
        return "generic"
    for site, pattern in _TWW_TARGET_SITE_PATTERNS:
        if pattern.search(reason_text):
            return site
    for site, pattern in _SITE_PATTERNS:
        if pattern.search(reason_text):
            return site
    return "generic"


def _overlaps_existing(
    existing: set[tuple[str, int, int]],
    label: str,
    start: int,
    end: int,
) -> bool:
    return any(
        existing_label == label and start < existing_end and existing_start < end
        for existing_label, existing_start, existing_end in existing
    )


def _build_finding(text: str, start: int, end: int) -> dict[str, Any]:
    return {
        "text": text[start:end],
        "label": LABEL_FINDING,
        "semantic_tag": LABEL_FINDING,
        "start": start,
        "end": end,
        "assertion": "present",
        "confidence": 0.0,
        _RECOVERY_MARKER: True,
    }


def _build_situation(
    text: str,
    start: int,
    end: int,
    situation: SuspectedCancerSituation,
) -> dict[str, Any]:
    return {
        "text": text[start:end],
        "label": LABEL_SITUATION,
        "semantic_tag": LABEL_SITUATION,
        "start": start,
        "end": end,
        "assertion": "present",
        "confidence": 0.0,
        "snomed_concept_id": situation.concept_id,
        "snomed_term": situation.snomed_term,
        _RECOVERY_MARKER: True,
    }


__all__ = [
    "propose_request_reason_entities",
    "propose_request_reason_findings",
    "recover_request_reason_entities",
    "recover_request_reason_findings",
]
