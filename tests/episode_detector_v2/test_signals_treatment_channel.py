from __future__ import annotations

from datetime import date

from services.analysis_worker.app.episode_detector_v2.signals.treatment_channel import (
    extract_treatment_signals,
)
from services.analysis_worker.app.episode_detector_v2.types import TimelineEvent


def _event(text: str) -> TimelineEvent:
    return TimelineEvent(
        encounter_id="enc-1",
        occurred_on=date(2025, 5, 19),
        event_kind="encounter",
        text_snippet=text,
    )


def test_letrozole_commenced_by_breast_surgeon_confirms_breast_treatment():
    event = _event(
        "Drug Review. Reconcilliation source: Breast clinic letter 28/04/25. "
        "Comments: pt commenced on letrozole 2.5mg od by breast surgeon."
    )

    signals = extract_treatment_signals([event])

    assert len(signals) == 1
    assert signals[0].site_key == "breast"
    assert signals[0].role == "treatment"
    assert signals[0].intent == "confirmed"


def test_letrozole_without_breast_treatment_context_does_not_confirm():
    event = _event("Medication query: patient asks about letrozole.")

    assert extract_treatment_signals([event]) == []

