"""Unit tests for libs/episode_learning/scorer_retrain.py."""

from __future__ import annotations

from datetime import datetime, timezone

from libs.episode_learning.correction_capture import CorrectionEvent
from libs.episode_learning.scorer_retrain import (
    DEFAULT_WEIGHTS,
    ScorerWeights,
    retrain_site_scorer,
)


def _event(**overrides):
    base = dict(
        audit_id="a-1",
        event_type="EpisodeManualAttach",
        correction_target="detector_boundary",
        site_key="breast",
        episode_id="ep-1",
        patient_id="p-1",
        actor_role="qa-ra-lead",
        label=1,
        captured_at=datetime(2026, 4, 22, tzinfo=timezone.utc),
        context={},
    )
    base.update(overrides)
    return CorrectionEvent(**base)


def test_default_weights_returned_when_no_events_for_site():
    out = retrain_site_scorer([], site_key="breast")
    assert isinstance(out, ScorerWeights)
    assert out.site_key == "breast"
    assert out.weights == DEFAULT_WEIGHTS
    assert out.sample_count == 0
    assert "no events" in out.notes


def test_events_for_other_sites_are_filtered_out():
    events = [_event(site_key="lung", correction_target="detector_boundary")]
    out = retrain_site_scorer(events, site_key="breast")
    assert out.sample_count == 0


def test_weights_change_when_correction_events_exist():
    events = [
        _event(audit_id=f"a-{i}", correction_target="detector_boundary")
        for i in range(5)
    ]
    out = retrain_site_scorer(events, site_key="breast", learning_rate=0.5)
    assert out.sample_count == 5
    assert out.weights != DEFAULT_WEIGHTS
    for channel in DEFAULT_WEIGHTS:
        assert isinstance(out.weights[channel], float)


def test_weight_keys_are_stable():
    events = [_event()]
    out = retrain_site_scorer(events, site_key="breast")
    assert set(out.weights.keys()) == set(DEFAULT_WEIGHTS.keys())


def test_clamped_step_keeps_weights_within_half_unit():
    events = [_event(audit_id=f"a-{i}") for i in range(20)]
    out = retrain_site_scorer(events, site_key="breast", learning_rate=10.0)
    for channel, value in out.weights.items():
        assert abs(value - DEFAULT_WEIGHTS[channel]) <= 0.5 + 1e-6


def test_other_target_does_not_explode_with_zero_features():
    events = [_event(correction_target="other")]
    out = retrain_site_scorer(events, site_key="breast")
    assert out.sample_count == 1


def test_base_weights_overrides_default():
    base = dict(DEFAULT_WEIGHTS)
    base["code"] = 0.0
    out = retrain_site_scorer(
        [_event()], site_key="breast", base_weights=base, learning_rate=0.1
    )
    assert out.weights["code"] != DEFAULT_WEIGHTS["code"]
