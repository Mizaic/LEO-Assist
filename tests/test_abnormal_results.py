"""Tests for services/analysis_worker/app/analyzers/abnormal_results.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.lab_results.classifier import LabClassification, LabConfigError, LabReferenceRange


def _make_client(
    *,
    demographics: list[dict] | None = None,
    structured: list[dict] | None = None,
    text_rows: list[dict] | None = None,
):
    client = MagicMock()

    def _run(query: str, **_params):
        if "RETURN coalesce(p.sex, p.gender)" in query:
            return demographics or []
        if (
            "MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]"
            in query
        ):
            return structured or []
        if (
            "MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(e:Encounter)"
            in query
        ):
            return text_rows or []
        return []

    client.run.side_effect = _run
    return client


def _make_kg_client():
    client = MagicMock()
    session = MagicMock()
    client.session.return_value.__enter__.return_value = session
    client.session.return_value.__exit__.return_value = None
    return client


def _lab_result(
    *,
    concept_id: str,
    classification: str,
    value: float,
    unit: str = "mmol/L",
    display_name: str = "Potassium",
    band: LabReferenceRange | None = None,
) -> LabClassification:
    resolved_band = band or LabReferenceRange(
        range_id="range-1",
        low=3.5,
        high=5.0,
        critical_low=2.5,
        critical_high=6.5,
        source="kg_seed",
    )
    return LabClassification(
        concept_id=concept_id,
        display_name=display_name,
        classification=classification,
        canonical_value=value,
        canonical_unit=unit,
        reference_range=resolved_band,
        interpretation_concept_id=None,
        interpretation_term=None,
    )


def test_classify_severity_normal():
    from services.analysis_worker.app.analyzers.abnormal_results import (
        classify_severity,
    )

    assert (
        classify_severity(4.2, low=3.5, high=5.0, critical_low=2.5, critical_high=6.5)
        == "normal"
    )


def test_classify_severity_mildly_abnormal():
    from services.analysis_worker.app.analyzers.abnormal_results import (
        classify_severity,
    )

    assert (
        classify_severity(5.2, low=3.5, high=5.0, critical_low=2.5, critical_high=6.5)
        == "mildly_abnormal"
    )


def test_classify_severity_critically_abnormal():
    from services.analysis_worker.app.analyzers.abnormal_results import (
        classify_severity,
    )

    assert (
        classify_severity(7.1, low=3.5, high=5.0, critical_low=2.5, critical_high=6.5)
        == "critically_abnormal"
    )


def test_kg_abnormal_flags_structured_result(monkeypatch):
    from services.analysis_worker.app.analyzers.abnormal_results import (
        detect_abnormal_results,
    )

    def _classify(concept_id, value, unit, *, patient_sex, patient_age, session=None):
        return _lab_result(
            concept_id=concept_id,
            classification="high",
            value=value,
            unit=str(unit or "mmol/L"),
        )

    monkeypatch.setattr(
        "services.analysis_worker.app.analyzers.abnormal_results.classify_lab_result",
        _classify,
    )
    client = _make_client(
        demographics=[{"sex": "female", "date_of_birth": "1985-02-01"}],
        structured=[
            {
                "encounter_id": "E1",
                "date": "2024-03-01",
                "concept_id": "104167008",
                "value": 6.0,
                "unit": "mmol/L",
            }
        ],
    )
    flagged = detect_abnormal_results(
        "P1",
        "2024-01-01",
        "2024-12-31",
        client,
        knowledge_client=_make_kg_client(),
    )
    assert len(flagged) == 1
    assert flagged[0]["classification"] == "high"
    assert flagged[0]["range"]["source"] == "kg_seed"
    assert flagged[0]["severity"] == "warning"


def test_structured_value_wins_over_text_regex(monkeypatch):
    from services.analysis_worker.app.analyzers.abnormal_results import (
        detect_abnormal_results,
    )

    def _classify(concept_id, value, unit, *, patient_sex, patient_age, session=None):
        return _lab_result(
            concept_id=concept_id,
            classification="critically_low",
            value=value,
            unit=str(unit or "g/L"),
            display_name="Haemoglobin",
            band=LabReferenceRange(
                range_id="hb-range",
                low=115,
                high=165,
                critical_low=70,
                critical_high=200,
                source="kg_seed",
            ),
        )

    monkeypatch.setattr(
        "services.analysis_worker.app.analyzers.abnormal_results.classify_lab_result",
        _classify,
    )
    client = _make_client(
        demographics=[{"sex": "female", "date_of_birth": "1985-02-01"}],
        structured=[
            {
                "encounter_id": "E1",
                "date": "2024-03-01",
                "concept_id": "365616006",
                "value": 60.0,
                "unit": "g/L",
            }
        ],
        text_rows=[
            {
                "encounter_id": "E1",
                "date": "2024-03-01",
                "text": "Haemoglobin critically low",
            },
        ],
    )
    flagged = detect_abnormal_results(
        "P1",
        "2024-01-01",
        "2024-12-31",
        client,
        knowledge_client=_make_kg_client(),
    )
    assert len(flagged) == 1
    assert flagged[0]["classification"] == "critically_low"
    assert flagged[0]["severity"] == "critical"


def test_no_range_flags_for_manual_review(monkeypatch):
    from services.analysis_worker.app.analyzers.abnormal_results import (
        detect_abnormal_results,
    )

    def _classify(concept_id, value, unit, *, patient_sex, patient_age, session=None):
        raise LabConfigError(f"No lab result config for observable {concept_id}.")

    monkeypatch.setattr(
        "services.analysis_worker.app.analyzers.abnormal_results.classify_lab_result",
        _classify,
    )
    client = _make_client(
        demographics=[{"sex": "male", "date_of_birth": "1980-01-01"}],
        structured=[
            {
                "encounter_id": "E1",
                "date": "2024-03-01",
                "concept_id": "999999",
                "value": 12.0,
                "unit": "units",
            }
        ],
    )
    flagged = detect_abnormal_results(
        "P1",
        "2024-01-01",
        "2024-12-31",
        client,
        knowledge_client=_make_kg_client(),
    )
    assert len(flagged) == 1
    assert flagged[0]["classification"] == "range_missing"
    assert flagged[0]["severity"] == "warning"


def test_text_fallback_still_works_without_structured_values():
    from services.analysis_worker.app.analyzers.abnormal_results import (
        detect_abnormal_results,
    )

    client = _make_client(
        text_rows=[
            {
                "encounter_id": "E1",
                "date": "2024-03-01",
                "text": "Critical potassium level",
            }
        ]
    )
    flagged = detect_abnormal_results(
        "P1",
        "2024-01-01",
        "2024-12-31",
        client,
        knowledge_client=_make_kg_client(),
    )
    assert len(flagged) == 1
    assert flagged[0]["classification"] == "text_fallback"
    assert flagged[0]["severity"] == "critical"


def test_text_fallback_skips_follow_up_language():
    from services.analysis_worker.app.analyzers.abnormal_results import (
        detect_abnormal_results,
    )

    client = _make_client(
        text_rows=[
            {
                "encounter_id": "E1",
                "date": "2024-03-01",
                "text": "HbA1c abnormal - repeat in 3 months",
            }
        ]
    )
    flagged = detect_abnormal_results(
        "P1",
        "2024-01-01",
        "2024-12-31",
        client,
        knowledge_client=_make_kg_client(),
    )
    assert flagged == []
