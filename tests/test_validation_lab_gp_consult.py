"""Tests for Validation Lab SOAP GP consult synthesis.

Atlas: DI-3002D641 / VT-B79AF7AC
"""

from __future__ import annotations

from datetime import date

from libs.validation_lab.gp_consult import (
    clinical_body_from_referral,
    referral_delay_days,
    referral_needs_lab_wait,
    synthesise_gp_encounter,
)
from libs.validation_lab.models import ObservationTrigger, ValidationCaseSpec


def test_clinical_body_strips_dear_greeting() -> None:
    body = clinical_body_from_referral(
        "Dear Endoscopy Team,\n\n"
        "Epigastric pain and haematemesis for 1 week.\n\n"
        "Yours sincerely,\nDr Smith"
    )
    assert "Dear" not in body
    assert "Epigastric pain" in body
    assert "Yours sincerely" not in body


def test_lab_wait_from_observations() -> None:
    assert referral_needs_lab_wait(
        referral_text="Please review",
        observations=[
            ObservationTrigger(observable_id="x", value=42.0, unit="u/ml", term="CA125")
        ],
    )


def test_lab_wait_from_text_markers() -> None:
    assert referral_needs_lab_wait(
        referral_text="PSA is raised at 12 ng/ml. Please advise.",
        observations=[],
    )
    assert not referral_needs_lab_wait(
        referral_text="Obvious dysphagia and weight loss.",
        observations=[],
    )


def test_delay_days_longer_when_labs_present() -> None:
    fast = referral_delay_days(
        case_id="case-fast",
        referral_text="Haematemesis today, urgent review.",
    )
    slow = referral_delay_days(
        case_id="case-slow",
        referral_text="Awaiting PSA and full blood count results.",
    )
    assert fast in (0, 1)
    assert 2 <= slow <= 5


def test_synthesise_gp_encounter_is_soap_not_letter() -> None:
    spec = ValidationCaseSpec(
        case_id="mt-1",
        title="Michael",
        patient_name="Michael Thompson",
        referral_text=(
            "Dear Endoscopy Team,\n\n"
            "Epigastric pain and haematemesis.\n\n"
            "Yours sincerely"
        ),
    )
    enc, referral_date = synthesise_gp_encounter(
        spec,
        referral_text=spec.referral_text,
        as_of=date(2026, 7, 20),
    )
    assert enc.text.startswith("Subjective:")
    assert "Dear Endoscopy" not in enc.text
    assert "Plan:" in enc.text
    assert "Referral" in enc.text
    assert referral_date == "2026-07-20"
    assert enc.date <= referral_date
