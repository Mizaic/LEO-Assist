"""Tests for diagnosis-anchored candidate generation."""

from __future__ import annotations

from datetime import date

from services.analysis_worker.app.episode_detector_v2.generators.diagnosis_anchored import (
    generate_diagnosis_anchored,
)
from services.analysis_worker.app.episode_detector_v2.types import Signal, TimelineEvent


def _event(encounter_id: str) -> TimelineEvent:
    return TimelineEvent(
        encounter_id=encounter_id,
        occurred_on=date(2025, 1, 1),
        event_kind="encounter",
    )


def _code(encounter_id: str, intent: str) -> Signal:
    return Signal(
        channel="code",
        encounter_id=encounter_id,
        site_key="breast",
        role="diagnosis",
        intent=intent,
        confidence=0.90,
    )


def test_diagnosis_anchored_ignores_suspected_codes():
    candidates = generate_diagnosis_anchored(
        patient_id="patient",
        events=[_event("suspected")],
        signals=[_code("suspected", "suspected")],
    )

    assert candidates == []


def test_diagnosis_anchored_keeps_confirmed_codes():
    candidates = generate_diagnosis_anchored(
        patient_id="patient",
        events=[_event("confirmed")],
        signals=[_code("confirmed", "confirmed")],
    )

    assert len(candidates) == 1
    assert candidates[0].anchor_event_id == "confirmed"
