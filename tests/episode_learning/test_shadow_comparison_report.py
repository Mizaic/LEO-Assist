"""Unit tests for scripts/episode_v2/shadow_comparison_report.py."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from libs.episode_learning.shadow_run import ShadowComparison
from scripts.episode_v2.shadow_comparison_report import (
    build_report,
    load_cohort_patient_ids,
    load_comparisons,
    report_to_json,
    report_to_markdown,
)


class _FakeRunner:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, cypher: str, **params: Any) -> Any:
        self.calls.append((cypher, params))
        return self._rows


def _row(
    pid: str,
    *,
    v1: list[str],
    v2: list[str],
    agreement: float,
) -> dict[str, Any]:
    return {
        "patient_id": pid,
        "run_at": datetime(2026, 4, 20, tzinfo=timezone.utc),
        "v1_episode_ids": v1,
        "v2_episode_ids": v2,
        "agreement": agreement,
        "added_in_v2": sorted(set(v2) - set(v1)),
        "dropped_in_v2": sorted(set(v1) - set(v2)),
    }


def test_load_comparisons_maps_rows_to_dataclass():
    runner = _FakeRunner(
        [_row("p-1", v1=["a"], v2=["a"], agreement=1.0)]
    )
    cmps = load_comparisons(runner, since=datetime(2026, 4, 15, tzinfo=timezone.utc))
    assert len(cmps) == 1
    assert isinstance(cmps[0], ShadowComparison)
    assert cmps[0].patient_id == "p-1"
    assert cmps[0].agreement == 1.0


def test_load_cohort_patient_ids_handles_missing_file(tmp_path: Path):
    missing = tmp_path / "missing.json"
    assert load_cohort_patient_ids(missing) == []


def test_load_cohort_patient_ids_extracts_ids(tmp_path: Path):
    cohort_path = tmp_path / "cohort.json"
    cohort_path.write_text(
        json.dumps(
            {
                "version": 1,
                "cohort": [
                    {"patient_id": "p-1"},
                    {"patient_id": "p-2"},
                    {"selection_reason": "no id"},
                ],
            }
        )
    )
    assert load_cohort_patient_ids(cohort_path) == ["p-1", "p-2"]


def test_build_report_combines_runner_and_cohort(tmp_path: Path):
    cohort_path = tmp_path / "cohort.json"
    cohort_path.write_text(
        json.dumps({"cohort": [{"patient_id": "p-1"}, {"patient_id": "p-2"}]})
    )
    runner = _FakeRunner(
        [
            _row("p-1", v1=["a"], v2=["a"], agreement=1.0),
            _row("p-2", v1=["b"], v2=[], agreement=0.0),
        ]
    )
    report = build_report(
        runner,
        cohort_path=cohort_path,
        since=datetime(2026, 4, 15, tzinfo=timezone.utc),
    )
    assert report.patients_evaluated == 2
    assert report.auto_case_agreement_rate == 0.5
    assert report.regression_recall == 0.5


def test_report_to_markdown_includes_headers_and_metrics():
    runner = _FakeRunner(
        [_row("p-1", v1=["a"], v2=["b"], agreement=0.0)]
    )
    cmps = load_comparisons(runner, since=datetime(2026, 4, 15, tzinfo=timezone.utc))
    from libs.episode_learning.shadow_run import aggregate_cohort_report

    report = aggregate_cohort_report(
        cmps, regression_cohort_patient_ids=[]
    )
    md = report_to_markdown(report)
    assert "# Episode Detector v2 -- Shadow Comparison Report" in md
    assert "Patients evaluated: 1" in md
    assert "## Top divergent patients" in md
    assert "p-1" in md


def test_report_to_json_is_serialisable():
    from libs.episode_learning.shadow_run import aggregate_cohort_report

    report = aggregate_cohort_report(
        [], regression_cohort_patient_ids=[]
    )
    payload = report_to_json(report)
    json.dumps(payload)  # must round-trip
    assert payload["patients_evaluated"] == 0
