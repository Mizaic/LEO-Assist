"""NHS number and UBRN helpers for paused extraction review.

Prefers identifiers from the patient graph. Falls back to labelled
values in the letter so the reviewer can still copy them.

Atlas trace: DI-4A012A59
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NHS_LABELED = re.compile(
    r"(?:NHS\s*(?:No\.?|Number)?)\s*[:#-]?\s*(\d{3}[\s-]?\d{3}[\s-]?\d{4})",
    re.IGNORECASE,
)
_NHS_BARE = re.compile(r"\b(\d{3}[\s-]\d{3}[\s-]\d{4})\b")
_UBRN_LABELED = re.compile(
    r"(?:UBRN|Unique Booking Reference(?: Number)?)\s*[:#-]?\s*"
    r"(\d{4}[\s-]?\d{4}[\s-]?\d{4})",
    re.IGNORECASE,
)
_UBRN_BARE = re.compile(r"\b(\d{4}[\s-]\d{4}[\s-]\d{4})\b")


@dataclass(frozen=True)
class ReviewIdentifiers:
    nhs_number: str = ""
    ubrn: str = ""


def compact_digits(raw: str) -> str:
    return "".join(ch for ch in str(raw or "") if ch.isdigit())


def format_nhs_number(raw: str) -> str:
    digits = compact_digits(raw)
    if len(digits) != 10:
        return ""
    return f"{digits[:3]} {digits[3:6]} {digits[6:]}"


def format_ubrn(raw: str) -> str:
    digits = compact_digits(raw)
    if len(digits) != 12:
        return ""
    return f"{digits[:4]} {digits[4:8]} {digits[8:]}"


def extract_review_identifiers(
    letter: str,
    *,
    graph_nhs_number: str = "",
    graph_ubrn: str = "",
) -> ReviewIdentifiers:
    nhs = compact_digits(graph_nhs_number) or _first_match(
        letter, _NHS_LABELED, _NHS_BARE
    )
    ubrn = compact_digits(graph_ubrn) or _first_match(
        letter, _UBRN_LABELED, _UBRN_BARE
    )
    if len(nhs) != 10:
        nhs = ""
    if len(ubrn) != 12:
        ubrn = ""
    return ReviewIdentifiers(nhs_number=nhs, ubrn=ubrn)


def _first_match(text: str, *patterns: re.Pattern[str]) -> str:
    for pattern in patterns:
        found = pattern.search(text or "")
        if found:
            return compact_digits(found.group(1))
    return ""
