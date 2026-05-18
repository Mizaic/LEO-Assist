"""Locked baseline tests for the NCDA evaluation harness (Stage 12)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.analysis_worker.app.ncda_detector.evaluation import (
    breach_flag_accuracy,
    coverage,
    days_error,
    evaluate,
    false_alarm_rate_cohort_3,
    per_cohort_metrics,
    per_role_metrics,
)


def test_per_role_metrics_simple():
    y_true = ["ftr", "dx", "treatment", "none", "ftr", "dx"]
    y_pred = ["ftr", "dx", "treatment", "none", "none", "dx"]
    out = per_role_metrics(y_true, y_pred)
    assert out["dx"]["precision"] == 1.0
    assert out["dx"]["recall"] == 1.0
    assert out["dx"]["f1"] == 1.0
    assert out["ftr"]["recall"] == 0.5
    assert out["none"]["support"] == 1


def test_per_role_metrics_empty_class_safe():
    out = per_role_metrics(["a", "a"], ["b", "b"])
    assert out["a"]["precision"] == 0.0
    assert out["b"]["precision"] == 0.0


def test_per_role_metrics_length_mismatch_raises():
    with pytest.raises(ValueError):
        per_role_metrics(["a"], ["a", "b"])


def test_per_cohort_metrics_returns_same_shape():
    out = per_cohort_metrics(["1a", "2", "3"], ["1a", "2", "1a"])
    assert "1a" in out and "f1" in out["1a"]


def test_days_error_basic():
    out = days_error([0, 5, 10], [0, 7, 8])
    assert out["mae"] == round((0 + 2 + 2) / 3, 3)
    assert out["max"] == 2.0
    assert out["n"] == 3


def test_days_error_empty():
    assert days_error([], [])["n"] == 0


def test_breach_flag_accuracy():
    out = breach_flag_accuracy([True, False, True, True], [True, True, True, False])
    assert out["accuracy"] == 0.5
    assert out["n"] == 4


def test_breach_flag_accuracy_empty():
    assert breach_flag_accuracy([], [])["n"] == 0


def test_coverage():
    assert coverage(["a", "b"], ["a", "b", "c"]) == round(2 / 3, 4)
    assert coverage([], []) == 1.0


def test_false_alarm_rate_cohort_3():
    fa = false_alarm_rate_cohort_3(["x", "y", "z"], ["x"])
    assert fa == round(2 / 3, 4)
    assert false_alarm_rate_cohort_3([], []) == 0.0


def test_evaluate_full_payload_baseline():
    """Lock baseline numbers so future regressions are caught."""
    metrics = evaluate(
        role_y_true=["ftr", "dx", "treatment", "none", "dx"],
        role_y_pred=["ftr", "dx", "treatment", "none", "dx"],
        cohort_y_true=["1a", "1b", "2", "3"],
        cohort_y_pred=["1a", "1b", "2", "3"],
        ftr_dx_days_pred=[10, 20, 28],
        ftr_dx_days_gold=[10, 22, 26],
        breach_flags_pred=[True, False, False],
        breach_flags_gold=[True, False, False],
        pair_recovered_ids=["P1", "P2"],
        pair_gold_ids=["P1", "P2", "P3"],
        predicted_cohort_3_ids=["A", "B"],
        gold_cohort_3_ids=["A"],
    )
    role = metrics["role_metrics"]
    assert role["ftr"]["f1"] == 1.0
    assert role["dx"]["f1"] == 1.0
    cohort = metrics["cohort_metrics"]
    assert all(cohort[c]["f1"] == 1.0 for c in ("1a", "1b", "2", "3"))
    assert metrics["days_error"]["ftr_to_dx"]["max"] == 2.0
    assert metrics["breach_flag_accuracy"]["accuracy"] == 1.0
    assert metrics["coverage"] == round(2 / 3, 4)
    assert metrics["cohort_3_false_alarm_rate"] == 0.5


def test_evaluate_cli_runs(tmp_path: Path):
    """Smoke test the CLI entrypoint."""
    from scripts.ncda.evaluate import main

    payload = {
        "role_y_true": ["ftr", "dx"],
        "role_y_pred": ["ftr", "dx"],
        "cohort_y_true": ["1a"],
        "cohort_y_pred": ["1a"],
        "ftr_dx_days_pred": [10],
        "ftr_dx_days_gold": [10],
        "breach_flags_pred": [True],
        "breach_flags_gold": [True],
        "pair_recovered_ids": ["P1"],
        "pair_gold_ids": ["P1"],
        "predicted_cohort_3_ids": [],
        "gold_cohort_3_ids": [],
    }
    in_path = tmp_path / "payload.json"
    in_path.write_text(json.dumps(payload))
    out_path = tmp_path / "report.json"
    rc = main(["--input", str(in_path), "--output", str(out_path), "--json"])
    assert rc == 0
    assert out_path.exists()
    parsed = json.loads(out_path.read_text())
    assert parsed["role_metrics"]["ftr"]["f1"] == 1.0
