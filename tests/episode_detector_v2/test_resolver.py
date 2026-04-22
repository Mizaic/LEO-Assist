"""Tests for episode_detector_v2.resolver.

Atlas trace:
  DI: DI-8A5FCF4F
"""

from __future__ import annotations

from datetime import date

from services.analysis_worker.app.episode_detector_v2.aggregator import (
    AggregatedCandidate,
)
from services.analysis_worker.app.episode_detector_v2.resolver import (
    resolve_conflicts,
)
from services.analysis_worker.app.episode_detector_v2.types import (
    CandidateEpisode,
    Signal,
)


def _agg(candidate_id: str, *, site="breast", anchor="enc-1", weight=1.0) -> AggregatedCandidate:
    cand = CandidateEpisode(
        candidate_id=candidate_id,
        site_key=site,
        generator="referral_anchored",
        encounter_ids=["enc-1"],
        anchor_event_id=anchor,
        anchor_date=date(2024, 3, 15),
    )
    sig = Signal(
        channel="pathway",
        encounter_id=anchor,
        site_key=site,
        role="referral",
        intent="suspected",
        confidence=weight,
    )
    return AggregatedCandidate(
        candidate=cand,
        evidence_weight=weight,
        channel_diversity=1,
        signals_by_channel={"pathway": [sig]},
    )


def test_higher_weight_wins_within_same_anchor():
    a = _agg("c-a", weight=0.5)
    b = _agg("c-b", weight=1.5)
    survivors = resolve_conflicts([a, b])
    assert [s.candidate.candidate_id for s in survivors] == ["c-b"]


def test_tie_broken_deterministically_by_candidate_id():
    a = _agg("c-a", weight=1.0)
    b = _agg("c-b", weight=1.0)
    survivors = resolve_conflicts([b, a])
    assert [s.candidate.candidate_id for s in survivors] == ["c-a"]


def test_two_sites_coexist_no_competition():
    breast = _agg("c-breast", site="breast")
    lung = _agg("c-lung", site="lung", anchor="enc-2")
    survivors = resolve_conflicts([breast, lung])
    assert {s.candidate.site_key for s in survivors} == {"breast", "lung"}


def test_returns_empty_for_empty_input():
    assert resolve_conflicts([]) == []
