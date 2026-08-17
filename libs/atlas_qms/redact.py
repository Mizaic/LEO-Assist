"""Redact NHS numbers and referral numbers before Atlas writeback.

Atlas: DI-ED5A9AC3
"""

from __future__ import annotations

import re

from libs.utils.deidentify import NHS_RE

NHS_PLACEHOLDER = "[NHS_NUMBER]"
UBRN_PLACEHOLDER = "[UBRN]"
UBRN_LABELED = re.compile(
    r"\b(?:UBRN|referral(?:\s+number)?)[:\s#-]*"
    r"(?:\d{4}[\s-]?\d{4}[\s-]?\d{4}|[A-Z0-9]{6,})\b",
    re.I,
)
UBRN_GROUPED = re.compile(r"\b\d{4}[\s-]\d{4}[\s-]\d{4}\b")
UBRN_12 = re.compile(r"\b\d{12}\b")


def redact_for_atlas(text: str) -> str:
    """Replace NHS numbers and referral numbers. Keep the rest."""
    out = UBRN_LABELED.sub(UBRN_PLACEHOLDER, text or "")
    out = UBRN_GROUPED.sub(UBRN_PLACEHOLDER, out)
    out = UBRN_12.sub(UBRN_PLACEHOLDER, out)
    return NHS_RE.sub(NHS_PLACEHOLDER, out)


def contains_identifiers(text: str) -> bool:
    raw = text or ""
    return bool(
        UBRN_LABELED.search(raw)
        or UBRN_GROUPED.search(raw)
        or UBRN_12.search(raw)
        or NHS_RE.search(raw)
    )
