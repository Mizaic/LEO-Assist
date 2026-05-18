"""Generator-consensus voting and confidence-tier assignment.

Atlas trace:
  DI: DI-8A5FCF4F
  DI: DI-2C015ADE (context-tier milestone enforcement)
  Mitigates: R-1276F86C (silent-drop), R-451E161F (over-confident auto),
             R-76D26C56 (AI-written context milestones require human review)

Counts how many independent generators (or channels) backed each
candidate. Assigns publishing tier:

- ``auto``    -- 2+ generator votes, channel diversity >= 2,
                 site is auto_publish-eligible (see site_keys.py),
                 AND no supporting signal carries role="context_milestone".
                 Fast-track/seen/diagnosis anchors with 3+ independent
                 evidence channels also qualify without result-only
                 generators.
- ``suggest`` -- 2+ generator votes OR (1 vote AND channel diversity >= 2),
                 AND no context_milestone signal present.
- ``review``  -- everything else, OR any context_milestone signal is present.

The context_milestone guard is belt-and-suspenders for the v2 detector
path: the episode_engine writer enforces the same rule via
_has_context_tier_milestone -> status=REVIEW. Both gates must agree.
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


def _has_context_milestone_signal(aggregated: AggregatedCandidate) -> bool:
    """Return True when any supporting signal is role='context_milestone'.

    DI-2C015ADE: the presence of an AI-proposed context-tier milestone
    signal forces the tier to at most 'suggest', never 'auto'. The
    episode_engine writer has an independent enforcement path.
    """
    return any(
        getattr(s, "role", "") == "context_milestone"
        for signals in aggregated.signals_by_channel.values()
        for s in signals
    )


def assign_confidence_tier(
    aggregated: AggregatedCandidate,
    consensus: list[str],
) -> tuple[str, list[str]]:
    """Return (tier, review_reasons)."""
    cand = aggregated.candidate
    diversity = aggregated.channel_diversity
    vote_count = len(consensus)
    site_auto = is_auto_eligible(cand.site_key)
    has_ctx = _has_context_milestone_signal(aggregated)
    reasons: list[str] = []

    strong_single_anchor = (
        cand.role_hint in {"referral", "first_seen", "diagnosis"} and diversity >= 3
    )
    if (
        (vote_count >= 2 or strong_single_anchor)
        and diversity >= 2
        and site_auto
        and not has_ctx
    ):
        return "auto", reasons

    if vote_count >= 2 or diversity >= 2:
        if not site_auto:
            reasons.append("site_not_auto_eligible_in_v1")
        if has_ctx:
            reasons.append("context_milestone_requires_review")
            return "suggest", reasons
        return "suggest", reasons

    reasons.append("insufficient_consensus")
    if diversity < 2:
        reasons.append("single_channel_evidence")
    if vote_count < 2:
        reasons.append("single_generator_vote")
    if not site_auto:
        reasons.append("site_not_auto_eligible_in_v1")
    if has_ctx:
        reasons.append("context_milestone_requires_review")
    return "review", reasons
