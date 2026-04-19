"""VT-LEO-AI-514 TC-005: friendly translator covers known Bedrock failure modes.

See DI-LEO-AI-513 / DI-LEO-AI-516. The translator MUST never echo
raw vendor strings for known modes, MUST cover the four known modes
(input_too_long, throttled, access_denied, network), and MUST fall
back to a generic plain-English message for anything else.
"""

from __future__ import annotations

import pytest

from libs.sbar.error_messages import (
    KNOWN_ERROR_CODES,
    translate_error,
)

_BEDROCK_INPUT_TOO_LONG = (
    "An error occurred (ValidationException) when calling the Converse "
    "operation: The model returned the following errors: Input is too "
    "long for requested model."
)


@pytest.mark.parametrize(
    "raw, expected_code",
    [
        (_BEDROCK_INPUT_TOO_LONG, "input_too_long"),
        ("Context length 200000 tokens exceeded.", "input_too_long"),
        (
            "An error occurred (ThrottlingException): Too many requests",
            "throttled",
        ),
        ("HTTP 429 rate limit exceeded", "throttled"),
        (
            "An error occurred (AccessDeniedException) when calling Converse",
            "access_denied",
        ),
        ("ExpiredTokenException: token expired", "access_denied"),
        (
            "EndpointConnectionError: Could not connect to the endpoint URL",
            "network",
        ),
        ("Connection timed out after 30s", "network"),
        ("missing_background_markdown", "missing_section"),
        ("totally unexpected vendor message", "unknown"),
        ("", "unknown"),
    ],
)
def test_translate_error_classifies_known_modes(raw: str, expected_code: str) -> None:
    result = translate_error("background", raw)
    assert result["stage"] == "background"
    assert result["code"] == expected_code
    assert expected_code in KNOWN_ERROR_CODES


def test_translate_error_message_is_plain_english_and_safe() -> None:
    result = translate_error("background", _BEDROCK_INPUT_TOO_LONG)
    msg = result["message"]
    assert "ValidationException" not in msg
    assert "Converse" not in msg
    assert "Bedrock" not in msg
    assert msg.endswith(".")
    assert "Background" in msg


def test_translate_error_stage_noun_for_each_stage() -> None:
    for stage in ("situation", "background", "assessment", "recommendation"):
        msg = translate_error(stage, _BEDROCK_INPUT_TOO_LONG)["message"]
        assert stage.capitalize() in msg


def test_translate_error_unknown_falls_back_to_generic_message() -> None:
    result = translate_error("background", "something weird happened")
    assert result["code"] == "unknown"
    assert "something weird happened" not in result["message"]
    assert "Background" in result["message"]
