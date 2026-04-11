"""Situation lookup normalisation for UK primary care NER entities.

Context assertion detection (negation, historical, hypothetical, declined)
has been moved to libs/ner/context_engine.py which uses MedSpaCy ConText.

This module retains only normalize_situation_lookup(), which rewrites
freeform situation-entity text to SNOMED-friendly lookup terms.  This is
a distinct concern from assertion classification and is kept here as a
lightweight, dependency-free helper.
"""

from __future__ import annotations

import re

_SITUATION_NORMALIZATIONS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\b(?:2ww|two\s+week\s+wait)\s+referral\b", re.I),
        "fast track referral",
    ),
    (
        re.compile(r"\b(?:on\s+)?waiting\s+list\s+(?:for|to)\b", re.I),
        "planned procedure",
    ),
    (re.compile(r"\bbooked\s+(?:for|in)\b", re.I), "planned procedure"),
    (re.compile(r"\bscheduled\s+(?:for|to)\b", re.I), "planned procedure"),
    (
        re.compile(
            r"\bplanned\s+(?:procedure|operation|surgery|intervention|admission|discharge)\b",
            re.I,
        ),
        "planned procedure",
    ),
    (
        re.compile(
            r"\bawaiting\s+(?:procedure|operation|surgery|biopsy|scan|investigation)\b",
            re.I,
        ),
        "planned procedure",
    ),
    (re.compile(r"\bawaiting\s+(?:results?|report|opinion|review)\b", re.I), None),
    (re.compile(r"\breferred\s+(?:for|to)\b", re.I), "referral to service"),
    (re.compile(r"\breferral\s+(?:for|to)\b", re.I), "referral to service"),
]


def normalize_situation_lookup(entity_text: str) -> str | None:
    """Return a SNOMED-friendly lookup term for freeform situation phrases.

    Returns None if no normalization pattern matches, meaning the original
    text should be used as-is for terminology lookup.
    """
    for pattern, canonical in _SITUATION_NORMALIZATIONS:
        if pattern.search(entity_text):
            return canonical
    return None
