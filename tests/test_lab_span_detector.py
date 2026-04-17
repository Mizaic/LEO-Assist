"""Unit tests for the lab-span detector / triple-backfill planner.

Covers the real gold-data shapes found in
``scripts/investigations/few_shot_review/verified_gold_few_shot_review_*``:

- Read-coded lab line with value + unit
- Read-coded lab line with value + unit + reference range
- Read-coded lab line with interpretation phrase after the range
- Colon-separated lab line without a Read code
- Bare test name (no value)
- Non-lab free text (must not match)
"""

from __future__ import annotations

import pytest

from libs.training.lab_span_detector import (
    LABEL_FINDING,
    LABEL_OBSERVABLE,
    LABEL_PROCEDURE,
    detect_lab_pattern,
    diagnose_lab_triple_coverage,
    plan_triple_backfill,
)


# -- detect_lab_pattern -------------------------------------------------------


def test_detects_read_coded_observable_with_range() -> None:
    text = "Reticulocyte count (42X..) 62 10^9/L [20 - 80]"
    pat = detect_lab_pattern(text)
    assert pat.matched is True
    assert pat.read_code == "42X.."
    assert pat.has_value_unit is True
    assert pat.has_interpretation is False
    assert pat.test_name_span is not None
    assert pat.test_name_span.text == "Reticulocyte count"
    assert text[pat.test_name_span.start : pat.test_name_span.end] == "Reticulocyte count"
    assert pat.observable_span is not None
    assert pat.observable_span.text.endswith("10^9/L [20 - 80]")
    assert pat.finding_span is None


def test_detects_interpretation_phrase_as_finding() -> None:
    text = (
        "Mean cell haemoglobin level (XE2pb) 32.1 pg [27 - 32] "
        "- Outside reference range"
    )
    pat = detect_lab_pattern(text)
    assert pat.matched is True
    assert pat.has_interpretation is True
    assert pat.finding_span is not None
    assert "Outside reference range" in pat.finding_span.text


def test_colon_separated_lab_without_read_code_is_not_matched() -> None:
    """The strict detector requires a Read/CTV3 bracketed code as well as a
    value+unit. Colon-separated lab lines without a code are deliberately
    rejected to keep the backfill false-positive rate at zero. The lenient
    fallback path lives in ``libs.ner.lab_triple_recovery`` and is exercised
    by ``tests/test_lab_triple_recovery.py``.
    """
    text = "Atypical Lymphocytes: 0.70 x10^9/l; Outside reference range"
    pat = detect_lab_pattern(text)
    assert pat.matched is False
    assert pat.read_code is None


def test_bare_test_name_does_not_match() -> None:
    """Short bare names are indistinguishable from non-lab findings.

    e.g. we cannot reliably tell "Full blood count" from "chest pain" without
    a SNOMED dictionary, so the detector refuses to match.
    """
    pat = detect_lab_pattern("Full blood count")
    assert pat.matched is False


def test_non_lab_prose_does_not_match() -> None:
    text = (
        "The patient reports a 3-month history of fatigue and night sweats."
    )
    pat = detect_lab_pattern(text)
    assert pat.matched is False


def test_empty_text_does_not_match() -> None:
    assert detect_lab_pattern("").matched is False
    assert detect_lab_pattern("   ").matched is False


# -- plan_triple_backfill -----------------------------------------------------


def _ent(text: str, start: int, end: int, label: str) -> dict:
    return {"text": text, "start": start, "end": end, "label": label}


def test_backfill_proposes_observable_when_only_procedure_present() -> None:
    text = "Reticulocyte count (42X..) 62 10^9/L [20 - 80]"
    existing = [_ent("Reticulocyte count", 0, 18, LABEL_PROCEDURE)]
    plan = plan_triple_backfill(text, existing)
    assert plan.matched is True
    assert LABEL_PROCEDURE in plan.existing_labels
    proposed_labels = [e["label"] for e in plan.proposed]
    assert proposed_labels == [LABEL_OBSERVABLE]
    assert plan.proposed[0]["text"].startswith("Reticulocyte count")
    assert plan.proposed[0]["text"].endswith("10^9/L [20 - 80]")
    assert plan.proposed[0]["_backfilled"] is True


def test_backfill_proposes_observable_and_finding_when_only_procedure() -> None:
    text = (
        "Mean cell haemoglobin level (XE2pb) 32.1 pg [27 - 32] "
        "- Outside reference range"
    )
    existing = [_ent("Mean cell haemoglobin level", 0, 27, LABEL_PROCEDURE)]
    plan = plan_triple_backfill(text, existing)
    labels = [e["label"] for e in plan.proposed]
    assert labels == [LABEL_OBSERVABLE, LABEL_FINDING]


def test_backfill_proposes_all_three_when_nothing_present() -> None:
    text = "Serum bilirubin level (44E..) 9 umol/L [< 21] - Abnormal result"
    plan = plan_triple_backfill(text, [])
    labels = [e["label"] for e in plan.proposed]
    assert labels == [LABEL_PROCEDURE, LABEL_OBSERVABLE, LABEL_FINDING]


def test_backfill_is_noop_when_all_three_present() -> None:
    text = (
        "Mean cell volume (42A..) 100 fL [80 - 99] - Outside reference range"
    )
    existing = [
        _ent("Mean cell volume", 0, 16, LABEL_PROCEDURE),
        _ent("Mean cell volume (42A..) 100 fL [80 - 99]", 0, 41, LABEL_OBSERVABLE),
        _ent(text, 0, len(text), LABEL_FINDING),
    ]
    plan = plan_triple_backfill(text, existing)
    assert plan.proposed == []
    assert plan.reason == "complete"


def test_backfill_noop_when_text_not_a_lab_row() -> None:
    text = "The patient has a persistent cough and a sore throat."
    plan = plan_triple_backfill(text, [])
    assert plan.matched is False
    assert plan.proposed == []
    assert plan.reason == "no_lab_pattern"


def test_backfill_without_value_does_not_match() -> None:
    """A bare test name cannot be safely distinguished from prose."""
    plan = plan_triple_backfill("Full blood count", [])
    assert plan.matched is False
    assert plan.reason == "no_lab_pattern"
    assert plan.proposed == []


def test_backfill_does_not_duplicate_exact_span() -> None:
    text = "Reticulocyte count (42X..) 62 10^9/L"
    existing = [
        _ent("Reticulocyte count", 0, 18, LABEL_PROCEDURE),
        _ent("Reticulocyte count (42X..) 62 10^9/L", 0, 36, LABEL_OBSERVABLE),
    ]
    plan = plan_triple_backfill(text, existing)
    assert plan.proposed == []


# -- diagnose_lab_triple_coverage ---------------------------------------------


def test_diagnose_reports_all_missing_for_uncoded_lab() -> None:
    text = (
        "Mean cell volume (42A..) 100 fL [80 - 99] - Outside reference range"
    )
    diag = diagnose_lab_triple_coverage(text, [])
    assert diag["is_lab"] is True
    assert set(diag["missing"]) == {
        LABEL_PROCEDURE,
        LABEL_OBSERVABLE,
        LABEL_FINDING,
    }


def test_diagnose_reports_complete_when_triple_present() -> None:
    text = "Reticulocyte count (42X..) 62 10^9/L [20 - 80]"
    existing = [
        _ent("Reticulocyte count", 0, 18, LABEL_PROCEDURE),
        _ent(text, 0, len(text), LABEL_OBSERVABLE),
    ]
    diag = diagnose_lab_triple_coverage(text, existing)
    assert diag["is_lab"] is True
    # No interpretation phrase, so finding is not required.
    assert diag["missing"] == []


def test_diagnose_reports_non_lab_row_as_not_lab() -> None:
    text = "Patient complains of chest pain radiating to the left arm."
    diag = diagnose_lab_triple_coverage(text, [])
    assert diag["is_lab"] is False
    assert diag["missing"] == []


@pytest.mark.parametrize(
    "text,expected_labels",
    [
        (
            "Plasma C-reactive protein level (XE2dy) < 5 mg/L [< 10]",
            [LABEL_PROCEDURE, LABEL_OBSERVABLE],
        ),
        (
            "Serum vitamin D level (XE2e7) 64 nmol/L",
            [LABEL_PROCEDURE, LABEL_OBSERVABLE],
        ),
        (
            "Haemoglobin A1c level (X772q) 5.6 % [4 - 5.9]",
            [LABEL_PROCEDURE, LABEL_OBSERVABLE],
        ),
    ],
)
def test_parametrized_real_gold_examples(text: str, expected_labels: list[str]) -> None:
    plan = plan_triple_backfill(text, [])
    assert [e["label"] for e in plan.proposed] == expected_labels
