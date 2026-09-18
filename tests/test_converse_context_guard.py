"""The context check fires on the real call path, before anything is sent.

A guard nobody calls is not a guard. Every provider call in the platform
funnels through ``LLMClient.converse``, so that is where the model's
window is checked. These tests assert the check runs there and that the
provider is never reached when it trips.

Rule: .cursor/rules/fail-closed-boundary.mdc rule 1 -- a failure that
could change a clinical output must stop the run, not be logged past.
"""

from __future__ import annotations

from typing import Any

import pytest

from libs.llm_client.context_budget import (
    ContextBudgetExceeded,
    ModelWindowUnknown,
)
from libs.llm_client.factory import LLMClient


class _ProviderWasCalled(AssertionError):
    """Raised by the stub so a leak through the guard is unmistakable."""


def _client(model_id: str = "gpt-5-mini") -> LLMClient:
    client = LLMClient(provider="azure", model_id=model_id, tier="small")

    def _explode() -> Any:
        raise _ProviderWasCalled(f"reached the provider for {model_id}")

    client._get_client = _explode  # type: ignore[method-assign]
    return client


def _messages(chars: int) -> list[dict[str, Any]]:
    return [{"role": "user", "content": [{"text": "x" * chars}]}]


def test_an_oversized_prompt_never_reaches_the_provider() -> None:
    """Roughly 1.2M characters is about 300,000 tokens, over gpt-5-mini's
    244,800 working budget."""
    with pytest.raises(ContextBudgetExceeded):
        _client().converse(system="", messages=_messages(1_200_000))


def test_an_undeclared_model_never_reaches_the_provider() -> None:
    with pytest.raises(ModelWindowUnknown):
        _client("gpt-6-turbo-experimental").converse(system="", messages=_messages(100))


def test_an_oversized_answer_request_never_reaches_the_provider() -> None:
    with pytest.raises(ContextBudgetExceeded):
        _client().converse(system="", messages=_messages(100), max_tokens=120_000)


def test_the_system_prompt_counts_towards_the_input() -> None:
    """Few-shot libraries live in the system prompt, so leaving it out of
    the count is how a call gets over the limit while looking fine."""
    with pytest.raises(ContextBudgetExceeded):
        _client().converse(system="y" * 1_200_000, messages=_messages(100))


def test_an_ordinary_call_is_let_through_to_the_provider() -> None:
    """The guard must not become a blanket refusal. Reaching the stub is
    the pass condition here."""
    with pytest.raises(_ProviderWasCalled):
        _client().converse(system="You are a coder.", messages=_messages(2_000))
