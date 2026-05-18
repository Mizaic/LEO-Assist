"""Coverage check tests -- silent drop must be impossible.

Atlas trace:
  DI: DI-8A5FCF4F
  Mitigates R-1276F86C (silent-drop)
"""

from __future__ import annotations

from datetime import date

from services.analysis_worker.app.episode_detector_v2.coverage import check_coverage
from services.analysis_worker.app.episode_detector_v2.types import (
    ResolvedEpisode,
    Signal,
    TimelineEvent,
)


def _evt(eid: str) -> TimelineEvent:
    return TimelineEvent(
        encounter_id=eid,
        occurred_on=date(2024, 3, 15),
        event_kind="encounter",
    )


def _sig(eid: str) -> Signal:
    return Signal(
        channel="code",
        encounter_id=eid,
        site_key="breast",
        role="diagnosis",
        intent="suspected",
        confidence=0.8,
    )


def _ep(eid: str, encs: list[str]) -> ResolvedEpisode:
    return ResolvedEpisode(
        episode_id=eid,
        site_key="breast",
        encounter_ids=encs,
        start_date=date(2024, 3, 15),
        end_date=date(2024, 3, 15),
        suspected_site="breast",
        role="diagnosis",
        intent="suspected",
        status="open",
        confidence_tier="auto",
        needs_human_review=False,
        review_reasons=[],
        vote_count=2,
        supporting_signals=[],
        alternatives_considered=[],
        generator_consensus=[],
    )


def test_complete_coverage_when_all_encounters_in_episode():
    events = [_evt("a"), _evt("b")]
    signals = [_sig("a")]
    episodes = [_ep("ep-1", ["a", "b"])]
    report = check_coverage(events, signals, episodes)
    assert report.is_complete


def test_off_pathway_encounters_classified_as_no_signal():
    """Encounter b has no signal and is far from any in-episode date,
    so it falls into ``encounter_ids_no_signal``.
    """
    events = [
        _evt("a"),
        # Use a far-away date so adjacency does not pull it in.
        TimelineEvent(
            encounter_id="b",
            occurred_on=date(2025, 6, 1),
            event_kind="encounter",
        ),
    ]
    signals = [_sig("a")]
    episodes = [_ep("ep-1", ["a"])]
    report = check_coverage(events, signals, episodes)
    assert report.is_complete
    assert "b" in report.encounter_ids_no_signal
    # Backwards-compat alias still resolves.
    assert "b" in report.encounter_ids_explicitly_off_pathway


def test_no_signal_encounter_within_adjacency_window_marked_adjacent():
    """A no-signal encounter within +/- 90 days of an in-episode
    encounter for an active confirmed episode is recorded in the
    adjacency bucket so the orchestrator can attach it to the active
    episode's follow-up if a curator agrees.
    """
    events = [_evt("a"), _evt("b-near")]  # both 2024-03-15
    signals = [_sig("a")]
    ep = _ep("ep-1", ["a"])
    ep.intent = "confirmed"
    report = check_coverage(events, signals, [ep])
    assert report.is_complete
    assert "b-near" in report.encounter_ids_adjacent_to_active_episode
    assert "b-near" not in report.encounter_ids_no_signal


def test_ruled_out_episode_does_not_emit_adjacency_anchors():
    """An adjacency claim only makes clinical sense for an active
    episode. A ruled_out episode must NOT pull nearby no-signal
    encounters into adjacency.
    """
    events = [_evt("a"), _evt("b-near")]
    signals = [_sig("a")]
    ep = _ep("ep-1", ["a"])
    ep.intent = "ruled_out"
    report = check_coverage(events, signals, [ep])
    assert "b-near" in report.encounter_ids_no_signal
    assert "b-near" not in report.encounter_ids_adjacent_to_active_episode


def test_unaccounted_encounter_with_signal_breaks_coverage():
    events = [_evt("a"), _evt("b")]
    signals = [_sig("a"), _sig("b")]
    episodes = [_ep("ep-1", ["a"])]
    report = check_coverage(events, signals, episodes)
    assert not report.is_complete
    assert report.encounter_ids_unaccounted == ["b"]


def test_silent_drop_is_caught():
    """Phase-1 fail-safe: encounters in two pathways with one resolved
    should leave the dropped pathway as unaccounted, not silently
    swallow it.
    """
    events = [_evt(f"e-{i}") for i in range(4)]
    signals = [_sig("e-0"), _sig("e-1"), _sig("e-2"), _sig("e-3")]
    episodes = [_ep("ep-only", ["e-0", "e-1"])]
    report = check_coverage(events, signals, episodes)
    assert set(report.encounter_ids_unaccounted) == {"e-2", "e-3"}
    assert not report.is_complete
