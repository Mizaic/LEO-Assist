"""Per-tier Azure reasoning flags from environment.

Small defaults to low reasoning. Big and max default to off.
An explicit create_llm(use_reasoning=...) argument still wins.
"""

from __future__ import annotations

import pytest

from libs.llm_client.factory import (
    create_llm,
    reset_llm_cache,
    resolve_azure_use_reasoning,
)


@pytest.fixture(autouse=True)
def _clear_llm_cache() -> None:
    reset_llm_cache()
    yield
    reset_llm_cache()


def test_small_defaults_to_reasoning_on() -> None:
    assert resolve_azure_use_reasoning("small", None) is True


def test_big_and_max_default_to_reasoning_off() -> None:
    assert resolve_azure_use_reasoning("big", None) is False
    assert resolve_azure_use_reasoning("max", None) is False


def test_explicit_argument_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_USE_REASONING_SMALL", "true")
    monkeypatch.setenv("AZURE_USE_REASONING_BIG", "false")
    assert resolve_azure_use_reasoning("small", False) is False
    assert resolve_azure_use_reasoning("big", True) is True


def test_env_can_disable_small(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_USE_REASONING_SMALL", "false")
    assert resolve_azure_use_reasoning("small", None) is False


def test_env_can_enable_big(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_USE_REASONING_BIG", "true")
    assert resolve_azure_use_reasoning("big", None) is True


def test_create_llm_small_uses_low_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_SMALL_MODEL", "gpt-5.4-nano")
    monkeypatch.delenv("AZURE_USE_REASONING_SMALL", raising=False)
    client = create_llm(provider="azure", tier="small")
    assert client.use_reasoning is True
    assert client.azure_reasoning_effort == "low"


def test_create_llm_big_leaves_reasoning_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_BIG_MODEL", "gpt-5.4")
    monkeypatch.delenv("AZURE_USE_REASONING_BIG", raising=False)
    client = create_llm(provider="azure", tier="big")
    assert client.use_reasoning is False
