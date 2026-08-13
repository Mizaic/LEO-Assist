"""VT-EC74EAD9: default SBAR invoker uses JSONInvocationOptions.

The default Situation, Background, and Recommendation path must
not pass max_tokens as a raw keyword to invoke_llm_json.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

from libs.llm_client.json_helper import JSONInvocationOptions
from libs.sbar.prompt_calls import (
    call_background,
    call_recommendation,
    call_situation,
)
from libs.sbar.source_resolver import ResolvedSituation, ResolvedSource


def _prompt(_name: str) -> str:
    return "SYSTEM"


def _assert_json_options(captured: dict[str, Any], max_tokens: int) -> None:
    assert "max_tokens" not in captured
    options = captured["options"]
    assert isinstance(options, JSONInvocationOptions)
    assert options.max_tokens == max_tokens
    assert options.temperature == 0.0


def test_call_situation_default_invoker_uses_json_options() -> None:
    captured: dict[str, Any] = {}

    async def _fake_invoke(system: str, user: str, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"situation_markdown": "ok"}

    resolved = ResolvedSituation(patient_id="pat-1")
    with patch(
        "libs.sbar.prompt_calls.invoke_llm_json",
        new=AsyncMock(side_effect=_fake_invoke),
    ):
        result = asyncio.run(call_situation(resolved, prompt_fetcher=_prompt))

    assert result["error"] is None
    _assert_json_options(captured, 512)


def test_call_background_default_invoker_uses_json_options() -> None:
    captured: dict[str, Any] = {}

    async def _fake_invoke(system: str, user: str, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"background_markdown": "ok"}

    sources = [
        ResolvedSource(
            source_label="Encounter",
            source_id="enc-1",
            text="short note",
            codes=[],
            metadata={},
        )
    ]
    with patch(
        "libs.sbar.prompt_calls.invoke_llm_json",
        new=AsyncMock(side_effect=_fake_invoke),
    ):
        result = asyncio.run(call_background(sources, [], prompt_fetcher=_prompt))

    assert result["error"] is None
    _assert_json_options(captured, 1024)


def test_call_recommendation_default_invoker_uses_json_options() -> None:
    captured: dict[str, Any] = {}

    async def _fake_invoke(system: str, user: str, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"recommendation_markdown": "- review", "actions": []}

    with patch(
        "libs.sbar.prompt_calls.invoke_llm_json",
        new=AsyncMock(side_effect=_fake_invoke),
    ):
        result = asyncio.run(
            call_recommendation(
                situation_md="s",
                background_md="b",
                assessment_md="a",
                assessment_rules=[],
                guideline_titles=[],
                guidelines=[],
                prompt_fetcher=_prompt,
            )
        )

    assert result["error"] is None
    _assert_json_options(captured, 1024)
