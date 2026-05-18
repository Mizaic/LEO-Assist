"""Tests for Stage 11 nightly self-learning job."""

from __future__ import annotations

import pytest

pytest.importorskip("sklearn")

from pathlib import Path

from services.training_worker.app.jobs.ncda_nightly import (
    DRIFT_DROP_POINTS,
    detect_drift,
    run_nightly,
    write_run_log,
)


def _gold_rows():
    return [
        {"role": "ftr", "text": "fast track 2WW (XaMeA)"},
        {"role": "dx", "outcome": "cancer_found", "text": "(XE1vW) malignant rectal tumour"},
        {"role": "dx", "outcome": "cancer_excluded", "text": "discharged from 2WW, all clear"},
        {"role": "treatment", "text": "first cycle chemotherapy"},
        {"role": "none", "text": "telephone consultation"},
    ]


def _silver_rows():
    return [{"role": "ftr", "text": "two-week-wait referral"}]


def _pair_rows():
    return [
        {"features": {"gap_days": 20, "ftr_role_p": 0.9, "dx_role_p": 0.9}, "label": 1},
        {"features": {"gap_days": 200, "ftr_role_p": 0.3, "dx_role_p": 0.3}, "label": 0},
    ]


def _evaluator(role_artifact, linkage_artifact):
    return {
        "role_metrics": {
            "ftr": {"f1": 0.9},
            "dx": {"f1": 0.85},
            "treatment": {"f1": 0.7},
            "none": {"f1": 0.95},
        },
        "cohort_metrics": {
            "1a": {"precision": 0.85},
            "1b": {"precision": 0.8},
            "2": {"precision": 0.75},
            "3": {"precision": 0.72},
        },
    }


def _failing_evaluator(role_artifact, linkage_artifact):
    return {
        "role_metrics": {"ftr": {"f1": 0.4}},
        "cohort_metrics": {"1a": {"precision": 0.85}},
    }


def test_run_nightly_trains_and_evaluates(tmp_path: Path):
    role_artifact = tmp_path / "role.joblib"
    linkage_artifact = tmp_path / "linkage.joblib"
    promoted_calls: list[tuple] = []

    def promoter(r, l, m):
        promoted_calls.append((r, l, m))
        return True

    result = run_nightly(
        gold_rows_loader=_gold_rows,
        silver_rows_loader=_silver_rows,
        pair_rows_loader=_pair_rows,
        role_artifact_path=role_artifact,
        linkage_artifact_path=linkage_artifact,
        evaluator=_evaluator,
        promoter=promoter,
    )
    assert role_artifact.exists()
    assert linkage_artifact.exists()
    assert result.metrics
    assert result.promoted is True
    assert promoted_calls


def test_run_nightly_does_not_promote_when_role_f1_below_floor(tmp_path: Path):
    result = run_nightly(
        gold_rows_loader=_gold_rows,
        silver_rows_loader=_silver_rows,
        pair_rows_loader=_pair_rows,
        role_artifact_path=tmp_path / "r.joblib",
        linkage_artifact_path=tmp_path / "l.joblib",
        evaluator=_failing_evaluator,
        promoter=lambda r, l, m: True,
    )
    assert result.promoted is False


def test_detect_drift_alerts_when_precision_drops():
    today = {
        "cohort_metrics": {
            "1a": {"precision": 0.6},  # was 0.85
        }
    }
    history = [
        {"cohort_metrics": {"1a": {"precision": 0.85}}},
        {"cohort_metrics": {"1a": {"precision": 0.85}}},
    ]
    alerts = detect_drift(today, history)
    assert any("1a" in a for a in alerts)


def test_detect_drift_silent_when_precision_steady():
    today = {"cohort_metrics": {"1a": {"precision": 0.84}}}
    history = [{"cohort_metrics": {"1a": {"precision": 0.85}}}] * 3
    alerts = detect_drift(today, history)
    assert alerts == []


def test_detect_drift_threshold_constant_documents_change_size():
    """Drift threshold should be small enough to catch a 3-point drop but
    not so small as to alert on noise."""
    assert 0.01 <= DRIFT_DROP_POINTS <= 0.05


def test_write_run_log_persists_metrics(tmp_path: Path):
    from services.training_worker.app.jobs.ncda_nightly import NightlyResult

    result = NightlyResult(
        started_at="2024-01-01T00:00:00",
        finished_at="2024-01-01T00:30:00",
        metrics={"role_metrics": {"ftr": {"f1": 0.9}}},
        promoted=True,
    )
    log = write_run_log(result, tmp_path)
    assert log.exists()
    payload = log.read_text()
    assert '"promoted": true' in payload
    assert "f1" in payload
