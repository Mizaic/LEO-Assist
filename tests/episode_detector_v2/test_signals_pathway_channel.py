"""Tests for episode_detector_v2.signals.pathway_channel.

Atlas trace:
  DI: DI-8A5FCF4F
"""

from __future__ import annotations

from datetime import date

from services.analysis_worker.app.episode_detector_v2.signals.pathway_channel import (
    extract_pathway_signals,
)
from services.analysis_worker.app.episode_detector_v2.types import TimelineEvent


def _evt(referral_form):
    return TimelineEvent(
        encounter_id="enc-1",
        occurred_on=date(2024, 3, 15),
        event_kind="encounter",
        referral_form=referral_form,
    )


def test_2ww_breast_form_yields_breast_suspected_signal():
    evt = _evt(
        {
            "form_type": "2ww_breast",
            "urgency": "2ww",
            "source": "GP",
            "reason": "Breast lump",
        }
    )
    signals = extract_pathway_signals([evt])
    assert len(signals) == 1
    assert signals[0].site_key == "breast"
    assert signals[0].intent == "suspected"
    assert signals[0].confidence > 0.8


def test_unknown_form_with_lung_reason_falls_back_to_lung():
    evt = _evt(
        {
            "form_type": "general_referral",
            "urgency": "urgent",
            "reason": "Persistent haemoptysis - suspected lung cancer",
        }
    )
    signals = extract_pathway_signals([evt])
    assert signals[0].site_key == "lung"
    assert signals[0].intent == "suspected"


def test_routine_referral_yields_unspecified_intent():
    evt = _evt(
        {
            "form_type": "2ww_breast",
            "urgency": "routine",
        }
    )
    signals = extract_pathway_signals([evt])
    assert signals[0].intent == "unspecified"


def test_no_referral_form_yields_no_signals():
    evt = _evt(None)
    assert extract_pathway_signals([evt]) == []


def test_unknown_site_form_yields_no_signals():
    evt = _evt({"form_type": "podiatry_referral", "urgency": "routine"})
    assert extract_pathway_signals([evt]) == []
