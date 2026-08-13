"""Original letter text from extract stage input."""

from __future__ import annotations

from libs.validation_lab.source_text import (
    letter_from_extract_input,
    source_text_from_stage_rows,
)


def test_letter_from_extract_input_uses_encounter_text() -> None:
    text = letter_from_extract_input(
        {"encounter_text": "Dear colleague,\n\nPlease see this patient."}
    )
    assert "Please see this patient" in text


def test_source_text_prefers_extract_stage() -> None:
    rows = [
        {
            "step_id": "persist",
            "input_json": {"encounter_text": "not the letter"},
        },
        {
            "step_id": "act-ref-extract",
            "input_json": {"encounter_text": "Dear GP, chest pain for two weeks."},
        },
    ]
    assert source_text_from_stage_rows(rows) == "Dear GP, chest pain for two weeks."


def test_source_text_joins_sentences_when_no_encounter_text() -> None:
    rows = [
        {
            "step_id": "extract",
            "input_json": {
                "sentences": [{"text": "Line one."}, {"text": "Line two."}]
            },
        }
    ]
    assert source_text_from_stage_rows(rows) == "Line one.\n\nLine two."
