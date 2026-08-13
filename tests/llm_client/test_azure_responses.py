"""Focused tests for the Azure Responses transport.

Atlas trace:
  DI: DI-7B978C0C
  DO: DO-FA8FCECF
  VT: VT-06157CF6
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from libs.llm_client import factory
from libs.llm_client.azure_responses import (
    AzureResponsesCall,
    AzureResponsesCapabilities,
    azure_transport_name,
    build_azure_responses_request,
    create_azure_responses_client,
)


class _FakeResponses:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class _FakeCompletions:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


class _FakeSdkClient:
    def __init__(
        self,
        *,
        responses: _FakeResponses,
        chat_response: Any | None = None,
    ) -> None:
        self.responses = responses
        self.chat_completions = _FakeCompletions(chat_response)
        self.chat = SimpleNamespace(completions=self.chat_completions)


def _responses_sdk_result() -> tuple[Any, Any]:
    function_call = SimpleNamespace(
        type="function_call",
        call_id="call-123",
        name="lookup_term",
        arguments='{"term": "dysphagia"}',
    )
    result = SimpleNamespace(
        id="resp-123",
        status="completed",
        output_text='{"ok": true}',
        output=[function_call],
        incomplete_details=None,
        usage=SimpleNamespace(
            input_tokens=120,
            output_tokens=45,
            input_tokens_details=SimpleNamespace(cached_tokens=30),
            output_tokens_details=SimpleNamespace(reasoning_tokens=12),
        ),
    )
    return result, function_call


def _chat_sdk_result() -> Any:
    usage = SimpleNamespace(
        prompt_tokens=20,
        completion_tokens=5,
        prompt_tokens_details=SimpleNamespace(cached_tokens=2),
        completion_tokens_details=None,
    )
    choice = SimpleNamespace(
        message=SimpleNamespace(content='{"legacy": true}'),
        finish_reason="stop",
    )
    return SimpleNamespace(choices=[choice], usage=usage)


def _responses_client(fake_sdk: _FakeSdkClient) -> factory.LLMClient:
    client = factory.LLMClient(
        provider="azure",
        model_id="gpt-5-mini",
        tier="small",
        use_reasoning=True,
    )
    client._client = fake_sdk
    client._azure_transport = "responses"
    return client


def _strict_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }


def _tool_config() -> tuple[dict[str, Any], dict[str, Any]]:
    schema = {
        "type": "object",
        "properties": {"term": {"type": "string"}},
        "required": ["term"],
    }
    config = {
        "tools": [
            {
                "toolSpec": {
                    "name": "lookup_term",
                    "description": "Look up a clinical term.",
                    "inputSchema": {"json": schema},
                }
            }
        ],
        "toolChoice": {"tool": {"name": "lookup_term"}},
    }
    return config, schema


def _assert_responses_request(
    request: dict[str, Any],
    prior_item: dict[str, Any],
    schema: dict[str, Any],
    tool_schema: dict[str, Any],
) -> None:
    assert request["model"] == "gpt-5-mini"
    assert request["store"] is False
    assert request["max_output_tokens"] == 8000
    assert request["input"][0] == {
        "role": "developer",
        "content": "Return JSON.",
    }
    assert request["input"][1] == {
        "role": "user",
        "content": "Check dysphagia.",
    }
    assert request["input"][2] is prior_item
    assert request["text"] == {
        "format": {
            "type": "json_schema",
            "name": "response",
            "schema": schema,
            "strict": True,
        },
        "verbosity": "low",
    }
    assert request["reasoning"] == {"effort": "low"}
    assert request["tools"] == [
        {
            "type": "function",
            "name": "lookup_term",
            "description": "Look up a clinical term.",
            "parameters": tool_schema,
            "strict": False,
        }
    ]
    assert request["tool_choice"] == {
        "type": "function",
        "name": "lookup_term",
    }


def _assert_responses_result(response: Any, function_call: Any) -> None:
    assert response.text == '{"ok": true}'
    assert response.response_id == "resp-123"
    assert response.raw_output_items == [function_call]
    assert response.tool_uses == [
        {
            "toolUseId": "call-123",
            "name": "lookup_term",
            "input": {"term": "dysphagia"},
        }
    ]
    assert response.input_tokens == 120
    assert response.output_tokens == 45
    assert response.cached_input_tokens == 30
    assert response.reasoning_tokens == 12
    assert response.stop_reason == "completed"


def test_v1_client_uses_undated_azure_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    sentinel = object()

    def _fake_openai(**kwargs: Any) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.delenv("AZURE_OPENAI_TRANSPORT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_READ_TIMEOUT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_RESPONSES_READ_TIMEOUT", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://unit.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "unit-key")
    monkeypatch.setattr(openai, "OpenAI", _fake_openai)

    result = create_azure_responses_client()

    assert result is sentinel
    assert azure_transport_name() == "responses"
    assert captured["base_url"] == "https://unit.openai.azure.com/openai/v1/"
    assert captured["api_key"] == "unit-key"
    assert captured["max_retries"] == 0
    assert isinstance(captured["timeout"], httpx.Timeout)
    assert captured["timeout"].connect == 10.0
    assert captured["timeout"].read == 120.0
    assert "api_version" not in captured


def test_responses_request_and_usage_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_result, function_call = _responses_sdk_result()
    fake_responses = _FakeResponses(response=sdk_result)
    fake_sdk = _FakeSdkClient(responses=fake_responses)
    client = _responses_client(fake_sdk)
    prior_item = {"type": "function_call_output", "call_id": "old", "output": "ok"}
    schema = _strict_schema()
    tool_config, tool_schema = _tool_config()
    telemetry: list[dict[str, Any]] = []

    def _capture_telemetry(**kwargs: Any) -> None:
        telemetry.append(kwargs)

    monkeypatch.setattr(factory, "_fire_converse_tracking", _capture_telemetry)

    response = client.converse(
        system="Return JSON.",
        messages=[{"role": "user", "content": "Check dysphagia."}],
        max_tokens=321,
        tool_config=tool_config,
        structured_schema=schema,
        response_items=[prior_item],
        verbosity="low",
        agent_task="azure_responses_test",
        patient_id="patient-1",
    )

    _assert_responses_request(fake_responses.calls[0], prior_item, schema, tool_schema)
    _assert_responses_result(response, function_call)
    assert telemetry[0]["input_tokens"] == 120
    assert telemetry[0]["output_tokens"] == 45
    assert telemetry[0]["cache_read_input_tokens"] == 30
    assert telemetry[0]["reasoning_tokens"] == 12


def test_chat_completions_flag_uses_rollback_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_responses = _FakeResponses(response=None)
    fake_sdk = _FakeSdkClient(
        responses=fake_responses,
        chat_response=_chat_sdk_result(),
    )
    client = factory.LLMClient(provider="azure", model_id="gpt-5-mini")
    client._client = fake_sdk
    monkeypatch.setenv("AZURE_OPENAI_TRANSPORT", "chat_completions")

    response = client.converse(
        system="Return JSON.",
        messages=[{"role": "user", "content": "Use rollback."}],
        max_tokens=64,
        json_mode=True,
    )

    assert fake_responses.calls == []
    assert len(fake_sdk.chat_completions.calls) == 1
    request = fake_sdk.chat_completions.calls[0]
    assert request["response_format"] == {"type": "json_object"}
    assert response.text == '{"legacy": true}'
    assert response.cached_input_tokens == 2


def test_chat_rollback_rejects_tool_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_sdk = _FakeSdkClient(
        responses=_FakeResponses(response=None),
        chat_response=_chat_sdk_result(),
    )
    client = factory.LLMClient(provider="azure", model_id="gpt-5-mini")
    client._client = fake_sdk
    monkeypatch.setenv("AZURE_OPENAI_TRANSPORT", "chat_completions")

    with pytest.raises(RuntimeError, match="does not support"):
        client.converse(
            system="Use a tool.",
            messages=[{"role": "user", "content": "Check."}],
            tool_config=_tool_config()[0],
        )

    assert fake_sdk.chat_completions.calls == []


def test_failed_responses_tool_call_does_not_fall_back_to_chat() -> None:
    fake_responses = _FakeResponses(error=RuntimeError("responses unavailable"))
    fake_sdk = _FakeSdkClient(
        responses=fake_responses,
        chat_response=_chat_sdk_result(),
    )
    client = _responses_client(fake_sdk)

    with pytest.raises(RuntimeError, match="responses unavailable"):
        client.converse(
            system="Use the tool.",
            messages=[{"role": "user", "content": "Look up dysphagia."}],
            tool_config={
                "tools": [
                    {
                        "toolSpec": {
                            "name": "lookup_term",
                            "inputSchema": {"json": {"type": "object"}},
                        }
                    }
                ]
            },
        )

    assert len(fake_responses.calls) == 1
    assert fake_sdk.chat_completions.calls == []


def test_unsupported_capability_fails_instead_of_downgrading() -> None:
    call = AzureResponsesCall(
        model_id="limited-deployment",
        system="Return JSON.",
        messages=[{"role": "user", "content": "Check."}],
        max_output_tokens=32,
        structured_schema=_strict_schema(),
        capabilities=AzureResponsesCapabilities(strict_schema=False),
    )

    with pytest.raises(ValueError, match="strict_schema"):
        build_azure_responses_request(call)


def test_strict_schema_rejects_non_object_root() -> None:
    call = AzureResponsesCall(
        model_id="gpt-5-mini",
        system="Return JSON.",
        messages=[{"role": "user", "content": "Check."}],
        max_output_tokens=32,
        structured_schema={"type": "array", "items": {"type": "string"}},
    )

    with pytest.raises(ValueError, match="object root"):
        build_azure_responses_request(call)


def test_parse_reads_message_text_when_output_text_missing() -> None:
    from libs.llm_client.azure_responses import parse_azure_responses_response

    message = SimpleNamespace(
        type="message",
        content=[SimpleNamespace(type="output_text", text='{"terms": []}')],
    )
    response = SimpleNamespace(
        id="resp-empty-direct",
        status="completed",
        output_text="",
        output=[message],
        incomplete_details=None,
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=4,
            input_tokens_details=SimpleNamespace(cached_tokens=0),
            output_tokens_details=SimpleNamespace(reasoning_tokens=0),
        ),
    )

    parsed = parse_azure_responses_response(response, "gpt-5-mini")

    assert parsed.text == '{"terms": []}'


def test_send_retries_timeout_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    from libs.llm_client.azure_responses import (
        AzureResponsesCall,
        send_azure_responses,
    )

    monkeypatch.setattr("libs.llm_client.azure_retry.time.sleep", lambda _delay: None)
    sdk_result, _function_call = _responses_sdk_result()
    fake = _FakeResponses(error=_timeout_error())
    fake.response = sdk_result

    def _create(**kwargs: Any) -> Any:
        fake.calls.append(kwargs)
        if len(fake.calls) == 1:
            raise fake.error
        return fake.response

    fake.create = _create  # type: ignore[method-assign]
    client = _FakeSdkClient(responses=fake)
    call = AzureResponsesCall(
        model_id="gpt-5-mini",
        system="Return JSON.",
        messages=[{"role": "user", "content": "Check."}],
        max_output_tokens=32,
        json_mode=True,
    )
    parsed = send_azure_responses(client, call)
    assert parsed.text == '{"ok": true}'
    assert len(fake.calls) == 2


def _timeout_error() -> openai.APITimeoutError:
    request = httpx.Request(
        "POST", "https://example.openai.azure.com/openai/v1/responses"
    )
    return openai.APITimeoutError(request=request)


def test_reasoning_expands_max_output_tokens() -> None:
    from libs.llm_client.azure_responses import reasoning_max_output_tokens

    assert reasoning_max_output_tokens(4096, tier="small", use_reasoning=False) == 8192
    assert reasoning_max_output_tokens(8192, tier="small", use_reasoning=False) == 16384
    assert reasoning_max_output_tokens(4096, tier="small", use_reasoning=True) == 8192
    assert reasoning_max_output_tokens(4096, tier="big", use_reasoning=True) == 16384
    assert reasoning_max_output_tokens(8192, tier="big", use_reasoning=True) == 32768
    assert reasoning_max_output_tokens(321, tier="small", use_reasoning=True) == 8000
