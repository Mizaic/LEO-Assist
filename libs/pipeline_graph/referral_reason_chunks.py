"""Rank referral-reason chunks so scan indications lose to the letter.

Atlas:
  DI: DI-41542A49
  DO: DO-4F133EE7
  VT: VT-95532C93
"""

from __future__ import annotations

from typing import Any

_SCAN_MARKERS: tuple[str, ...] = (
    "accession no",
    "this is a final report",
    "sonographer",
    "us pelvis:",
    "us pelvis transvaginal",
    "alert-cancer",
)

_PATTERN_SCORE: tuple[tuple[str, int], ...] = (
    ("the reason i am concerned this patient has cancer is", 100),
    ("further clinical details", 90),
    ("the reason for referral is", 85),
    ("i am referring this patient because", 80),
    ("reason i am referring", 75),
    ("reason for referral", 70),
    ("reasons for request", 65),
    ("reason for request", 65),
    ("referral criteria and clinical information", 40),
    ("referral information", 30),
    ("clinical information", 10),
)


def is_scan_report_chunk(text: str) -> bool:
    """True when the chunk is an imaging report, not the referral letter."""
    lowered = text.lower()
    return any(marker in lowered for marker in _SCAN_MARKERS)


def chunk_reason_score(text: str) -> int:
    """Higher scores are better reason-for-referral sources."""
    if is_scan_report_chunk(text):
        return 0
    lowered = text.lower()
    return max(
        (score for pattern, score in _PATTERN_SCORE if pattern in lowered),
        default=0,
    )


def select_reason_chunks(
    rows: list[dict[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return the best reason chunks. Drop scan reports when a letter exists."""
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for row in rows:
        text = str(row.get("text") or "")
        score = chunk_reason_score(text)
        if score <= 0:
            continue
        ordinal = int(row.get("ordinal") or 0)
        scored.append((score, ordinal, row))
    if not scored:
        return []
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [row for _score, _ordinal, row in scored[:limit]]
