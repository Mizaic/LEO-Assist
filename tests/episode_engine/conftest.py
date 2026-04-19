"""Shared helpers for episode-engine unit VTs.

The episode engine talks to Bedrock through ``LLMClient.converse``. All unit
tests in this package mock that client so the tests are deterministic, fast,
and cost nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeLLMResponse:
    """Mimics ``libs.llm_client.factory.LLMResponse``."""

    text: str = ""
    input_tokens: int = 1234
    output_tokens: int = 567
    cached_input_tokens: int = 0
    stop_reason: str = "tool_use"
    model_id: str = "fake-model"
    tool_uses: list[dict[str, Any]] = field(default_factory=list)


def tool_use(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Build a Bedrock-style toolUse dict."""
    return {
        "name": tool_name,
        "toolUseId": "tu-test",
        "input": payload,
    }


def tool_use_str(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Same as ``tool_use`` but with the input serialised as a JSON string -
    real Bedrock occasionally returns this shape."""
    return {
        "name": tool_name,
        "toolUseId": "tu-test",
        "input": json.dumps(payload),
    }


class FakeLLM:
    """Drop-in for ``LLMClient`` used by the episode-engine agents.

    Pass a single ``FakeLLMResponse`` for the simple single-call tests, or
    a list of responses for tests that drive a stage which makes more than
    one Bedrock call (for example the Audit Relevance Filter batches).
    Each call consumes the next response in order; once exhausted the last
    response is replayed indefinitely so tests stay forgiving when an extra
    call slips in.
    """

    def __init__(
        self,
        response: FakeLLMResponse | list[FakeLLMResponse],
        *,
        model_id: str = "fake-model",
    ):
        self.model_id = model_id
        self.tier = "small"
        self.provider = "aws"
        if isinstance(response, list):
            assert response, "FakeLLM needs at least one response"
            self._responses: list[FakeLLMResponse] = list(response)
        else:
            self._responses = [response]
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> FakeLLMResponse:
        self.calls.append(kwargs)
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


class RaisingLLM:
    """LLMClient stand-in that raises on every call."""

    def __init__(self, exc: Exception, *, model_id: str = "fake-model"):
        self.model_id = model_id
        self.tier = "small"
        self.provider = "aws"
        self._exc = exc

    def converse(self, **_: Any) -> FakeLLMResponse:  # pragma: no cover - trivial
        raise self._exc
