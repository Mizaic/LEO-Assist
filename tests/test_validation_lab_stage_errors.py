"""Plain-English Validation Lab stage error helpers."""

from __future__ import annotations

import json

from libs.validation_lab.stage_errors import (
    plain_english_pipeline_message,
    stage_errors_from_row,
    stage_warnings_from_row,
)


def test_stage_errors_from_row_prefers_errors_json() -> None:
    row = {
        "errors_json": json.dumps(["terminology: connection refused"]),
        "output_json": json.dumps({"errors": ["ignored"]}),
    }
    assert stage_errors_from_row(row) == ["terminology: connection refused"]


def test_stage_warnings_from_row_prefers_warnings_json() -> None:
    row = {
        "warnings_json": json.dumps(
            ['terminology_low_confidence: 1 entity/entities below score threshold 0.55 -- "dysphagia" (score 0.42)']
        ),
        "output_json": json.dumps({"warnings": ["ignored"]}),
    }
    assert len(stage_warnings_from_row(row)) == 1


def test_stage_warnings_from_row_falls_back_to_output_warnings() -> None:
    row = {
        "output_json": json.dumps(
            {
                "warnings": [
                    "coding_verifier: 1 entity classified not_codeable"
                ]
            }
        )
    }
    assert stage_warnings_from_row(row) == [
        "coding_verifier: 1 entity classified not_codeable"
    ]


def test_plain_english_for_terminology_low_confidence() -> None:
    raw = (
        'terminology_low_confidence: 1 entity/entities below score threshold 0.55 -- '
        '"dysphagia" (score 0.42)'
    )
    text = plain_english_pipeline_message(raw)
    assert "dysphagia" in text
    assert "55%" in text
    assert "42%" in text
    assert "left uncoded" in text
    assert "stopped" not in text


def test_plain_english_for_coding_verifier_not_codeable() -> None:
    text = plain_english_pipeline_message(
        "coding_verifier: 1 entity classified not_codeable"
    )
    assert "not coded" in text
    assert "descriptor" in text


def test_plain_english_for_terminology_connection_error() -> None:
    text = plain_english_pipeline_message("terminology: Connection refused")
    assert "terminology service" in text.lower()
