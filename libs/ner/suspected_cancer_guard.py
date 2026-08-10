"""Guards against coding suspected referrals as confirmed malignancy disorders.

Atlas trace (related):
  DI: DI-95CB940F (situation assertion present)
  DO: DO-847F1ED5
"""

from __future__ import annotations

import re
from typing import Any

from libs.domains.ncda_concept_sets import CANCER_TYPE_IDS
from libs.ner.request_reason_recovery import (
    SUSPECTED_CANCER_BY_SITE,
    SuspectedCancerSituation,
    infer_suspected_cancer_site,
)

_GENERIC_SUSPECTED = SUSPECTED_CANCER_BY_SITE["generic"]
_SUSPECTED_SITUATION_IDS = frozenset(
    situation.concept_id for situation in SUSPECTED_CANCER_BY_SITE.values()
)

_SUSPECTED_CONTEXT_RE = re.compile(
    r"(?:"
    r"\bsuspected\b|"
    r"\b2\s*ww\b|\btww\b|\btwo\s+week\s+wait\b|\bfast\s+track\b|"
    r"suspected\s+cancer\s+pathway|"
    r"cancer\s+pathway\s+for\b|"
    r"\bassess(?:ment)?\s+for\b|"
    r"\bassessment\s+of\b|"
    r"\bexclude\s+(?:malignancy|cancer)\b|"
    r"\brule\s+out\b|"
    r"\binvestigate\s+for\b|"
    r"\bconcerning\s+for\b|"
    r"\bquery\s+\??\s*"
    r")",
    re.IGNORECASE,
)

_CANCER_SPAN_RE = re.compile(
    r"\b(?:"
    r"(?:oesophageal|esophageal|gastric|stomach|colorectal|bowel|breast|lung|"
    r"prostate|pancreatic|skin|cervical|ovarian|haematolog\w+|hematolog\w+|"
    r"lymphoma|melanoma|malignancy|cancer)"
    r")\b",
    re.IGNORECASE,
)

_SITE_FROM_TEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "upper_gi",
        re.compile(
            r"\b(?:ugi|upper\s+gi|oesophag\w*|esophag\w*|gastric|stomach)\b",
            re.IGNORECASE,
        ),
    ),
    ("breast", re.compile(r"\bbreast\b", re.IGNORECASE)),
    (
        "lower_gi",
        re.compile(r"\b(?:lgi|lower\s+gi|bowel|colorectal|colon|fit)\b", re.IGNORECASE),
    ),
    ("lung", re.compile(r"\b(?:lung|chest|respiratory)\b", re.IGNORECASE)),
    ("prostate", re.compile(r"\b(?:prostate|psa)\b", re.IGNORECASE)),
    ("skin", re.compile(r"\b(?:skin|derm(?:atology)?|melanoma)\b", re.IGNORECASE)),
)


def _infer_site_from_cancer_text(text: str) -> str:
    for site, pattern in _SITE_FROM_TEXT_PATTERNS:
        if pattern.search(text):
            return site
    return infer_suspected_cancer_site(text)


def _entity_blob(entity: dict[str, Any]) -> str:
    parts = [
        entity.get("text"),
        entity.get("evidence"),
        entity.get("normalized"),
        entity.get("normalized_lookup"),
        entity.get("lookup_term"),
        entity.get("term"),
    ]
    return " ".join(str(part) for part in parts if part)


def _sentence_window(encounter_text: str, start: int, end: int) -> str:
    if not encounter_text:
        return ""
    bounds_start = max(0, encounter_text.rfind(".", 0, start) + 1)
    bounds_end = encounter_text.find(".", end)
    if bounds_end == -1:
        bounds_end = len(encounter_text)
    return encounter_text[bounds_start:bounds_end]


def is_suspected_cancer_context(blob: str, sentence: str = "") -> bool:
    """Return True when text implies investigation, not confirmed diagnosis."""
    combined = f"{blob} {sentence}".strip()
    if not combined:
        return False
    if _SUSPECTED_CONTEXT_RE.search(combined):
        return True
    if re.search(r"\bsuspected\b.+\bcancer\b", combined, re.IGNORECASE):
        return True
    if re.search(r"\bmalignancy\b", combined, re.IGNORECASE) and re.search(
        r"\bassess|\bexclude|\brule\s+out|\binvestig", combined, re.IGNORECASE
    ):
        return True
    return False


def is_confirmed_malignancy_disorder(entity: dict[str, Any]) -> bool:
    """True when the resolved concept is a canonical confirmed cancer disorder."""
    concept_id = str(entity.get("concept_id") or "").strip()
    if not concept_id or concept_id in _SUSPECTED_SITUATION_IDS:
        return False
    try:
        numeric = int(concept_id)
    except ValueError:
        return False
    if numeric not in CANCER_TYPE_IDS:
        return False
    tag = str(entity.get("semantic_tag") or entity.get("label") or "").lower()
    term = str(entity.get("term") or "")
    if tag == "situation" or term.endswith("(situation)"):
        return False
    return True


def preferred_suspected_situation(
    blob: str, sentence: str = ""
) -> SuspectedCancerSituation:
    """Pick the site-specific suspected-cancer SNOMED situation."""
    combined = f"{blob} {sentence}".strip()
    site = _infer_site_from_cancer_text(combined)
    return SUSPECTED_CANCER_BY_SITE.get(site, _GENERIC_SUSPECTED)


def enrich_suspected_cancer_lookup(
    entity: dict[str, Any],
    encounter_text: str,
) -> None:
    """Set lookup_term to a suspected-situation phrase before terminology."""
    label = str(entity.get("label") or entity.get("semantic_tag") or "").lower()
    if label != "situation" and not _CANCER_SPAN_RE.search(_entity_blob(entity)):
        return

    start = int(entity.get("start", 0) or 0)
    end = int(entity.get("end", 0) or 0)
    sentence = _sentence_window(encounter_text, start, end)
    blob = _entity_blob(entity)
    if not is_suspected_cancer_context(blob, sentence):
        return

    situation = preferred_suspected_situation(blob, sentence)
    lookup = situation.snomed_term.replace(" (situation)", "").strip()
    entity["lookup_term"] = lookup
    entity["normalized"] = lookup
    entity["semantic_tag"] = "situation"
    entity["label"] = "situation"
    entity["_suspected_cancer_guard"] = "enriched_lookup"


def enrich_suspected_cancer_lookups(
    encounter_text: str,
    entities: list[dict[str, Any]],
) -> None:
    """Apply suspected-cancer lookup enrichment to all entities."""
    for entity in entities:
        enrich_suspected_cancer_lookup(entity, encounter_text)


def guard_suspected_cancer_resolution(
    entity: dict[str, Any],
    encounter_text: str,
) -> None:
    """Remap confirmed malignancy disorder codes in suspected context."""
    if not is_confirmed_malignancy_disorder(entity):
        return

    start = int(entity.get("start", 0) or 0)
    end = int(entity.get("end", 0) or 0)
    sentence = _sentence_window(encounter_text, start, end)
    blob = _entity_blob(entity)
    if not is_suspected_cancer_context(blob, sentence):
        label = str(entity.get("label") or "").lower()
        if label != "situation":
            return

    situation = preferred_suspected_situation(blob, sentence)
    term = situation.snomed_term
    if not term.endswith("(situation)"):
        term = f"{term} (situation)"
    entity.update(
        concept_id=situation.concept_id,
        term=term,
        semantic_tag="situation",
        label="situation",
        terminology_unresolved=False,
    )
    entity["_suspected_cancer_guard"] = "remapped_disorder_to_situation"


def guard_suspected_cancer_resolutions(
    encounter_text: str,
    entities: list[dict[str, Any]],
) -> None:
    """Remap all malignancy disorder miscodes in suspected referral context."""
    for entity in entities:
        guard_suspected_cancer_resolution(entity, encounter_text)


def _sentence_key(entity: dict[str, Any]) -> str:
    sentence_id = str(entity.get("__sentence_id") or "").strip()
    if sentence_id:
        return sentence_id
    start = int(entity.get("start", 0) or 0)
    end = int(entity.get("end", 0) or 0)
    return f"span:{start}:{end}"


def dedupe_suspected_malignancy_conflicts(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop confirmed malignancy when a suspected situation exists in same sentence."""
    suspected_by_sentence: dict[str, set[str]] = {}
    for entity in entities:
        concept_id = str(entity.get("concept_id") or "")
        if concept_id not in _SUSPECTED_SITUATION_IDS:
            continue
        tag = str(entity.get("semantic_tag") or entity.get("label") or "").lower()
        if tag != "situation" and not concept_id:
            continue
        key = _sentence_key(entity)
        suspected_by_sentence.setdefault(key, set()).add(concept_id)

    if not suspected_by_sentence:
        return entities

    kept: list[dict[str, Any]] = []
    for entity in entities:
        if not is_confirmed_malignancy_disorder(entity):
            kept.append(entity)
            continue
        key = _sentence_key(entity)
        if key in suspected_by_sentence:
            entity["__suppress__"] = True
            entity["_suspected_cancer_guard"] = "suppressed_duplicate_disorder"
            continue
        kept.append(entity)
    return [entity for entity in kept if not entity.get("__suppress__")]


__all__ = [
    "dedupe_suspected_malignancy_conflicts",
    "enrich_suspected_cancer_lookup",
    "enrich_suspected_cancer_lookups",
    "guard_suspected_cancer_resolution",
    "guard_suspected_cancer_resolutions",
    "is_confirmed_malignancy_disorder",
    "is_suspected_cancer_context",
]
