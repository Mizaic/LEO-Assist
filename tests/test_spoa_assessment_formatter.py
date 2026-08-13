"""Tests for SPoA-aware Assessment formatting."""

from __future__ import annotations

from libs.sbar.assessment_formatter import format_assessment


def test_spoa_assessment_shows_service_and_alternatives() -> None:
    compliance_context = {
        "primary": {
            "service_name": "Breast 2WW Single Point of Access",
            "service_specialty": "Breast",
            "guideline_ids": ["NG12"],
            "supported": False,
            "matched_rules": [],
        },
        "alternatives": {
            "matched_rules": [
                {
                    "rule_id": "alt-1",
                    "name": "Alternative breast rule",
                    "guideline_title": "Suspected cancer",
                    "actions": [{"priority": "2ww", "name": "Mammogram"}],
                }
            ]
        },
        "healthcare_service_missing": False,
    }
    out = format_assessment(
        matched_rules=[],
        patient_codes=["123"],
        compliance_context=compliance_context,
        spoa_disposition="refer_to_alternative_service",
        spoa_disposition_evidence="Receiving service guidelines did not match.",
    )
    assert "Receiving service" in out.markdown
    assert "Supported by receiving service?** no" in out.markdown
    assert "Other guidelines that would support this request" in out.markdown
    assert "Advisory SPoA disposition" not in out.markdown
    assert out.spoa_disposition == "refer_to_alternative_service"


def test_spoa_assessment_primary_supported() -> None:
    compliance_context = {
        "primary": {
            "service_name": "Breast SPoA",
            "service_specialty": "Breast",
            "guideline_ids": ["NG12"],
            "supported": True,
            "matched_rules": [
                {
                    "rule_id": "pri-1",
                    "name": "Nipple discharge rule",
                    "actions": [{"priority": "2ww", "name": "Breast clinic"}],
                }
            ],
        },
        "alternatives": {"matched_rules": []},
    }
    out = format_assessment(
        matched_rules=compliance_context["primary"]["matched_rules"],
        patient_codes=["123"],
        compliance_context=compliance_context,
        spoa_disposition="outpatient_appointment",
        spoa_disposition_evidence="Receiving service guidelines matched.",
    )
    assert "Supported by receiving service?** yes" in out.markdown
    assert "Primary matches" in out.markdown
    assert "Advisory SPoA disposition" not in out.markdown
