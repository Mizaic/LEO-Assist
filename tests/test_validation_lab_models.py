"""ValidationCaseSpec equity / observation field regression tests.

Atlas: DI-EB716E68 / DO-A0ADDB38 / VT-C6B93AF0
"""

from __future__ import annotations

from dataclasses import asdict

from libs.validation_lab.models import ValidationCaseSpec


def test_case_spec_without_equity_matches_baseline_keys() -> None:
    spec = ValidationCaseSpec(case_id="c1", title="t", referral_text="note")
    data = asdict(spec)
    assert data["case_id"] == "c1"
    assert data["referral_text"] == "note"
    assert data.get("ethnicity_concept_id") is None
    assert data.get("observations") == []


def test_case_spec_accepts_equity_and_observations() -> None:
    from libs.validation_lab.models import ObservationTrigger

    spec = ValidationCaseSpec(
        case_id="c2",
        title="t",
        referral_text="note",
        ethnicity_concept_id="976631000000101",
        ethnicity_term="White British",
        performance_status_grade=1,
        comorbidity_band="low",
        core20_decile=2,
        plus_group="none",
        observations=[
            ObservationTrigger(observable_id="100", value=412.0, unit="u/mL")
        ],
    )
    assert spec.performance_status_grade == 1
    assert spec.observations[0].unit == "u/mL"
