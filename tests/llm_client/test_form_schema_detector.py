"""Tests for libs.llm_client.form_schema_detector.

Covers:
  - _parse_response: good JSON, fenced JSON, object-root, invalid, empty
  - _validate_section / _validate_item: missing fields get safe defaults
  - detect_form_sections: single create_llm converse call on the big tier

Atlas trace: VT-D2EC1B30, DI-5C9CA57B, DO-D0C19842
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from libs.llm_client.form_schema_detector import (
    _parse_response,
    _validate_item,
    _validate_section,
    detect_form_sections,
)
from libs.llm_client.prompt_safety import INJECTION_GUARD

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


def test_parse_response_object_root():
    raw = json.dumps({"sections": [_VALID_SECTION]})
    result = _parse_response(raw)
    assert result is not None
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


def test_parse_response_empty_object_root_returns_none():
    result = _parse_response('{"sections": []}')
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
    raw = {
        "pattern": "Ovary",
        "entity_text": "Ovarian cancer suspected",
        "semantic_tag": "finding",
        "assertion": "present",
    }
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
# detect_form_sections (mocked create_llm converse -- not run_consensus)
# ---------------------------------------------------------------------------

GYNAE_SAMPLE = """
Section A: Gynaecological Cancer type suspected
Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]

Section B: Referral criteria
B1. Lesion suspicious of cancer of cervix or vagina Yes [X] No [ ]

Clinical Frailty Scale
1. Very Fit [ ] 2. Well [ ] 3. Managing Well [ ]
"""


def _llm_response(text: str) -> MagicMock:
    mock = MagicMock()
    mock.text = text
    return mock


def _patch_llm(response_text: str = "", *, side_effect=None):
    client = MagicMock()
    if side_effect is not None:
        client.converse.side_effect = side_effect
    else:
        client.converse.return_value = _llm_response(response_text)
    return (
        patch(
            "libs.llm_client.form_schema_detector.create_llm",
            return_value=client,
        ),
        client,
    )


def test_detect_returns_sections_from_llm():
    sections = [
        {
            "section_id": "A",
            "label": "Section A: Gynaecological Cancer type suspected",
            "section_type": "checkbox_single",
            "start_pattern": "(?i)section\\s+a",
            "items": [
                {
                    "pattern": "Ovary",
                    "entity_text": "Ovarian cancer suspected",
                    "semantic_tag": "finding",
                    "assertion": "present",
                },
                {
                    "pattern": "Cervix",
                    "entity_text": "Cervical cancer suspected",
                    "semantic_tag": "finding",
                    "assertion": "present",
                },
            ],
        }
    ]
    patcher, _client = _patch_llm(json.dumps({"sections": sections}))
    with patcher:
        result = detect_form_sections(GYNAE_SAMPLE)

    assert len(result) == 1
    assert result[0]["section_id"] == "A"
    items = result[0]["items"]
    assert len(items) == 2
    assert items[1]["entity_text"] == "Cervical cancer suspected"


def test_detect_uses_big_tier_and_single_converse():
    patcher, client = _patch_llm(json.dumps({"sections": [_VALID_SECTION]}))
    with patch(
        "libs.llm_client.form_schema_detector.create_llm",
        return_value=client,
    ) as create:
        detect_form_sections(GYNAE_SAMPLE)

    create.assert_called_once_with(tier="big")
    assert client.converse.call_count == 1
    kwargs = client.converse.call_args.kwargs
    assert kwargs["agent_task"] == "form_schema_detect"
    assert kwargs["json_mode"] is True
    assert kwargs["structured_schema"]["required"] == ["sections"]


def test_detect_empty_parse_falls_back_to_splitter():
    patcher, client = _patch_llm("not json at all")
    with patcher:
        result = detect_form_sections(GYNAE_SAMPLE)

    assert any(s["section_id"] == "A" for s in result)
    assert client.converse.call_count == 1


def test_detect_does_not_import_run_consensus():
    import libs.llm_client.form_schema_detector as detector

    assert not hasattr(detector, "run_consensus")


def test_detect_sanitises_form_text_and_truncates():
    long_text = "A" * 10000
    captured: list[str] = []

    def fake_create(*, tier):
        assert tier == "big"
        client = MagicMock()

        def converse(**kwargs):
            captured.append(kwargs["messages"][0]["content"])
            return _llm_response(json.dumps({"sections": []}))

        client.converse.side_effect = converse
        return client

    with patch(
        "libs.llm_client.form_schema_detector.create_llm",
        side_effect=fake_create,
    ):
        detect_form_sections(long_text)

    assert captured
    assert len(captured[0]) <= 6000


def test_detect_system_prompt_uses_shared_injection_guard():
    patcher, client = _patch_llm(json.dumps({"sections": [_VALID_SECTION]}))
    with patcher:
        detect_form_sections(GYNAE_SAMPLE)

    system = client.converse.call_args.kwargs["system"]
    assert system.startswith(INJECTION_GUARD)


def test_detect_returns_empty_on_llm_exception_when_no_headers():
    patcher, _client = _patch_llm(side_effect=RuntimeError("provider down"))
    with patcher:
        result = detect_form_sections("Narrative letter with no tick boxes.")

    assert result == []


def test_detect_uses_splitter_on_llm_exception_when_headers_exist():
    patcher, _client = _patch_llm(side_effect=RuntimeError("provider down"))
    with patcher:
        result = detect_form_sections(GYNAE_SAMPLE)

    assert any(s["section_id"] == "A" for s in result)
