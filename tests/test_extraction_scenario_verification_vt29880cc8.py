"""VT-29880CC8: extraction scenario expected-string verification.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B492CAFD
  VT: VT-29880CC8

Verifies the VT acceptance criteria:
  AC1 -- the fixed Markdown corpus and expected-string JSON load together.
  AC2 -- scoring compares extracted terms[].text before coding.
  AC3 -- phrase-level precision, recall, and F1 use raw surface strings.
  AC4 -- the pass threshold is fixed at 95% F1.
  AC5 -- missed and extra strings are reported for clinician review.
"""

from __future__ import annotations

from pathlib import Path

from tests.helpers.clinical_extraction_scenario_loader import (
    fixture_dir,
    load_expected_strings,
    score_extraction_cases,
)

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "services/api/app/routers/extraction_scenarios.py"
LOADER = ROOT / "tests/helpers/clinical_extraction_scenario_loader.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_vt29880cc8_tc001_fixed_corpus_and_expected_strings_load() -> None:
    """AC1 -- the fixed Markdown corpus and JSON answer key load together."""
    doc = load_expected_strings()
    cases = doc["cases"]
    base = fixture_dir().parent.parent.parent

    assert doc["traceability"]["verification_test"] == "VT-29880CC8"
    assert len(cases) >= 90
    assert all((base / case["source_markdown"]).is_file() for case in cases)
    assert all(case["expected_strings"] for case in cases)


def test_vt29880cc8_tc002_scorer_contract_is_terms_text_before_coding() -> None:
    """AC2 -- extraction verification compares terms[].text before coding."""
    loader = _read(LOADER)
    doc = load_expected_strings()

    assert doc["validation_scope"] == "extraction_only_terms_text_before_coding"
    assert "terms[].text" in loader
    assert "score_case(case" in _read(ROUTER)


def test_vt29880cc8_tc003_phrase_metrics_use_raw_surface_strings() -> None:
    """AC3 -- precision, recall, and F1 use raw extraction surfaces."""
    doc = load_expected_strings()
    case = doc["cases"][0]
    expected = list(case["expected_strings"])
    extracted = {
        case["case_id"]: [
            expected[0],
            expected[1] if len(expected) > 1 else expected[0],
        ]
    }

    result = score_extraction_cases([case], extracted, doc["normalisation"])

    assert {"precision", "recall", "f1"} <= set(result["overall"])
    assert result["overall"]["true_positive"] == len(set(extracted[case["case_id"]]))
    assert doc["normalisation"] == {
        "casefold": False,
        "trim": False,
        "collapse_whitespace": False,
        "strip_terminal_punctuation": False,
    }


def test_vt29880cc8_tc004_pass_threshold_is_ninety_five_percent() -> None:
    """AC4 -- the verification pass threshold is fixed at 95% phrase F1."""
    doc = load_expected_strings()
    router = _read(ROUTER)

    assert doc["pass_threshold"]["overall_phrase_f1"] == 0.95
    assert "_PASS_THRESHOLD = 0.95" in router


def test_vt29880cc8_tc005_missed_and_extra_strings_are_reported() -> None:
    """AC5 -- missed and extra strings are exposed for clinician review."""
    doc = load_expected_strings()
    case = doc["cases"][0]
    extracted = {case["case_id"]: ["rectal bleeding", "extra phrase"]}

    result = score_extraction_cases([case], extracted, doc["normalisation"])
    row = result["by_case"][0]

    assert row["false_positive"] == 1
    assert row["false_negative"] >= 1
    assert row["extra_strings"] == ["extra phrase"]
    assert row["missed_strings"]
