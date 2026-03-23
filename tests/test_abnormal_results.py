"""Tests for services/analysis_worker/app/analyzers/abnormal_results.py."""

from __future__ import annotations

from unittest.mock import MagicMock


def _make_client(
    *,
    demographics: list[dict] | None = None,
    structured: list[dict] | None = None,
    text_rows: list[dict] | None = None,
    reference_lookup: list[dict] | None = None,
):
    client = MagicMock()

    def _run(query: str, **_params):
        if "RETURN coalesce(p.sex, p.gender)" in query:
            return demographics or []
        if "MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]" in query:
            return structured or []
        if "MATCH (rr:ReferenceRange)" in query:
            return reference_lookup or []
        if "MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(e:Encounter)" in query:
            return text_rows or []
        return []

    client.run.side_effect = _run
    return client


def test_classify_severity_normal():
    from services.analysis_worker.app.analyzers.abnormal_results import classify_severity

    assert classify_severity(4.2, low=3.5, high=5.0, critical_low=2.5, critical_high=6.5) == "normal"


def test_classify_severity_mildly_abnormal():
    from services.analysis_worker.app.analyzers.abnormal_results import classify_severity

    assert classify_severity(5.2, low=3.5, high=5.0, critical_low=2.5, critical_high=6.5) == "mildly_abnormal"


def test_classify_severity_critically_abnormal():
    from services.analysis_worker.app.analyzers.abnormal_results import classify_severity

    assert classify_severity(7.1, low=3.5, high=5.0, critical_low=2.5, critical_high=6.5) == "critically_abnormal"


def test_lookup_uses_tenant_override_before_platform():
    from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

    client = _make_client(
        demographics=[{"sex": "female", "date_of_birth": "1985-02-01"}],
        structured=[
            {"encounter_id": "E1", "date": "2024-03-01", "concept_id": "104167008", "value": 6.0, "unit": "mmol/L"}
        ],
        reference_lookup=[
            {
                "low": 3.5,
                "high": 5.0,
                "critical_low": 2.5,
                "critical_high": 6.5,
                "org_id": "org-1",
                "source": "tenant_override",
                "range_id": "tenant-range",
                "preferred_term": "Potassium",
            }
        ],
    )
    flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", client, org_id="org-1")
    assert len(flagged) == 1
    assert flagged[0]["range"]["org_id"] == "org-1"
    assert flagged[0]["classification"] == "mildly_abnormal"


def test_structured_value_wins_over_text_regex():
    from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

    client = _make_client(
        demographics=[{"sex": "female", "date_of_birth": "1985-02-01"}],
        structured=[
            {"encounter_id": "E1", "date": "2024-03-01", "concept_id": "365616006", "value": 60.0, "unit": "g/L"}
        ],
        reference_lookup=[
            {
                "low": 115,
                "high": 165,
                "critical_low": 70,
                "critical_high": 200,
                "org_id": None,
                "source": "platform_default",
                "range_id": "platform-hb",
                "preferred_term": "Haemoglobin",
            }
        ],
        text_rows=[
            {"encounter_id": "E1", "date": "2024-03-01", "text": "Haemoglobin critically low"},
        ],
    )
    flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", client)
    assert len(flagged) == 1
    assert flagged[0]["classification"] == "critically_abnormal"
    assert flagged[0]["severity"] == "critical"


def test_no_range_flags_for_manual_review():
    from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

    client = _make_client(
        demographics=[{"sex": "male", "date_of_birth": "1980-01-01"}],
        structured=[
            {"encounter_id": "E1", "date": "2024-03-01", "concept_id": "999999", "value": 12.0, "unit": "units"}
        ],
        reference_lookup=[],
    )
    flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", client, org_id="org-1")
    assert len(flagged) == 1
    assert flagged[0]["classification"] == "range_missing"
    assert flagged[0]["severity"] == "warning"


def test_text_fallback_still_works_without_structured_values():
    from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

    client = _make_client(
        text_rows=[{"encounter_id": "E1", "date": "2024-03-01", "text": "Critical potassium level"}]
    )
    flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", client)
    assert len(flagged) == 1
    assert flagged[0]["classification"] == "text_fallback"
    assert flagged[0]["severity"] == "critical"


def test_text_fallback_skips_follow_up_language():
    from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

    client = _make_client(
        text_rows=[{"encounter_id": "E1", "date": "2024-03-01", "text": "HbA1c abnormal - repeat in 3 months"}]
    )
    flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", client)
    assert flagged == []
