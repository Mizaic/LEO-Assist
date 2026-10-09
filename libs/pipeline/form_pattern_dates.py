"""Find dates the referrer typed into a taught heading or rule quote.

A start pattern is the form's printed heading. A date in it was copied
from one letter, so the next letter's heading would not match and the
section would be lost.

Atlas trace: DI-C1744ED5, DO-1C8E7598, DI-9BF69EC9
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)" r"[a-z]*\.?"
_DATE = re.compile(
    r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b"
    r"|\b\d{4}-\d{1,2}-\d{1,2}\b"
    rf"|\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH}\s+\d{{2,4}}\b",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def contains_date(text: str) -> bool:
    """True when *text* holds a calendar date such as 25/6/26."""
    return bool(_DATE.search(text or ""))


def drop_dated_sentences(pattern: str) -> str:
    """Remove each sentence that holds a date, and the stop before it."""
    if not contains_date(pattern):
        return pattern
    kept = [s for s in _SENTENCE_END.split(pattern) if not contains_date(s)]
    return " ".join(kept).strip().rstrip(".").strip()


def dated_start_pattern_message(sections: Iterable[dict[str, Any]]) -> str:
    """Plain-English refusal for the first section whose heading has a date."""
    for section in sections:
        if not contains_date(str(section.get("start_pattern") or "")):
            continue
        name = str(section.get("label") or section.get("section_id") or "").strip()
        return (
            f"The start pattern for '{name}' has a date in it. "
            "Use the form's printed heading only, then save again."
        )
    return ""


__all__ = ["contains_date", "dated_start_pattern_message", "drop_dated_sentences"]
