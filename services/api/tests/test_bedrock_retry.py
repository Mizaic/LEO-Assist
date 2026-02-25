"""Tests for Bedrock retry with exponential backoff."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.v3.bedrock_retry import (
    _get_error_code,
    _is_retryable,
    converse_with_retry,
)


def _make_client_error(code: str):
    """Create a botocore ClientError with the given code."""
    from botocore.exceptions import ClientError

    return ClientError(
        {"Error": {"Code": code, "Message": "test"}},
        "Converse",
    )


def test_get_error_code_empty_for_non_client_error() -> None:
    assert _get_error_code(ValueError("x")) == ""


def test_get_error_code_extracts_from_client_error() -> None:
    err = _make_client_error("ThrottlingException")
    assert _get_error_code(err) == "ThrottlingException"


def test_is_retryable_throttle_codes() -> None:
    for code in (
        "ThrottlingException",
        "TooManyRequestsException",
        "RequestLimitExceeded",
        "ServiceUnavailableException",
        "InternalServerException",
        "ModelTimeoutException",
    ):
        assert _is_retryable(_make_client_error(code)) is True


def test_is_retryable_non_retryable() -> None:
    assert _is_retryable(_make_client_error("ValidationException")) is False
    assert _is_retryable(_make_client_error("AccessDeniedException")) is False
    assert _is_retryable(ValueError("x")) is False


def test_converse_with_retry_success_first_try() -> None:
    client = MagicMock()
    client.converse.return_value = {"output": {"message": {"content": [{"text": "ok"}]}}}
    result = converse_with_retry(
        client,
        model_id="test-model",
        messages=[{"role": "user", "content": [{"text": "hi"}]}],
        inferenceConfig={"maxTokens": 10},
    )
    assert result["output"]["message"]["content"][0]["text"] == "ok"
    assert client.converse.call_count == 1


def test_converse_with_retry_retries_on_throttle_then_succeeds() -> None:
    from botocore.exceptions import ClientError

    client = MagicMock()
    throttle = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "Converse",
    )
    success = {"output": {"message": {"content": [{"text": "ok"}]}}}
    client.converse.side_effect = [throttle, throttle, success]

    result = converse_with_retry(
        client,
        model_id="test-model",
        messages=[{"role": "user", "content": [{"text": "hi"}]}],
        inferenceConfig={"maxTokens": 10},
        max_retries=5,
        base_delay=0.01,
        max_delay=0.05,
        jitter=0,
    )
    assert result["output"]["message"]["content"][0]["text"] == "ok"
    assert client.converse.call_count == 3


def test_converse_with_retry_raises_after_exhausting_retries() -> None:
    from botocore.exceptions import ClientError

    client = MagicMock()
    throttle = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "Converse",
    )
    client.converse.side_effect = throttle

    with pytest.raises(ClientError):
        converse_with_retry(
            client,
            model_id="test-model",
            messages=[{"role": "user", "content": [{"text": "hi"}]}],
            inferenceConfig={"maxTokens": 10},
            max_retries=3,
            base_delay=0.01,
            max_delay=0.02,
            jitter=0,
        )
    assert client.converse.call_count == 3


def test_converse_with_retry_does_not_retry_validation_error() -> None:
    from botocore.exceptions import ClientError

    client = MagicMock()
    validation = ClientError(
        {"Error": {"Code": "ValidationException", "Message": "Invalid"}},
        "Converse",
    )
    client.converse.side_effect = validation

    with pytest.raises(ClientError):
        converse_with_retry(
            client,
            model_id="test-model",
            messages=[{"role": "user", "content": [{"text": "hi"}]}],
            inferenceConfig={"maxTokens": 10},
            max_retries=5,
        )
    assert client.converse.call_count == 1
