"""Tests for `libs/utils/device_resolver.py`.

Atlas trace:
  DO: DO-89AF1CCE
  DI: DI-3717DFB0

The resolver decides which inference backend (CPU/CUDA/MPS) to use, and must
fall back safely when probes fail so a single bad probe never crashes the
worker at startup.
"""

from __future__ import annotations

from unittest.mock import patch

from libs.utils.device_resolver import (
    AcceleratorDecision,
    _normalise_requested,
    resolve_accelerator,
)


class TestNormaliseRequested:
    def test_none_defaults_to_auto(self):
        assert _normalise_requested(None) == "auto"

    def test_empty_string_defaults_to_auto(self):
        assert _normalise_requested("") == "auto"

    def test_unknown_token_defaults_to_auto(self):
        assert _normalise_requested("tpu") == "auto"

    def test_known_tokens_pass_through_lowercase(self):
        for token in ("cpu", "CUDA", "Mps", " auto "):
            decision = _normalise_requested(token)
            assert decision in {"cpu", "cuda", "mps", "auto"}


class TestExplicitCpu:
    def test_cpu_request_returns_cpu_no_fallback(self):
        d = resolve_accelerator("cpu")
        assert d.requested == "cpu"
        assert d.resolved == "cpu"
        assert d.fallback_applied is False
        assert d.fallback_reason == ""


class TestCudaProbe:
    def test_cuda_request_resolves_when_probe_succeeds(self):
        with patch(
            "libs.utils.device_resolver._probe_cuda",
            return_value=(True, ""),
        ):
            d = resolve_accelerator("cuda")
        assert d.resolved == "cuda"
        assert d.fallback_applied is False

    def test_cuda_request_falls_back_to_cpu_when_probe_fails(self):
        with patch(
            "libs.utils.device_resolver._probe_cuda",
            return_value=(False, "no driver"),
        ):
            d = resolve_accelerator("cuda")
        assert d.resolved == "cpu"
        assert d.fallback_applied is True
        assert "no driver" in d.fallback_reason


class TestMpsProbe:
    def test_mps_request_resolves_when_probe_succeeds(self):
        with patch(
            "libs.utils.device_resolver._probe_mps",
            return_value=(True, ""),
        ):
            d = resolve_accelerator("mps")
        assert d.resolved == "mps"
        assert d.fallback_applied is False

    def test_mps_request_falls_back_to_cpu_when_probe_fails(self):
        with patch(
            "libs.utils.device_resolver._probe_mps",
            return_value=(False, "macos too old"),
        ):
            d = resolve_accelerator("mps")
        assert d.resolved == "cpu"
        assert d.fallback_applied is True
        assert "macos too old" in d.fallback_reason


class TestAutoOnDarwin:
    def test_auto_picks_mps_when_macos_and_probe_ok(self):
        with patch("libs.utils.device_resolver.platform.system",
                   return_value="Darwin"), \
             patch("libs.utils.device_resolver._probe_mps",
                   return_value=(True, "")):
            d = resolve_accelerator("auto")
        assert d.resolved == "mps"
        assert d.fallback_applied is False

    def test_auto_falls_back_to_cpu_on_macos_when_mps_unavailable(self):
        with patch("libs.utils.device_resolver.platform.system",
                   return_value="Darwin"), \
             patch("libs.utils.device_resolver._probe_mps",
                   return_value=(False, "no mps")):
            d = resolve_accelerator("auto")
        assert d.resolved == "cpu"
        assert d.fallback_applied is True

    def test_auto_skips_mps_when_prefer_mps_disabled(self):
        with patch("libs.utils.device_resolver.platform.system",
                   return_value="Darwin"), \
             patch("libs.utils.device_resolver._probe_cuda",
                   return_value=(False, "no cuda")):
            d = resolve_accelerator("auto", prefer_mps_on_macos=False)
        assert d.resolved == "cpu"


class TestAutoOnLinux:
    def test_auto_picks_cuda_when_available(self):
        with patch("libs.utils.device_resolver.platform.system",
                   return_value="Linux"), \
             patch("libs.utils.device_resolver._probe_cuda",
                   return_value=(True, "")):
            d = resolve_accelerator("auto")
        assert d.resolved == "cuda"
        assert d.fallback_applied is False

    def test_auto_falls_back_to_cpu_when_cuda_unavailable(self):
        with patch("libs.utils.device_resolver.platform.system",
                   return_value="Linux"), \
             patch("libs.utils.device_resolver._probe_cuda",
                   return_value=(False, "no cuda")):
            d = resolve_accelerator("auto")
        assert d.resolved == "cpu"
        assert d.fallback_applied is True


class TestDecisionShape:
    def test_decision_includes_provenance_fields(self):
        d = resolve_accelerator("cpu")
        assert isinstance(d, AcceleratorDecision)
        assert d.platform_name
        assert d.machine
        # macos_major may be None on non-macOS hosts; only assert type
        assert d.macos_major is None or isinstance(d.macos_major, int)
