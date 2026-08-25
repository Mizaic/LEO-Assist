"""Tests for libs.llm_client.form_schema_detector.

Covers:
  - _parse_response: good JSON, fenced JSON, invalid, nested list, empty
  - _validate_section / _validate_item: missing fields get safe defaults
  - detect_form_sections: mocked run_consensus call

Atlas trace: VT-D2EC1B30
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from libs.llm_client.form_schema_detector import (
    _parse_response,
    _validate_item,
    _validate_section,
    detect_form_sections,
)


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

_VALID_SECTION = {
    "section_id": "A",
    "label": "Section A: Cancer type",
    "section_type": "checkbox_single",
    "start_pattern": "(?i)section\\s+a:",
    "items": [
        {
            "pattern": "Cervix",
            "entity_text": "Cervical cancer suspected",
            "semantic_tag": "finding",
            "assertion": "present",
        }
    ],
}


def test_parse_response_plain_json():
    raw = json.dumps([_VALID_SECTION])
    result = _parse_response(raw)
    assert result is not None
    assert len(result) == 1
    assert result[0]["section_id"] == "A"


def test_parse_response_markdown_fenced():
    raw = f"```json\n{json.dumps([_VALID_SECTION])}\n```"
    result = _parse_response(raw)
    assert result is not None
    assert result[0]["section_type"] == "checkbox_single"


def test_parse_response_array_embedded_in_text():
    raw = f"Here are the sections:\n{json.dumps([_VALID_SECTION])}\nDone."
    result = _parse_response(raw)
    assert result is not None
    assert result[0]["label"] == "Section A: Cancer type"


def test_parse_response_invalid_json_returns_none():
    result = _parse_response("not json at all")
    assert result is None


def test_parse_response_non_list_returns_none():
    result = _parse_response('{"key": "value"}')
    assert result is None


def test_parse_response_empty_array_returns_none():
    result = _parse_response("[]")
    assert result is None


# ---------------------------------------------------------------------------
# _validate_section / _validate_item
# ---------------------------------------------------------------------------


def test_validate_section_all_fields():
    out = _validate_section(_VALID_SECTION)
    assert out["section_id"] == "A"
    assert out["section_type"] == "checkbox_single"
    assert len(out["items"]) == 1


def test_validate_section_missing_fields_get_defaults():
    out = _validate_section({})
    assert out["section_id"] == "?"
    assert out["section_type"] == "free_text"
    assert out["items"] == []


def test_validate_item_all_fields():
    raw = {"pattern": "Ovary", "entity_text": "Ovarian cancer suspected",
           "semantic_tag": "finding", "assertion": "present"}
    out = _validate_item(raw)
    assert out["pattern"] == "Ovary"
    assert out["entity_text"] == "Ovarian cancer suspected"


def test_validate_item_missing_fields_get_defaults():
    out = _validate_item({})
    assert out["semantic_tag"] == "finding"
    assert out["assertion"] == "present"
    assert out["pattern"] == ""
    assert out["entity_text"] == ""


# ---------------------------------------------------------------------------
# detect_form_sections (mocked run_consensus)
# ---------------------------------------------------------------------------

GYNAE_SAMPLE = """
Section A: Gynaecological Cancer type suspected
Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]

Section B: Referral criteria
B1. Lesion suspicious of cancer of cervix or vagina Yes [X] No [ ]

Clinical Frailty Scale
1. Very Fit [ ] 2. Well [ ] 3. Managing Well [ ]
"""


def _mock_result(sections: list) -> MagicMock:
    mock = MagicMock()
    mock.verdict = sections
    return mock


def test_detect_returns_sections_from_llm():
    sections = [
        {
            "section_id": "A",
            "label": "Section A: Gynaecological Cancer type suspected",
            "section_type": "checkbox_single",
            "start_pattern": "(?i)section\\s+a",
            "items": [
                {"pattern": "Ovary", "entity_text": "Ovarian cancer suspected",
                 "semantic_tag": "finding", "assertion": "present"},
                {"pattern": "Cervix", "entity_text": "Cervical cancer suspected",
                 "semantic_tag": "finding", "assertion": "present"},
            ],
        }
    ]
    with patch(
        "libs.llm_client.form_schema_detector.run_consensus",
        return_value=_mock_result(sections),
    ):
        result = detect_form_sections(GYNAE_SAMPLE)

    assert len(result) == 1
    assert result[0]["section_id"] == "A"
    items = result[0]["items"]
    assert len(items) == 2
    assert items[1]["entity_text"] == "Cervical cancer suspected"


def test_detect_returns_empty_on_consensus_fail():
    mock = MagicMock()
    mock.verdict = []
    with patch(
        "libs.llm_client.form_schema_detector.run_consensus",
        return_value=mock,
    ):
        result = detect_form_sections(GYNAE_SAMPLE)

    assert result == []


def test_detect_truncates_long_text():
    long_text = "A" * 10000
    captured: list[str] = []

    def fake_consensus(*, system_prompt, user_msg, parse_fn, fail_verdict, options):
        captured.append(user_msg)
        mock = MagicMock()
        mock.verdict = []
        return mock

    with patch(
        "libs.llm_client.form_schema_detector.run_consensus",
        side_effect=fake_consensus,
    ):
        detect_form_sections(long_text)

    assert len(captured[0]) <= 6000
