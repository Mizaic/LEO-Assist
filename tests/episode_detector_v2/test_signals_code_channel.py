"""Tests for episode_detector_v2.signals.code_channel.

Atlas trace:
  DI: DI-8A5FCF4F
"""

from __future__ import annotations

from datetime import date

from services.analysis_worker.app.episode_detector_v2.signals.code_channel import (
    extract_code_signals,
)
from services.analysis_worker.app.episode_detector_v2.types import TimelineEvent


def _evt(encounter_id="enc-1", codes=()):
    return TimelineEvent(
        encounter_id=encounter_id,
        occurred_on=date(2024, 3, 15),
        event_kind="encounter",
        coded_entities=tuple(codes),
    )


def test_breast_confirmed_concept_emits_confirmed_signal():
    evt = _evt(codes=[{"concept_id": "254837009", "display_name": "Malignant"}])
    signals = extract_code_signals([evt])
    assert len(signals) == 1
    assert signals[0].channel == "code"
    assert signals[0].site_key == "breast"
    assert signals[0].intent == "confirmed"
    assert signals[0].confidence >= 0.9


def test_breast_suspected_concept_emits_suspected_signal():
    evt = _evt(codes=[{"concept_id": "134405005"}])
    signals = extract_code_signals([evt])
    assert signals[0].intent == "suspected"


def test_unknown_concept_emits_no_signal():
    evt = _evt(codes=[{"concept_id": "999999999"}])
    signals = extract_code_signals([evt])
    assert signals == []


def test_negated_assertion_overrides_intent_to_ruled_out():
    evt = _evt(
        codes=[{"concept_id": "254837009", "assertion": "negated"}]
    )
    signals = extract_code_signals([evt])
    assert signals[0].intent == "ruled_out"
    assert signals[0].confidence >= 0.85


def test_emits_lung_confirmed_signal_for_registered_lung_snomed():
    """Stub-site fail-safe: lung is not auto-eligible but the code
    channel still emits a signal so the coverage check sees the
    encounter and flags it for human review.
    """
    evt = _evt(codes=[{"concept_id": "363358000", "display_name": "Malignant lung"}])
    signals = extract_code_signals([evt])
    assert len(signals) == 1
    assert signals[0].site_key == "lung"
    assert signals[0].intent == "confirmed"


def test_emits_upper_gi_suspected_signal_for_registered_ugi_snomed():
    evt = _evt(codes=[{"concept_id": "162574000", "display_name": "Suspected UGI ca"}])
    signals = extract_code_signals([evt])
    assert len(signals) == 1
    assert signals[0].site_key == "upper_gi"
    assert signals[0].intent == "suspected"


def test_truly_unknown_cancer_concept_still_emits_no_signal():
    evt = _evt(codes=[{"concept_id": "111111111"}])
    assert extract_code_signals([evt]) == []
