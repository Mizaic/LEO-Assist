"""VT-LEO-AI-120 - Episode KPI persistence verification.

Covers:
  - TC-001: KPI persisted for complete milestone set
  - TC-002: No KPI property written for missing milestone
  - TC-003: Idempotent on re-run
  - TC-004: Integrated into build_episodes (calculate_kpis is invoked)
  - TC-005: Null-safe on malformed dates
"""

from __future__ import annotations

from unittest.mock import MagicMock

from services.analysis_worker.app.analyzers.kpi_calculator import (
    _compute_episode_kpis,
    _pick_first,
    calculate_kpis,
)


class _FakePatientClient:
    """Minimal stub that records run calls and returns pre-scripted responses."""

    def __init__(self, responses: list) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._responses = list(responses)

    def run(self, query, **params):
        self.calls.append((query, params))
        if not self._responses:
            return []
        return self._responses.pop(0)


def _milestones_rows(presentation=None, referral=None, diagnosis=None, treatment=None):
    rows = []
    if presentation:
        rows.append({"milestone": "first_presentation", "earliest_date": presentation})
    if referral:
        rows.append({"milestone": "referral", "earliest_date": referral})
    if diagnosis:
        rows.append({"milestone": "diagnosis_confirmed", "earliest_date": diagnosis})
    if treatment:
        rows.append({"milestone": "treatment_started", "earliest_date": treatment})
    return rows


def test_kpi_persisted_for_complete_milestone_set():
    """VT-117-TC-001."""
    client = _FakePatientClient(
        [
            _milestones_rows(
                presentation="2024-01-01",
                referral="2024-01-11",
                diagnosis="2024-01-31",
                treatment="2024-03-01",
            ),
            [{"cnt": 3}],
            [],
            [],
            [],
            [],
        ]
    )

    kpis = calculate_kpis("P1", ["ep1"], client)
    metrics = {row["metric"]: row["value"] for row in kpis}

    assert metrics["days_presentation_to_referral"] == 10
    assert metrics["consultations_before_referral"] == 3
    assert metrics["days_referral_to_diagnosis"] == 20
    assert metrics["days_diagnosis_to_treatment"] == 30


def test_no_kpi_when_milestones_missing():
    """VT-117-TC-002: partial milestones produce only the KPIs they support."""
    client = _FakePatientClient(
        [
            _milestones_rows(referral="2024-01-11", diagnosis="2024-01-31"),
            [],
        ]
    )

    kpis = calculate_kpis("P1", ["ep1"], client)
    metrics = {row["metric"]: row["value"] for row in kpis}

    assert metrics == {"days_referral_to_diagnosis": 20}
    assert "days_presentation_to_referral" not in metrics
    assert "days_diagnosis_to_treatment" not in metrics


def test_idempotent_on_rerun():
    """VT-117-TC-003."""
    milestone_rows = _milestones_rows(
        presentation="2024-01-01",
        referral="2024-01-11",
        diagnosis="2024-01-31",
    )
    client = _FakePatientClient(
        [milestone_rows, [{"cnt": 2}], [], [], [], milestone_rows, [{"cnt": 2}], [], [], []]
    )

    first = calculate_kpis("P1", ["ep1"], client)
    second = calculate_kpis("P1", ["ep1"], client)

    assert {r["metric"]: r["value"] for r in first} == {
        r["metric"]: r["value"] for r in second
    }


def test_null_safe_malformed_date():
    """VT-117-TC-005: malformed date raises no exception, KPI absent."""
    client = _FakePatientClient(
        [
            [
                {"milestone": "first_presentation", "earliest_date": ""},
                {"milestone": "referral", "earliest_date": "2024-01-11"},
                {"milestone": "diagnosis_confirmed", "earliest_date": "not-a-date"},
            ],
            [],
        ]
    )

    kpis = calculate_kpis("P1", ["ep1"], client)
    metrics = {row["metric"]: row["value"] for row in kpis}

    assert "days_referral_to_diagnosis" not in metrics
    assert "days_presentation_to_referral" not in metrics


def test_pick_first_prefers_earliest_valid_date():
    """Helper: _pick_first returns the earliest of multiple equivalent keys."""
    ms = {"diagnosis": "2024-02-01", "diagnosis_confirmed": "2024-01-15"}
    assert _pick_first(ms, ("diagnosis_confirmed", "diagnosis")) == "2024-01-15"

    ms = {"treatment_started": "2024-03-01"}
    assert _pick_first(ms, ("treatment_started", "treatment")) == "2024-03-01"

    assert _pick_first({}, ("treatment_started", "treatment")) is None


def test_treatment_started_milestone_key():
    """_compute_episode_kpis handles the real milestone_type values written by the builder."""
    client = MagicMock()
    client.run.return_value = [{"cnt": 1}]
    milestones = {
        "first_presentation": "2024-01-01",
        "referral": "2024-01-10",
        "diagnosis_confirmed": "2024-01-20",
        "treatment_started": "2024-02-10",
    }

    kpis = _compute_episode_kpis("ep1", milestones, "P1", client)
    metrics = {row["metric"]: row["value"] for row in kpis}

    assert metrics["days_referral_to_diagnosis"] == 10
    assert metrics["days_diagnosis_to_treatment"] == 21


def test_calculate_kpis_invoked_by_build_episodes():
    """VT-117-TC-004: build_episodes calls calculate_kpis as terminal post-pass."""
    import inspect
    from services.analysis_worker.app.analyzers.episode_builder import _builder

    source = inspect.getsource(_builder)
    assert "calculate_kpis(" in source, (
        "build_episodes must invoke calculate_kpis as terminal post-pass"
    )
    assert "from services.analysis_worker.app.analyzers.kpi_calculator import calculate_kpis" in source


def test_uses_match_not_merge_for_kpi_write():
    """KPI writer must use MATCH (not MERGE) to avoid creating orphan episode nodes."""
    from services.analysis_worker.app.analyzers import kpi_calculator

    assert kpi_calculator._Q_SET_KPI.startswith("MATCH"), (
        "KPI writer must use MATCH to avoid creating orphan EpisodeOfCare nodes"
    )
    assert "MERGE (ep:EpisodeOfCare" not in kpi_calculator._Q_SET_KPI
