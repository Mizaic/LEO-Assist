"""Tests for AWS_LLM_ENABLED provider gate."""

from __future__ import annotations

import pytest

from libs.llm_client.factory import (
    aws_llm_enabled,
    create_llm,
    default_llm_provider,
    effective_llm_provider,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", False),
        ("false", False),
        ("0", False),
        ("true", True),
        ("yes", True),
        ("on", True),
    ],
)
def test_aws_llm_enabled_parses_env(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    monkeypatch.setenv("AWS_LLM_ENABLED", raw)
    assert aws_llm_enabled() is expected


def test_default_llm_provider_forces_azure_when_aws_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_LLM_ENABLED", "false")
    monkeypatch.setenv("PIPELINE_MODEL_PROVIDER", "aws")
    assert default_llm_provider() == "azure"


def test_default_llm_provider_allows_aws_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_LLM_ENABLED", "true")
    monkeypatch.setenv("PIPELINE_MODEL_PROVIDER", "aws")
    assert default_llm_provider() == "aws"


def test_create_llm_redirects_aws_to_azure_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_LLM_ENABLED", "false")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_SMALL_MODEL", "gpt-test")

    client = create_llm(provider="aws", tier="small")
    assert client.provider == "azure"


def test_effective_llm_provider_normalizes_unknown() -> None:
    assert effective_llm_provider("unknown-vendor") == "azure"
