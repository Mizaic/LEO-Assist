"""Shared windowing helpers for candidate generators.

Atlas trace:
  DI: DI-8A5FCF4F

Plain functions only -- so the candidate generators stay pure and easy
to test.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

from ..types import TimelineEvent


# Default window: 365 days backwards, 730 days forwards from the anchor.
# These match the historical episode_builder defaults so the regression
# cohort is a like-for-like comparison.
DEFAULT_LOOKBACK_DAYS = 365
DEFAULT_LOOKAHEAD_DAYS = 730


def encounters_in_window(
    events: list[TimelineEvent],
    *,
    anchor_date: date,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
) -> list[str]:
    """Return encounter ids whose date falls inside the window.

    Deterministic order (chronological).
    """
    start = anchor_date - timedelta(days=lookback_days)
    end = anchor_date + timedelta(days=lookahead_days)
    return [
        evt.encounter_id
        for evt in events
        if start <= evt.occurred_on <= end
    ]


def candidate_id(
    *,
    patient_id: str,
    site_key: str,
    generator: str,
    anchor_date: date,
) -> str:
    """Stable, content-addressed candidate id."""
    raw = f"{patient_id}|{site_key.lower()}|{generator}|{anchor_date.isoformat()}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"cand-{digest}"
