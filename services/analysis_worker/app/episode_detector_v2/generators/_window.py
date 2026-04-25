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


def _rulebook_window_days(site_key: str | None) -> tuple[int, int]:
    """Return the configured detection window for a site."""
    if not site_key:
        return DEFAULT_LOOKBACK_DAYS, DEFAULT_LOOKAHEAD_DAYS
    try:
        from libs.episode_detector.loader import current_bundle

        rb = current_bundle().get(site_key)
    except Exception:
        rb = None
    if rb is None:
        return DEFAULT_LOOKBACK_DAYS, DEFAULT_LOOKAHEAD_DAYS
    return rb.windows.lookback_days, rb.windows.lookahead_days


def encounters_in_window(
    events: list[TimelineEvent],
    *,
    anchor_date: date,
    site_key: str | None = None,
    lookback_days: int | None = None,
    lookahead_days: int | None = None,
) -> list[str]:
    """Return encounter ids whose date falls inside the window.

    Deterministic order (chronological).
    """
    default_lookback, default_lookahead = _rulebook_window_days(site_key)
    resolved_lookback = lookback_days if lookback_days is not None else default_lookback
    resolved_lookahead = (
        lookahead_days if lookahead_days is not None else default_lookahead
    )
    start = anchor_date - timedelta(days=resolved_lookback)
    end = anchor_date + timedelta(days=resolved_lookahead)
    return [evt.encounter_id for evt in events if start <= evt.occurred_on <= end]


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
