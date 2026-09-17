"""Parse one clinical observation date from letter text.

Atlas trace:
  DI: DI-0BB36B4D
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-0BB36B4D")

Owned surface: the :DOCUMENTS.observed_at property. Do not invent a second
date map. Two different dates in the same text are not guessed.
"""

from __future__ import annotations

from datetime import date
import re
from typing import Any

# Shared with taught blood-table cells (lab_result_evidence).
DATE_TOKEN = (
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}"
    r"|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
)

_DATE_RE = re.compile(DATE_TOKEN)

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _century_year(year: int) -> int:
    if year >= 100:
        return year
    return 2000 + year


def _iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(_century_year(year), month, day).isoformat()
    except ValueError:
        return None


def _token_to_iso(token: str) -> str | None:
    raw = token.strip()
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if iso:
        return _iso(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    words = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{2,4})", raw)
    if words:
        month = _MONTHS.get(words.group(2).lower())
        if month is None:
            return None
        return _iso(int(words.group(3)), month, int(words.group(1)))
    numeric = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", raw)
    if numeric:
        return _iso(int(numeric.group(3)), int(numeric.group(2)), int(numeric.group(1)))
    return None


def parse_observation_date(text: str) -> str | None:
    """Return YYYY-MM-DD when the text holds exactly one calendar date."""
    found: set[str] = set()
    for match in _DATE_RE.finditer(text or ""):
        parsed = _token_to_iso(match.group(0))
        if parsed:
            found.add(parsed)
        if len(found) > 1:
            return None
    if len(found) == 1:
        return next(iter(found))
    return None


_FINDING_LABELS = frozenset(
    {"finding", "clinical_finding", "disorder", "disease", "situation"}
)


def _line_at(text: str, index: int) -> str:
    if not text:
        return ""
    pos = max(0, min(index, len(text)))
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end == -1:
        end = len(text)
    return text[start:end]


def assign_finding_observed_at(
    encounter_text: str, entities: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Stamp observed_at on findings and disorders with exactly one line date."""
    for ent in entities:
        if str(ent.get("observed_at") or "").strip():
            continue
        label = str(ent.get("label") or ent.get("semantic_tag") or "").lower()
        if label not in _FINDING_LABELS:
            continue
        start = int(ent.get("start") or 0)
        line = _line_at(encounter_text, start)
        observed = parse_observation_date(line) or parse_observation_date(
            str(ent.get("text") or "")
        )
        if observed:
            ent["observed_at"] = observed
    return entities
