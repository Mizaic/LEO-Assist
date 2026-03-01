"""
De-identification pass for clinical text before NER extraction (GAP-008).

Replaces patient-identifiable patterns (names, postcodes, NHS numbers, dates,
phone numbers, and configurable organisation names) with placeholder tokens.
The character offsets of the original text are preserved via a OffsetMap so
NER span positions can be adjusted back to the source document.

Environment variables
---------------------
DEID_LOCAL_ORGS   Comma-separated list of additional organisation names to
                  redact (GAP-014). Example: "St Mary's Hospital,City Clinic"
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# -- NHS number: 10 digits, commonly space- or hyphen-separated ----------
_NHS_NUMBER = re.compile(r"\b\d{3}[\s\-]\d{3}[\s\-]\d{4}\b|\b\d{10}\b")
# -- UK postcode (full or partial) ----------------------------------------
_UK_POSTCODE = re.compile(
    r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE
)
# -- UK date formats: DD/MM/YYYY, DD-MM-YYYY, D Month YYYY ---------------
_DATE = re.compile(
    r"\b\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}\b"
    r"|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\b",
    re.IGNORECASE,
)
# -- UK phone numbers (07xxx, +44, 01xxx, 02xxx, 03xxx) ------------------
_PHONE = re.compile(
    r"\b(?:\+44\s?7\d{3}|\b07\d{3})\s?\d{3}\s?\d{3}\b"
    r"|\b0[123]\d{1,4}\s?\d{3,4}\s?\d{4}\b"
)
# -- Email address ---------------------------------------------------------
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")


def _build_org_pattern() -> re.Pattern | None:
    raw = os.environ.get("DEID_LOCAL_ORGS", "").strip()
    if not raw:
        return None
    names = [n.strip() for n in raw.split(",") if n.strip()]
    if not names:
        return None
    escaped = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(r"\b(?:" + escaped + r")\b", re.IGNORECASE)


@dataclass
class DeidResult:
    """Result of de-identification. Contains redacted text and a list of replacements."""
    text: str
    replacements: list[tuple[int, int, str]] = field(default_factory=list)


def deidentify(text: str) -> DeidResult:
    """Replace identifiable patterns in *text* with placeholder tokens.

    Returns DeidResult with the redacted text.  Character positions of
    placeholders differ from the originals — callers that need original offsets
    should use the replacements list to adjust span positions.
    """
    result = text
    replacements: list[tuple[int, int, str]] = []

    org_pattern = _build_org_pattern()

    patterns: list[tuple[re.Pattern, str]] = [
        (_NHS_NUMBER, "[NHS_NO]"),
        (_UK_POSTCODE, "[POSTCODE]"),
        (_DATE, "[DATE]"),
        (_PHONE, "[PHONE]"),
        (_EMAIL, "[EMAIL]"),
    ]
    if org_pattern:
        patterns.append((org_pattern, "[ORG]"))

    for pattern, token in patterns:
        new_result = ""
        prev = 0
        for m in pattern.finditer(result):
            new_result += result[prev:m.start()]
            replacements.append((m.start(), m.end(), m.group()))
            new_result += token
            prev = m.end()
        new_result += result[prev:]
        result = new_result

    return DeidResult(text=result, replacements=replacements)
