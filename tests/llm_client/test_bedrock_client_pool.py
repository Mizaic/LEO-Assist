"""Tests for process-wide Bedrock boto3 client pooling."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_boto3_module() -> MagicMock:
    class _FakeConfig:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    mock_botocore = MagicMock()
    mock_botocore.config.Config = _FakeConfig

    mock_boto3 = MagicMock()
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client

    previous_boto3 = sys.modules.get("boto3")
    previous_botocore = sys.modules.get("botocore")
    previous_botocore_config = sys.modules.get("botocore.config")
    sys.modules["boto3"] = mock_boto3
    sys.modules["botocore"] = mock_botocore
    sys.modules["botocore.config"] = mock_botocore.config
    try:
        yield mock_boto3
    finally:
        for name, previous in (
            ("boto3", previous_boto3),
            ("botocore", previous_botocore),
            ("botocore.config", previous_botocore_config),
        ):
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


class TestBedrockMaxPoolConnections:
    def test_explicit_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from libs.llm_client.bedrock_client import bedrock_max_pool_connections

        monkeypatch.setenv("BEDROCK_MAX_POOL_CONNECTIONS", "48")
        monkeypatch.delenv("SB_MAX_CONCURRENT_CALLS", raising=False)
        assert bedrock_max_pool_connections() == 48

    def test_scales_with_sb_concurrency_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from libs.llm_client.bedrock_client import bedrock_max_pool_connections

        monkeypatch.delenv("BEDROCK_MAX_POOL_CONNECTIONS", raising=False)
        monkeypatch.setenv("SB_MAX_CONCURRENT_CALLS", "8")
        assert bedrock_max_pool_connections() == 32

    def test_scales_with_sb_concurrency_high(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from libs.llm_client.bedrock_client import bedrock_max_pool_connections

        monkeypatch.delenv("BEDROCK_MAX_POOL_CONNECTIONS", raising=False)
        monkeypatch.setenv("SB_MAX_CONCURRENT_CALLS", "16")
        assert bedrock_max_pool_connections() == 64


class TestBedrockRuntimeClientCache:
    def setup_method(self) -> None:
        from libs.llm_client.bedrock_client import reset_bedrock_client_cache

        reset_bedrock_client_cache()

    def teardown_method(self) -> None:
        from libs.llm_client.bedrock_client import reset_bedrock_client_cache

        reset_bedrock_client_cache()

    def test_reuses_client_for_same_config(self, mock_boto3_module: MagicMock) -> None:
        from libs.llm_client.bedrock_client import get_bedrock_runtime_client

        first = get_bedrock_runtime_client("eu-west-2", 30, 90, 1, True)
        second = get_bedrock_runtime_client("eu-west-2", 30, 90, 1, True)
        assert first is second
        assert mock_boto3_module.client.call_count == 1

    def test_different_config_gets_distinct_client(
        self, mock_boto3_module: MagicMock
    ) -> None:
        from libs.llm_client.bedrock_client import get_bedrock_runtime_client

        sync_client = MagicMock(name="sync")
        async_client = MagicMock(name="async")
        mock_boto3_module.client.side_effect = [sync_client, async_client]

        first = get_bedrock_runtime_client("eu-west-2", 30, 90, 1, True)
        second = get_bedrock_runtime_client("eu-west-2", 60, 300, 3, False)
        assert first is sync_client
        assert second is async_client
        assert mock_boto3_module.client.call_count == 2

    def test_boto3_config_sets_max_pool_connections(
        self, monkeypatch: pytest.MonkeyPatch, mock_boto3_module: MagicMock
    ) -> None:
        from libs.llm_client.bedrock_client import get_bedrock_runtime_client

        monkeypatch.setenv("BEDROCK_MAX_POOL_CONNECTIONS", "55")
        client = get_bedrock_runtime_client("eu-west-2", 30, 90, 1, True)

        assert client is mock_boto3_module.client.return_value
        _service, kwargs = mock_boto3_module.client.call_args
        assert kwargs["region_name"] == "eu-west-2"
        assert kwargs["config"].max_pool_connections == 55


class TestCreateLlmBedrockReuse:
    def setup_method(self) -> None:
        from libs.llm_client.factory import reset_llm_cache

        reset_llm_cache()

    def teardown_method(self) -> None:
        from libs.llm_client.factory import reset_llm_cache

        reset_llm_cache()

    def test_create_llm_reuses_underlying_bedrock_client(
        self, monkeypatch: pytest.MonkeyPatch, mock_boto3_module: MagicMock
    ) -> None:
        from libs.llm_client.factory import create_llm, reset_llm_cache

        # Without this the factory honours the local AWS_LLM_ENABLED=false,
        # quietly hands back an Azure client, and the test fails on the
        # Azure endpoint it just deleted rather than on client reuse.
        monkeypatch.setenv("AWS_LLM_ENABLED", "true")
        monkeypatch.setenv("AWS_SMALL_MODEL", "anthropic.claude-haiku-test")
        monkeypatch.setenv(
            "AWS_BEDROCK_MODEL",
            "arn:aws:bedrock:eu-west-2::anthropic.claude-haiku-test",
        )
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        reset_llm_cache()

        first = create_llm(provider="aws", tier="small")
        second = create_llm(provider="aws", tier="small")
        first_client = first._get_client()
        second_client = second._get_client()

        assert first is second
        assert first_client is second_client
        assert mock_boto3_module.client.call_count == 1
