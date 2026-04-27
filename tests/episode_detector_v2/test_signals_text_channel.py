"""Tests for episode_detector_v2.signals.text_channel."""

from __future__ import annotations

from datetime import date

from libs.episode_detector.loader import (
    DEFAULTS_DIR,
    load_default_bundle,
    load_rulebook,
    override_sites,
    set_current_bundle,
)
from services.analysis_worker.app.episode_detector_v2.signals.text_channel import (
    extract_text_signals,
)
from services.analysis_worker.app.episode_detector_v2.types import TimelineEvent


def _event(encounter_id: str, text: str) -> TimelineEvent:
    return TimelineEvent(
        encounter_id=encounter_id,
        occurred_on=date(2025, 4, 1),
        event_kind="encounter",
        text_snippet=text,
    )


def test_prostate_surface_symptoms_emit_text_signal():
    prostate_v1 = load_rulebook(DEFAULTS_DIR / "prostate_urological.v1.json")
    set_current_bundle(
        override_sites(
            load_default_bundle(),
            {prostate_v1.site_key: prostate_v1},
        )
    )
    event = _event(
        "symptoms",
        "Getting up 2-3 x each night to pass urine. Poor flow. "
        "Feels that he incompletely empties his bladder.",
    )

    signals = extract_text_signals([event])

    assert any(
        signal.site_key == "prostate_urological"
        and signal.role == "diagnosis"
        and signal.intent == "suspected"
        for signal in signals
    )
