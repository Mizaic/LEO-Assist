"""Stage 13 - feature-flag routing for the NCDA detector."""

from __future__ import annotations

import pytest

from libs import feature_flags


@pytest.fixture(autouse=True)
def _clear_state(monkeypatch):
    feature_flags.clear_process_override("ncda_detector")
    monkeypatch.delenv("NCDA_DETECTOR", raising=False)
    yield
    feature_flags.clear_process_override("ncda_detector")


def test_ncda_flag_is_registered():
    flag = feature_flags.registered_flags()["ncda_detector"]
    assert flag.default == "off"
    assert set(flag.allowed) == {"off", "shadow", "on"}


def test_default_off():
    assert feature_flags.resolve("ncda_detector") == "off"


def test_is_cancer_suspect_returns_true_when_high_ftr_score():
    rows = [{"role": "none", "role_p": 0.4}, {"role": "ftr", "role_p": 0.65}]
    assert feature_flags.is_cancer_suspect(rows) is True


def test_is_cancer_suspect_returns_true_when_high_dx_score():
    rows = [{"role": "dx", "role_p": 0.92, "dx_outcome": "cancer_excluded"}]
    assert feature_flags.is_cancer_suspect(rows) is True


def test_is_cancer_suspect_false_when_below_threshold():
    rows = [{"role": "ftr", "role_p": 0.49}, {"role": "dx", "role_p": 0.4}]
    assert feature_flags.is_cancer_suspect(rows) is False


def test_is_cancer_suspect_ignores_treatment_only_signal():
    rows = [{"role": "treatment", "role_p": 0.99}]
    assert feature_flags.is_cancer_suspect(rows) is False


def test_routing_off_skips_run():
    rows = [{"role": "ftr", "role_p": 0.95}]
    should_run, mode = feature_flags.ncda_detector_should_run(rows)
    assert mode == "off"
    assert should_run is False


def test_routing_shadow_runs_for_everyone(monkeypatch):
    monkeypatch.setenv("NCDA_DETECTOR", "shadow")
    rows = [{"role": "none", "role_p": 0.99}]
    should_run, mode = feature_flags.ncda_detector_should_run(rows)
    assert mode == "shadow"
    assert should_run is True


def test_routing_on_only_runs_for_cancer_suspects(monkeypatch):
    monkeypatch.setenv("NCDA_DETECTOR", "on")
    suspect_rows = [{"role": "dx", "role_p": 0.7}]
    bystander_rows = [{"role": "none", "role_p": 0.95}]
    assert feature_flags.ncda_detector_should_run(suspect_rows) == (True, "on")
    assert feature_flags.ncda_detector_should_run(bystander_rows) == (False, "on")


def test_routing_per_tenant_override(monkeypatch):
    monkeypatch.setenv("NCDA_DETECTOR", "off")
    monkeypatch.setenv("NCDA_DETECTOR__TENANT_PILOT", "on")
    rows = [{"role": "ftr", "role_p": 0.8}]
    assert feature_flags.ncda_detector_should_run(rows)[1] == "off"
    assert (
        feature_flags.ncda_detector_should_run(rows, tenant_id="tenant-pilot")
        == (True, "on")
    )
