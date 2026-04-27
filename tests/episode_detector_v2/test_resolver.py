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


def _agg(
    candidate_id: str,
    *,
    site="breast",
    anchor="enc-1",
    anchor_date=date(2024, 3, 15),
    encounter_ids: list[str] | None = None,
    weight=1.0,
) -> AggregatedCandidate:
    cand = CandidateEpisode(
        candidate_id=candidate_id,
        site_key=site,
        generator="referral_anchored",
        encounter_ids=encounter_ids or ["enc-1"],
        anchor_event_id=anchor,
        anchor_date=anchor_date,
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


def test_same_site_distant_anchors_merge_when_encounter_windows_overlap():
    first = _agg(
        "c-first",
        anchor="referral-2024",
        anchor_date=date(2024, 6, 10),
        encounter_ids=["shared", "referral-2024"],
    )
    second = _agg(
        "c-second",
        anchor="referral-2025",
        anchor_date=date(2025, 4, 22),
        encounter_ids=["shared", "referral-2025"],
    )
    # Broad windows can share encounters while anchors sit far apart; one
    # clinical episode should survive with merged encounter membership.
    first.signals_by_channel["code"] = [
        Signal(
            channel="code",
            encounter_id="shared",
            site_key="breast",
            role="diagnosis",
            intent="suspected",
            confidence=0.5,
        )
    ]
    second.signals_by_channel["code"] = list(first.signals_by_channel["code"])

    survivors = resolve_conflicts([first, second])

    assert len(survivors) == 1
    assert set(survivors[0].candidate.encounter_ids) == {
        "shared",
        "referral-2024",
        "referral-2025",
    }
    assert survivors[0].consensus_generators == ("referral_anchored",)


def test_same_site_distant_anchors_stay_separate_when_windows_disjoint():
    first = _agg(
        "c-first",
        anchor="referral-2024",
        anchor_date=date(2024, 6, 10),
        encounter_ids=["a", "referral-2024"],
    )
    second = _agg(
        "c-second",
        anchor="referral-2025",
        anchor_date=date(2025, 4, 22),
        encounter_ids=["x", "referral-2025"],
    )

    survivors = resolve_conflicts([first, second])

    assert {s.candidate.candidate_id for s in survivors} == {"c-first", "c-second"}
