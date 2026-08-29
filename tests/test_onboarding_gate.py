"""Red tests: teach a form, run its golden letter, fail closed on a bad gate.

Atlas trace:
  DI: DI-9A75B3C6
  DO: DO-E9A3C122
  VT: VT-C73DA421
  Risk: R-238CAF49
"""

from __future__ import annotations

from pathlib import Path

from libs.referral_quality.onboarding_gate import evaluate_onboarding, run_onboarding

_FIXTURE_DIR = (
    Path(__file__).parent / "fixtures" / "golden_corpus" / "rk5_117038_demo-v1"
)


def test_onboarding_command_fails_when_gate_check_fails() -> None:
    report = evaluate_onboarding(
        _FIXTURE_DIR,
        extra_facts=[
            {
                "text": "high BMI is a risk factor",
                "evidence_text": "high BMI is a risk factor. Check CA125.",
                "assertion": "present",
            }
        ],
    )
    assert report.ready is False
    assert report.contamination
    assert report.coverage_incomplete is False
    assert report.completeness_assessable is True
    assert any("assertion" in check.lower() for check in report.checks)


def test_onboarding_command_is_green_for_clean_golden_letter() -> None:
    report = evaluate_onboarding(_FIXTURE_DIR)
    assert report.ready is True
    assert report.contamination == []
    assert report.completeness_assessable is True
    code = run_onboarding(_FIXTURE_DIR)
    assert code == 0
