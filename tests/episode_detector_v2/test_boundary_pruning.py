"""Tests for v2 episode boundary pruning."""

from __future__ import annotations

from datetime import date

from services.analysis_worker.app.episode_detector_v2.aggregator import (
    AggregatedCandidate,
)
from services.analysis_worker.app.episode_detector_v2.boundary import detect_boundary
from services.analysis_worker.app.episode_detector_v2.resolver import resolve_conflicts
from services.analysis_worker.app.episode_detector_v2.types import (
    CandidateEpisode,
    Signal,
    TimelineEvent,
)


def _event(encounter_id: str, occurred_on: date) -> TimelineEvent:
    return TimelineEvent(
        encounter_id=encounter_id,
        occurred_on=occurred_on,
        event_kind="encounter",
    )


def _candidate(
    candidate_id: str,
    *,
    anchor_event_id: str,
    anchor_date: date,
    encounter_ids: list[str],
    generator: str = "diagnosis_anchored",
) -> CandidateEpisode:
    return CandidateEpisode(
        candidate_id=candidate_id,
        site_key="breast",
        generator=generator,
        encounter_ids=encounter_ids,
        anchor_event_id=anchor_event_id,
        anchor_date=anchor_date,
        role_hint="diagnosis",
        intent_hint="confirmed",
    )


def _signal(
    encounter_id: str,
    *,
    channel: str,
    role: str,
    intent: str = "confirmed",
    confidence: float = 0.8,
) -> Signal:
    return Signal(
        channel=channel,
        encounter_id=encounter_id,
        site_key="breast",
        role=role,
        intent=intent,
        confidence=confidence,
    )


def test_boundary_ignores_context_only_signals_for_start_date():
    candidate = _candidate(
        "cand",
        anchor_event_id="dx",
        anchor_date=date(2025, 3, 24),
        encounter_ids=["context", "dx"],
    )
    aggregated = AggregatedCandidate(
        candidate=candidate,
        evidence_weight=1.0,
        channel_diversity=2,
        signals_by_channel={
            "text": [
                _signal(
                    "context",
                    channel="text",
                    role="context_milestone",
                    intent="unspecified",
                )
            ],
            "code": [_signal("dx", channel="code", role="diagnosis")],
        },
    )

    boundary = detect_boundary(
        aggregated,
        [_event("context", date(2025, 1, 21)), _event("dx", date(2025, 3, 24))],
    )

    assert boundary.start_date == date(2025, 3, 24)
    assert boundary.intent == "confirmed"


def test_benign_closure_reopens_when_later_record_mentions_breast_cancer():
    candidate = _candidate(
        "cand",
        anchor_event_id="normal",
        anchor_date=date(2025, 9, 1),
        encounter_ids=["normal"],
    )
    aggregated = AggregatedCandidate(
        candidate=candidate,
        evidence_weight=1.0,
        channel_diversity=1,
        signals_by_channel={
            "code": [
                _signal(
                    "normal",
                    channel="code",
                    role="outcome",
                    intent="ruled_out",
                )
            ],
        },
    )

    boundary = detect_boundary(
        aggregated,
        [
            _event("normal", date(2025, 9, 1)),
            TimelineEvent(
                encounter_id="later",
                occurred_on=date(2025, 10, 1),
                event_kind="encounter",
                text_snippet="Problem: History of breast cancer.",
            ),
        ],
    )

    assert boundary.status == "open"
    assert boundary.intent == "confirmed"
    assert boundary.end_date is None


def test_resolver_collapses_overlapping_same_site_candidates():
    early = AggregatedCandidate(
        candidate=_candidate(
            "cand-early",
            anchor_event_id="early",
            anchor_date=date(2025, 3, 14),
            encounter_ids=["a", "b", "c"],
            generator="site_cohort_anchored",
        ),
        evidence_weight=1.0,
        channel_diversity=1,
        signals_by_channel={},
    )
    diagnosis = AggregatedCandidate(
        candidate=_candidate(
            "cand-dx",
            anchor_event_id="dx",
            anchor_date=date(2025, 3, 24),
            encounter_ids=["a", "b", "c"],
            generator="diagnosis_anchored",
        ),
        evidence_weight=1.0,
        channel_diversity=1,
        signals_by_channel={},
    )

    resolved = resolve_conflicts([early, diagnosis])

    assert [agg.candidate.candidate_id for agg in resolved] == ["cand-dx"]
