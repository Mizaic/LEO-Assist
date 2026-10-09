"""Whole-letter form detection with a visible fallback.

The detector must read the whole letter, ask for an answer every model on
the fleet can give, and say so whenever a simpler reader stood in for the
model.

Atlas trace: VT-25098971, DI-C1744ED5, DO-1C8E7598, R-98702FED
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from libs.llm_client import form_schema_detector as fsd
from libs.llm_client.azure_responses import reasoning_max_output_tokens
from libs.llm_client.context_budget import PUBLISHED_WINDOWS
from libs.llm_client.form_schema_detector import detect_form_schema

_FIXTURE = Path(__file__).parent / "fixtures" / "form_schema"
_LETTER = (_FIXTURE / "sfh_lower_gi_2ww_full_deid.md").read_text(encoding="utf-8")

_CLINICAL = {
    "section_id": "2",
    "label": "SECTION 2: Symptoms suggesting colorectal cancer",
    "section_type": "checkbox_multi",
    "start_pattern": "SECTION 2: Symptoms suggesting colorectal cancer",
    "items": [],
    "default_semantic_tags": ["finding"],
}


def _client(text: str = "", *, side_effect=None) -> MagicMock:
    client = MagicMock()
    if side_effect is not None:
        client.converse.side_effect = side_effect
    else:
        response = MagicMock()
        response.text = text
        client.converse.return_value = response
    return client


def _detect(client: MagicMock, text: str = _LETTER):
    with patch(
        "libs.llm_client.form_schema_detector.create_llm", return_value=client
    ) as create:
        return detect_form_schema(text), create


def test_letter_longer_than_6000_chars_reaches_the_model_whole() -> None:
    assert len(_LETTER) > 6000
    client = _client(json.dumps({"sections": [_CLINICAL]}))
    detection, _create = _detect(client)

    sent = client.converse.call_args.kwargs["messages"][0]["content"]
    assert sent == _LETTER
    assert "Full description" in sent
    assert "Hospital Use Only" in sent
    assert detection.letter_cut is False


def test_letter_over_the_fleet_budget_is_flagged(monkeypatch) -> None:
    monkeypatch.setattr(fsd, "_MAX_FORM_CHARS", 1000)
    client = _client(json.dumps({"sections": [_CLINICAL]}))
    detection, _create = _detect(client)

    assert detection.letter_cut is True
    assert "too long" in detection.message


def _smallest_output_budget() -> int:
    return min(w.usable_output_tokens for w in PUBLISHED_WINDOWS.values())


def test_output_limit_fits_smallest_model_after_azure_expansion() -> None:
    expanded = reasoning_max_output_tokens(
        fsd._MAX_TOKENS, tier="big", use_reasoning=False
    )
    assert fsd._MAX_TOKENS >= 6000
    assert fsd._MAX_TOKENS <= _smallest_output_budget()
    assert expanded <= _smallest_output_budget()


def test_answer_cap_allows_four_chars_per_expanded_token() -> None:
    expanded = reasoning_max_output_tokens(
        fsd._MAX_TOKENS, tier="big", use_reasoning=False
    )
    assert fsd._MAX_RESPONSE_CHARS >= 4 * expanded


def test_detector_pins_reasoning_off_so_expansion_stays_doubled() -> None:
    client = _client(json.dumps({"sections": [_CLINICAL]}))
    _detection, create = _detect(client)

    create.assert_called_once_with(tier="big", use_reasoning=False)


def test_model_answer_is_used_without_a_notice() -> None:
    client = _client(json.dumps({"sections": [_CLINICAL]}))
    detection, _create = _detect(client)

    assert detection.used_fallback is False
    assert detection.reason == "model"
    assert detection.message == ""
    assert detection.sections[0]["section_id"] == "2"


@pytest.mark.parametrize(
    ("client", "reason"),
    [
        (_client(side_effect=RuntimeError("provider down")), "model_failed"),
        (_client("not json at all"), "model_unreadable"),
        (
            _client(
                json.dumps(
                    {"sections": [dict(_CLINICAL, section_type="admin", items=[])]}
                )
            ),
            "model_no_clinical",
        ),
    ],
    ids=["call-failed", "unreadable", "admin-only"],
)
def test_fallback_is_reported_with_a_plain_message(client, reason) -> None:
    detection, _create = _detect(client)

    assert detection.used_fallback is True
    assert detection.reason == reason
    assert "check every section" in detection.message.lower()
    assert detection.sections, "the splitter must still offer sections"


def test_detect_form_sections_still_returns_the_list() -> None:
    client = _client(json.dumps({"sections": [_CLINICAL]}))
    with patch("libs.llm_client.form_schema_detector.create_llm", return_value=client):
        sections = fsd.detect_form_sections(_LETTER)

    assert isinstance(sections, list)
    assert sections[0]["section_id"] == "2"
