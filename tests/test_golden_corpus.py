"""Red tests: golden corpus per organisation, service and form version.

Atlas trace:
  DI: DI-9A75B3C6
  DO: DO-E9A3C122
  VT: VT-C73DA421
  Risk: R-238CAF49
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libs.referral_quality.golden_corpus import GoldenCaseError, load_golden_case

_FIXTURE_DIR = (
    Path(__file__).parent / "fixtures" / "golden_corpus" / "rk5_117038_demo-v1"
)


def test_golden_case_keyed_by_org_service_form_version() -> None:
    case = load_golden_case(_FIXTURE_DIR)
    assert case.organization_id == "RK5"
    assert case.service_id == "117038"
    assert case.form_version == "demo-v1"
    assert "discrete hard breast lump" in case.letter.lower()
    assert case.expected_facts
    assert case.expected_facts[0].assertion == "present"
    assert case.completeness.assessable is True
    assert isinstance(case.fired_rules, tuple)
    assert case.sbar.headline_must_not_contain


def test_golden_case_rejects_missing_key(tmp_path: Path) -> None:
    payload = {
        "organization_id": "RK5",
        "service_id": "117038",
        "letter": "Section A\nA1. lump [X]",
        "expected_facts": [{"text": "lump", "assertion": "present"}],
        "completeness": {"assessable": True},
        "fired_rules": [],
        "sbar": {"headline_must_contain": ["lump"]},
    }
    (tmp_path / "case.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GoldenCaseError, match="form_version"):
        load_golden_case(tmp_path)
