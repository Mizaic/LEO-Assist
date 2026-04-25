"""Tests for episode_detector_v2.signals.result_channel."""

from __future__ import annotations

from datetime import date

from services.analysis_worker.app.episode_detector_v2.signals.result_channel import (
    extract_result_signals,
)
from services.analysis_worker.app.episode_detector_v2.types import TimelineEvent


def _event(encounter_id: str, text: str) -> TimelineEvent:
    return TimelineEvent(
        encounter_id=encounter_id,
        occurred_on=date(2025, 6, 11),
        event_kind="encounter",
        text_snippet=text,
    )


def test_cyst_of_breast_with_investigation_emits_ruled_out_result_signal():
    event = _event(
        "cyst",
        "Minor: Cyst of breast. Aspiration of breast. "
        "Mammogram - M2. US scan of breast - U2.",
    )

    signals = extract_result_signals([event])

    assert len(signals) == 1
    assert signals[0].site_key == "breast"
    assert signals[0].intent == "ruled_out"
    assert signals[0].channel == "result"


def test_cyst_without_breast_investigation_does_not_close_pathway():
    event = _event("cyst", "History of breast cyst checked previously.")

    assert extract_result_signals([event]) == []
