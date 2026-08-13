"""Retry Azure Responses timeouts instead of dropping the letter.

Atlas trace:
  DI: DI-7B978C0C
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-7B978C0C")
"""

from __future__ import annotations

import httpx
import openai
import pytest

from libs.llm_client.azure_retry import call_azure_with_retry


def _timeout() -> openai.APITimeoutError:
    request = httpx.Request(
        "POST", "https://example.openai.azure.com/openai/v1/responses"
    )
    return openai.APITimeoutError(request=request)


def test_timeout_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("libs.llm_client.azure_retry.time.sleep", sleeps.append)
    attempts = {"n": 0}

    def _flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise _timeout()
        return "ok"

    assert call_azure_with_retry(_flaky, model_id="gpt-5-mini") == "ok"
    assert attempts["n"] == 2
    assert sleeps and sleeps[0] >= 1.0


def test_timeout_raises_after_final_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("libs.llm_client.azure_retry.time.sleep", lambda _delay: None)
    attempts = {"n": 0}

    def _always_timeout() -> str:
        attempts["n"] += 1
        raise _timeout()

    with pytest.raises(openai.APITimeoutError):
        call_azure_with_retry(_always_timeout, model_id="gpt-5-mini")
    assert attempts["n"] == 3


def test_http_500_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("libs.llm_client.azure_retry.time.sleep", lambda _delay: None)
    request = httpx.Request(
        "POST", "https://example.openai.azure.com/openai/v1/responses"
    )
    response = httpx.Response(500, request=request)
    attempts = {"n": 0}

    def _flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise openai.APIStatusError(
                message="server error",
                response=response,
                body=None,
            )
        return "ok"

    assert call_azure_with_retry(_flaky, model_id="gpt-5-mini") == "ok"
    assert attempts["n"] == 2
