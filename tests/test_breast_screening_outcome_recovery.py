from __future__ import annotations

from libs.ner.breast_screening_outcome_recovery import (
    CONCEPT_ID,
    SNOMED_TERM,
    recover_breast_screening_outcome_finding,
)


def test_recovers_nhs_breast_screening_programme_plus_abnormal_68621() -> None:
    text = (
        "As per GP report list from the NHS Breast Screening Programme. "
        "Breast neoplasm screening abnormal (68621)"
    )
    out = recover_breast_screening_outcome_finding(text, [])

    findings = [e for e in out if e.get("label") == "finding"]
    assert len(findings) == 1
    f = findings[0]
    assert f["snomed_concept_id"] == CONCEPT_ID
    assert f["snomed_term"] == SNOMED_TERM
    assert "Breast neoplasm screening abnormal" in f["text"]
    assert text[f["start"] : f["end"]] == f["text"]


def test_does_not_duplicate_overlapping_finding() -> None:
    text = "NHS breast screening. Breast neoplasm screening abnormal (68621)"
    existing = [
        {
            "text": "Breast neoplasm screening abnormal (68621)",
            "label": "finding",
            "start": 20,
            "end": 62,
        }
    ]
    out = recover_breast_screening_outcome_finding(text, existing)
    assert [e for e in out if e.get("label") == "finding"] == existing


def test_fallback_when_screening_context_distant() -> None:
    text = (
        "NHS breast screening programme referral. "
        "Some other line. "
        "Breast neoplasm screening abnormal (68621)"
    )
    out = recover_breast_screening_outcome_finding(text, [])

    findings = [e for e in out if e.get("label") == "finding"]
    assert len(findings) == 1


def test_no_match_without_breast_screening_context() -> None:
    text = "Breast neoplasm screening abnormal (68621) in isolation"
    out = recover_breast_screening_outcome_finding(text, [])
    assert not any(e.get("label") == "finding" for e in out)
