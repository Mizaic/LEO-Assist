"""Plain-English Validation Lab stage error helpers."""

from __future__ import annotations

import json

from libs.validation_lab.stage_errors import (
    plain_english_pipeline_error,
    stage_errors_from_row,
)


def test_stage_errors_from_row_prefers_errors_json() -> None:
    row = {
        "errors_json": json.dumps(["terminology: connection refused"]),
        "output_json": json.dumps({"errors": ["ignored"]}),
    }
    assert stage_errors_from_row(row) == ["terminology: connection refused"]


def test_stage_errors_from_row_falls_back_to_output_errors() -> None:
    row = {
        "output_json": json.dumps(
            {
                "errors": [
                    'terminology_low_confidence: 1 entity/entities below score threshold 0.55 -- "dysphagia" (score 0.42)'
                ]
            }
        )
    }
    assert len(stage_errors_from_row(row)) == 1


def test_plain_english_for_terminology_low_confidence() -> None:
    raw = (
        'terminology_low_confidence: 1 entity/entities below score threshold 0.55 -- '
        '"dysphagia" (score 0.42)'
    )
    text = plain_english_pipeline_error(raw)
    assert "dysphagia" in text
    assert "55%" in text
    assert "42%" in text
    assert "unsafe codes" in text


def test_plain_english_for_terminology_connection_error() -> None:
    text = plain_english_pipeline_error("terminology: Connection refused")
    assert "terminology service" in text.lower()
