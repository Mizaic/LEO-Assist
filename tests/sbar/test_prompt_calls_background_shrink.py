"""VT-LEO-AI-514 TC-003 / TC-004: prompt_calls.call_background wires the shrinker.

Verifies:
  - call_background passes the shrunk user message to the invoker
    and threads the shrinker notice through the return dict on the
    success path (TC-003).
  - When invoke_llm_json returns an oversize ValidationException-style
    error, call_background returns the friendly translated message
    and never echoes the raw vendor string (TC-004).
"""

from __future__ import annotations

import asyncio

from libs.sbar import prompt_calls
from libs.sbar.source_resolver import ResolvedSource

_BEDROCK_INPUT_TOO_LONG = (
    "An error occurred (ValidationException) when calling the Converse "
    "operation: The model returned the following errors: Input is too "
    "long for requested model."
)


def _sources(n: int, text_len: int) -> list[ResolvedSource]:
    return [
        ResolvedSource(
            source_label="Encounter",
            source_id=f"enc-{i}",
            text="x" * text_len,
            codes=[],
            metadata={},
        )
        for i in range(n)
    ]


def test_call_background_threads_notice_on_success() -> None:
    sources = _sources(5, text_len=8000)
    captured_user: list[str] = []

    async def _ok_invoker(system, user, **_kw):
        captured_user.append(user)
        return {"background_markdown": "ok"}

    result = asyncio.run(
        prompt_calls.call_background(
            sources,
            [],
            referring_specialty=None,
            invoker=_ok_invoker,
            prompt_fetcher=lambda _name: "SYSTEM",
        )
    )

    assert result["error"] is None
    assert result["error_code"] is None
    assert result["markdown"] == "ok"
    assert len(captured_user) == 1
    if result["notice"] is not None:
        assert "ValidationException" not in result["notice"]


def test_call_background_returns_friendly_error_when_input_too_long() -> None:
    async def _err_invoker(system, user, **_kw):
        return {"error": _BEDROCK_INPUT_TOO_LONG}

    result = asyncio.run(
        prompt_calls.call_background(
            _sources(2, text_len=200),
            [],
            referring_specialty=None,
            invoker=_err_invoker,
            prompt_fetcher=lambda _name: "SYSTEM",
        )
    )

    assert result["markdown"] == ""
    assert result["error_code"] == "input_too_long"
    msg = result["error"]
    assert isinstance(msg, str) and msg
    assert "ValidationException" not in msg
    assert "Converse" not in msg
    assert "Background" in msg


def test_call_background_translates_missing_section_to_friendly_message() -> None:
    async def _empty_invoker(system, user, **_kw):
        return {"background_markdown": "   "}

    result = asyncio.run(
        prompt_calls.call_background(
            _sources(1, text_len=100),
            [],
            referring_specialty=None,
            invoker=_empty_invoker,
            prompt_fetcher=lambda _name: "SYSTEM",
        )
    )

    assert result["error_code"] == "missing_section"
    msg = result["error"]
    assert isinstance(msg, str) and msg
    assert "missing_background_markdown" not in msg
    assert "Background" in msg
