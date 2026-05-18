"""Unit tests for scripts/episode_v2/hard_cut.py."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.episode_v2.hard_cut import (
    evaluate_shadow_gate,
    perform_cut,
    planned_deletions,
    render_atlas_obsolescence_plan,
)


def _write_report(path: Path, **payload) -> None:
    base = {
        "auto_case_agreement_rate": 1.0,
        "regression_recall": 1.0,
        "patients_evaluated": 12,
    }
    base.update(payload)
    path.write_text(json.dumps(base))


def test_gate_fails_when_report_missing(tmp_path: Path):
    verdict = evaluate_shadow_gate(tmp_path / "missing.json")
    assert verdict.passed is False
    assert "not found" in verdict.rationale


def test_gate_fails_when_report_unreadable(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    verdict = evaluate_shadow_gate(bad)
    assert verdict.passed is False
    assert "unreadable" in verdict.rationale


def test_gate_fails_when_report_too_old(tmp_path: Path):
    report = tmp_path / "report.json"
    _write_report(report)
    old = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
    os.utime(report, (old, old))
    verdict = evaluate_shadow_gate(report, max_age_days=14)
    assert verdict.passed is False
    assert "stale" in verdict.rationale


def test_gate_fails_when_too_few_patients(tmp_path: Path):
    report = tmp_path / "report.json"
    _write_report(report, patients_evaluated=3)
    verdict = evaluate_shadow_gate(report)
    assert verdict.passed is False
    assert "10 patients" in verdict.rationale


def test_gate_fails_when_agreement_below_threshold(tmp_path: Path):
    report = tmp_path / "report.json"
    _write_report(report, auto_case_agreement_rate=0.95)
    verdict = evaluate_shadow_gate(report)
    assert verdict.passed is False
    assert "agreement" in verdict.rationale


def test_gate_fails_when_recall_below_threshold(tmp_path: Path):
    report = tmp_path / "report.json"
    _write_report(report, regression_recall=0.9)
    verdict = evaluate_shadow_gate(report)
    assert verdict.passed is False
    assert "recall" in verdict.rationale


def test_gate_passes_when_report_meets_all_criteria(tmp_path: Path):
    report = tmp_path / "report.json"
    _write_report(report)
    verdict = evaluate_shadow_gate(report)
    assert verdict.passed is True
    assert "passed" in verdict.rationale


def test_planned_deletions_only_returns_existing_paths(tmp_path: Path):
    paths = ("does/not/exist", "also/not/here")
    out = planned_deletions(repo_root=tmp_path, paths=paths)
    assert out == []


def test_perform_cut_removes_files_and_directories(tmp_path: Path):
    file_target = tmp_path / "v1_file.py"
    dir_target = tmp_path / "v1_dir"
    file_target.write_text("module")
    (dir_target / "nested").mkdir(parents=True)
    (dir_target / "nested" / "x.py").write_text("module")
    deleted = perform_cut(
        repo_root=tmp_path,
        paths=("v1_file.py", "v1_dir"),
    )
    assert sorted(p.name for p in deleted) == ["v1_dir", "v1_file.py"]
    assert not file_target.exists()
    assert not dir_target.exists()


def test_perform_cut_skips_missing_paths(tmp_path: Path):
    deleted = perform_cut(
        repo_root=tmp_path,
        paths=("does/not/exist",),
    )
    assert deleted == []


def test_atlas_plan_lists_dos_and_dis():
    plan = render_atlas_obsolescence_plan()
    assert "## Design Outputs" in plan
    assert "## Design Inputs" in plan
    assert "DO-0C7A443A" in plan
    assert "DI-080A2454" in plan
    assert "Replaced by Episode Detector v2" in plan
