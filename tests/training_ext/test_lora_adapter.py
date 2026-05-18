"""Wave 4 tests for the LoRA adapter helpers."""

from __future__ import annotations

import os

import pytest

from libs.training_ext.lora_adapter import (
    LoRAConfig,
    _DEFAULT_TARGET_MODULES,
    target_modules_for_family,
    training_mode,
)


class TestLoRAConfigFromEnv:
    def test_defaults(self, monkeypatch):
        for key in (
            "LORA_RANK",
            "LORA_ALPHA",
            "LORA_DROPOUT",
            "LORA_TARGET_MODULES",
            "LORA_BIAS",
        ):
            monkeypatch.delenv(key, raising=False)
        cfg = LoRAConfig.from_env()
        assert cfg.rank == 8
        assert cfg.alpha == 16
        assert cfg.dropout == 0.1
        assert cfg.target_modules == _DEFAULT_TARGET_MODULES
        assert cfg.bias == "none"

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("LORA_RANK", "16")
        monkeypatch.setenv("LORA_ALPHA", "32")
        monkeypatch.setenv("LORA_DROPOUT", "0.2")
        monkeypatch.setenv("LORA_TARGET_MODULES", "q_proj, v_proj")
        monkeypatch.setenv("LORA_BIAS", "all")
        cfg = LoRAConfig.from_env()
        assert cfg.rank == 16
        assert cfg.alpha == 32
        assert cfg.dropout == pytest.approx(0.2)
        assert cfg.target_modules == ("q_proj", "v_proj")
        assert cfg.bias == "all"

    def test_bad_env_falls_back_to_defaults(self, monkeypatch):
        monkeypatch.setenv("LORA_RANK", "not-an-int")
        monkeypatch.setenv("LORA_DROPOUT", "garbage")
        cfg = LoRAConfig.from_env()
        assert cfg.rank == 8
        assert cfg.dropout == pytest.approx(0.1)


class TestTrainingMode:
    @pytest.mark.parametrize("value,expected", [
        ("full", "full"),
        ("frozen", "frozen"),
        ("lora", "lora"),
        ("LoRa", "lora"),
        ("", "frozen"),
    ])
    def test_valid_modes(self, monkeypatch, value, expected):
        if value:
            monkeypatch.setenv("TRAINING_MODE", value)
        else:
            monkeypatch.delenv("TRAINING_MODE", raising=False)
        assert training_mode() == expected

    def test_unknown_mode_falls_back(self, monkeypatch):
        monkeypatch.setenv("TRAINING_MODE", "bananas")
        assert training_mode() == "frozen"


def test_target_modules_for_family_matrix():
    assert target_modules_for_family("Bio_ClinicalBERT") == _DEFAULT_TARGET_MODULES
    assert target_modules_for_family("roberta-base") == _DEFAULT_TARGET_MODULES
    assert target_modules_for_family("gpt2") == ("q_proj", "v_proj")
