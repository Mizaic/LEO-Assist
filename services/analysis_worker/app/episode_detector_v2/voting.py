"""Generator-consensus voting and confidence-tier assignment.

Atlas trace:
  DI: DI-8A5FCF4F
  Mitigates: R-1276F86C (silent-drop), R-451E161F (over-confident auto)

Counts how many independent generators (or channels) backed each
candidate. Assigns publishing tier:

- ``auto``    -- 2+ generator votes, channel diversity >= 2,
                 site is auto_publish-eligible (see site_keys.py).
- ``suggest`` -- 2+ generator votes OR (1 vote AND channel diversity >= 2).
- ``review``  -- everything else: needs human review before persistence.
"""

from __future__ import annotations

from collections.abc import Sequence

from .aggregator import AggregatedCandidate
from .site_keys import is_auto_eligible


def vote_for_candidates(
    aggregated: Sequence[AggregatedCandidate],
) -> dict[str, list[str]]:
    """Return a map of (site_key, anchor_event_id) -> list of generator names."""
    votes: dict[str, list[str]] = {}
    for agg in aggregated:
        cand = agg.candidate
        key = f"{cand.site_key}|{cand.anchor_event_id}"
        votes.setdefault(key, []).append(cand.generator)
    return {k: sorted(set(v)) for k, v in votes.items()}


def assign_confidence_tier(
    aggregated: AggregatedCandidate,
    consensus: list[str],
) -> tuple[str, list[str]]:
    """Return (tier, review_reasons)."""
    cand = aggregated.candidate
    diversity = aggregated.channel_diversity
    vote_count = len(consensus)
    site_auto = is_auto_eligible(cand.site_key)
    reasons: list[str] = []

    if vote_count >= 2 and diversity >= 2 and site_auto:
        return "auto", reasons

    if vote_count >= 2 or diversity >= 2:
        if not site_auto:
            reasons.append("site_not_auto_eligible_in_v1")
        return "suggest", reasons

    reasons.append("insufficient_consensus")
    if diversity < 2:
        reasons.append("single_channel_evidence")
    if vote_count < 2:
        reasons.append("single_generator_vote")
    if not site_auto:
        reasons.append("site_not_auto_eligible_in_v1")
    return "review", reasons
