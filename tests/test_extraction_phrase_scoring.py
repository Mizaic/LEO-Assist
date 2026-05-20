"""Phrase-level F1 scoring with optional containment matching."""

from __future__ import annotations

from tests.helpers.clinical_extraction_scenario_loader import (
    load_expected_strings,
    score_case,
)


def _rules(*, containment: bool) -> dict[str, bool]:
    return {
        "casefold": True,
        "trim": True,
        "collapse_whitespace": True,
        "strip_terminal_punctuation": True,
        "containment_match": containment,
    }


def test_exact_match_without_containment() -> None:
    case = {
        "case_id": "x",
        "expected_strings": ["abnormal mri"],
        "expected_observables": [],
    }
    score = score_case(
        case, ["abnormal mri brain scan"], _rules(containment=False)
    )
    assert score["true_positive"] == 0
    assert score["false_positive"] == 1


def test_containment_match_counts_tp_without_fp() -> None:
    case = {
        "case_id": "x",
        "expected_strings": ["abnormal mri", "visual disturbance"],
        "expected_observables": [],
    }
    score = score_case(
        case,
        ["abnormal mri brain scan", "new onset visual disturbance in the right field"],
        _rules(containment=True),
    )
    assert score["true_positive"] == 2
    assert score["false_positive"] == 0
    assert score["f1"] == 1.0


def test_fixture_rules_match_lowercase_panel_abbrevs_to_gold() -> None:
    """Gold uses Ferritin/HbA1c; post-processing often emits lowercase abbrevs."""
    doc = load_expected_strings()
    case = next(
        c for c in doc["cases"] if c["case_id"] == "brain_cns_email_001"
    )
    score = score_case(
        case,
        ["ferritin", "hba1c"],
        doc["normalisation"],
    )
    assert "Ferritin" not in score["missed_strings"]
    assert "HbA1c" not in score["missed_strings"]
    assert "ferritin" not in score["extra_strings"]
    assert "hba1c" not in score["extra_strings"]


def test_observable_recall_uses_display_names() -> None:
    case = {
        "case_id": "x",
        "expected_strings": ["Hb"],
        "expected_observables": [
            {"test_name": "Haemoglobin", "display_name": "Hb"},
            {"test_name": "Albumin", "display_name": "Alb"},
        ],
    }
    score = score_case(case, ["Albumin 31.2 g/L", "Hb"], _rules(containment=True))
    assert score["observable_recall"] == 1.0
