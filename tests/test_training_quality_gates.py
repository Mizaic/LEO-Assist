from __future__ import annotations

from libs.training_ext.training_quality import (
    evaluate_label_coverage,
    macro_f1,
    summarise_export_support,
)


def test_export_support_gate_fails_single_label_collapse() -> None:
    report = summarise_export_support(
        {
            "PROCEDURE": {"train": 100, "val": 10, "dev": 10, "test": 10},
        },
        expected_labels=("DISORDER", "FINDING", "PROCEDURE"),
        min_support=30,
    )

    assert report["passed"] is False
    assert report["missing_expected_labels"] == ["DISORDER", "FINDING"]
    assert report["support_total"]["PROCEDURE"] == 130


def test_export_support_normalises_canonical_label_aliases() -> None:
    report = summarise_export_support(
        {
            "OBSERVABLE": {"train": 30, "val": 0, "dev": 0, "test": 0},
        },
        expected_labels=("observable_entity",),
        min_support=30,
    )

    assert report["passed"] is True
    assert report["expected_labels"] == ["OBSERVABLE"]


def test_export_support_gate_passes_balanced_core_labels() -> None:
    report = summarise_export_support(
        {
            "DISORDER": {"train": 30, "val": 2, "dev": 2, "test": 2},
            "FINDING": {"train": 35, "val": 3, "dev": 3, "test": 3},
            "PROCEDURE": {"train": 40, "val": 4, "dev": 4, "test": 4},
        },
        expected_labels=("DISORDER", "FINDING", "PROCEDURE"),
        min_support=30,
    )

    assert report["passed"] is True
    assert report["missing_expected_labels"] == []
    assert report["low_support_expected_labels"] == {}


def test_label_coverage_gate_fails_procedure_only_metrics() -> None:
    report = evaluate_label_coverage(
        {
            "PROCEDURE": {"f1": 0.91, "support": 50},
        },
        expected_labels=("DISORDER", "FINDING", "PROCEDURE"),
        min_evaluated_labels=2,
        min_macro_f1=0.70,
    )

    assert report["passed"] is False
    assert report["macro_f1"] == 0.91
    assert "DISORDER" in report["missing_expected_labels"]
    assert any("evaluated_expected_labels=1" in f for f in report["failures"])


def test_macro_f1_and_label_coverage_pass_balanced_metrics() -> None:
    per_label = {
        "DISORDER": {"f1": 0.8, "support": 40},
        "FINDING": {"f1": 0.7, "support": 35},
        "PROCEDURE": {"f1": 0.9, "support": 45},
    }

    report = evaluate_label_coverage(
        per_label,
        expected_labels=("DISORDER", "FINDING", "PROCEDURE"),
        min_evaluated_labels=3,
        min_macro_f1=0.75,
    )

    assert macro_f1(per_label) == 0.8
    assert report["passed"] is True
    assert report["failures"] == []
