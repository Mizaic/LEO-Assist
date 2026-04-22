"""Tests for the feature-flag plumbing.

Atlas trace:
  DI: DI-8A5FCF4F (Defence-in-depth episode detector with coverage fail-safe)
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-8A5FCF4F")
"""

from __future__ import annotations

import pytest

from libs import feature_flags


@pytest.fixture(autouse=True)
def _clear_overrides_and_env(monkeypatch):
    feature_flags.clear_process_override("episode_pipeline")
    monkeypatch.delenv("EPISODE_PIPELINE", raising=False)
    yield
    feature_flags.clear_process_override("episode_pipeline")


def test_default_is_v1():
    assert feature_flags.resolve("episode_pipeline") == "v1"


def test_global_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv("EPISODE_PIPELINE", "v2")
    assert feature_flags.resolve("episode_pipeline") == "v2"


def test_unknown_value_falls_back_to_default(monkeypatch, caplog):
    monkeypatch.setenv("EPISODE_PIPELINE", "v999")
    with caplog.at_level("WARNING"):
        assert feature_flags.resolve("episode_pipeline") == "v1"
    assert any("v999" in m for m in caplog.messages)


def test_per_tenant_env_var_beats_global(monkeypatch):
    monkeypatch.setenv("EPISODE_PIPELINE", "v1")
    monkeypatch.setenv("EPISODE_PIPELINE__TENANT_ABC", "v2")
    assert feature_flags.resolve("episode_pipeline", tenant_id="tenant-abc") == "v2"
    assert feature_flags.resolve("episode_pipeline", tenant_id="other") == "v1"


def test_process_override_beats_env(monkeypatch):
    monkeypatch.setenv("EPISODE_PIPELINE", "v2")
    feature_flags.set_process_override("episode_pipeline", "shadow")
    assert feature_flags.resolve("episode_pipeline") == "shadow"


def test_unknown_flag_raises():
    with pytest.raises(KeyError):
        feature_flags.resolve("does_not_exist")


def test_set_invalid_override_raises():
    with pytest.raises(ValueError):
        feature_flags.set_process_override("episode_pipeline", "nope")


def test_episode_pipeline_allowed_values():
    flag = feature_flags.registered_flags()["episode_pipeline"]
    assert flag.default == "v1"
    assert set(flag.allowed) == {"v1", "v2", "shadow"}
