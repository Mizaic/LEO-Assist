"""Assessments API coerces Neo4j scalar types for Pydantic models."""

from services.analytics_api.app.routers.patients_epr_subresources import (
    AssessmentRow,
    _coerce_optional_text,
)


def test_coerce_optional_text_handles_boolean_stt():
    assert _coerce_optional_text(True) == "true"
    assert _coerce_optional_text(False) == "false"
    assert _coerce_optional_text(None) is None


def test_assessment_row_accepts_boolean_stt_from_graph():
    row = AssessmentRow(
        assessment_id="assessment_1",
        stt=_coerce_optional_text(True),
        stt_evidence="needs imaging",
    )
    assert row.stt == "true"
