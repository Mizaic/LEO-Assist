"""Unit tests for libs/episode_learning/shadow_run.py."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from libs.episode_learning.shadow_run import (
    ShadowComparison,
    aggregate_cohort_report,
    compare_episode_lists,
    persist_shadow_run,
)


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, cypher: str, **params: Any) -> Any:
        self.calls.append((cypher, params))
        return [{"patient_id": params.get("patient_id")}]


def test_compare_full_agreement_returns_one_point_zero():
    cmp = compare_episode_lists(["a", "b"], ["a", "b"])
    assert cmp["agreement"] == 1.0
    assert cmp["added_in_v2"] == []
    assert cmp["dropped_in_v2"] == []


def test_compare_zero_overlap_returns_zero():
    cmp = compare_episode_lists(["a", "b"], ["c", "d"])
    assert cmp["agreement"] == 0.0
    assert cmp["added_in_v2"] == ["c", "d"]
    assert cmp["dropped_in_v2"] == ["a", "b"]


def test_compare_partial_overlap_uses_jaccard():
    cmp = compare_episode_lists(["a", "b", "c"], ["b", "c", "d"])
    assert cmp["agreement"] == round(2 / 4, 4)
    assert cmp["added_in_v2"] == ["d"]
    assert cmp["dropped_in_v2"] == ["a"]


def test_compare_empty_inputs_handle_safely():
    cmp = compare_episode_lists([], [])
    assert cmp["agreement"] == 0.0
    assert cmp["v1_count"] == 0
    assert cmp["v2_count"] == 0


def test_persist_shadow_run_writes_one_row_with_jaccard():
    runner = _FakeRunner()
    when = datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc)
    cmp = persist_shadow_run(
        runner,
        patient_id="p-1",
        v1_episode_ids=["a", "b"],
        v2_episode_ids=["b", "c"],
        run_at=when,
    )
    assert isinstance(cmp, ShadowComparison)
    assert cmp.agreement == round(1 / 3, 4)
    assert cmp.added_in_v2 == ("c",)
    assert cmp.dropped_in_v2 == ("a",)
    assert len(runner.calls) == 1
    cypher, params = runner.calls[0]
    assert "MERGE (s:EpisodeShadowRun" in cypher
    assert params["patient_id"] == "p-1"
    assert params["agreement"] == round(1 / 3, 4)


def _comparison(
    pid: str,
    *,
    v1: tuple[str, ...] = (),
    v2: tuple[str, ...] = (),
) -> ShadowComparison:
    cmp = compare_episode_lists(v1, v2)
    return ShadowComparison(
        patient_id=pid,
        run_at=datetime(2026, 4, 22, tzinfo=timezone.utc),
        v1_episode_ids=v1,
        v2_episode_ids=v2,
        agreement=cmp["agreement"],
        added_in_v2=tuple(cmp["added_in_v2"]),
        dropped_in_v2=tuple(cmp["dropped_in_v2"]),
    )


def test_aggregate_report_counts_full_agreement_correctly():
    rows = [
        _comparison("p-1", v1=("a",), v2=("a",)),
        _comparison("p-2", v1=("b",), v2=("b",)),
        _comparison("p-3", v1=("c",), v2=("d",)),
    ]
    report = aggregate_cohort_report(rows, regression_cohort_patient_ids=[])
    assert report.patients_evaluated == 3
    assert report.auto_case_agreement_rate == round(2 / 3, 4)
    assert report.fully_agreeing_patients == ("p-1", "p-2")
    assert report.diverging_patients == ("p-3",)


def test_regression_recall_counts_v2_with_any_episodes():
    rows = [
        _comparison("p-1", v1=("a",), v2=("a",)),
        _comparison("p-2", v1=("b",), v2=()),  # v2 dropped this patient
        _comparison("p-3", v1=("c",), v2=("c",)),
    ]
    report = aggregate_cohort_report(
        rows, regression_cohort_patient_ids=["p-1", "p-2", "p-3"]
    )
    assert report.regression_recall == round(2 / 3, 4)


def test_aggregate_report_handles_empty_input():
    report = aggregate_cohort_report([], regression_cohort_patient_ids=["p-1"])
    assert report.patients_evaluated == 0
    assert report.auto_case_agreement_rate == 0.0
    assert report.regression_recall == 0.0
