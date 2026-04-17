"""Ground-truth regression harness.

Pins the NCDA ground-truth dataset to the current baselines so any
change that alters episode counts, milestone parity, or the interval
KPI math is caught immediately rather than propagating silently into
dashboards and audits.

Two fixtures under data/ground_truth/ drive the checks:
  - clean_episode_ground_truth.json -- 117 curated episodes with
    first_presentation / referral / first_seen / diagnosis_date /
    treatment_start / outcome / expected_status.
  - ncda_export.json -- derived export with pre-computed interval
    KPIs from the current pipeline.

The harness validates three things:
  1. Schema + cardinality of each file match the recorded baseline.
  2. Distribution tripwires: cancer/benign counts, referral types,
     cancer-type mix. Moving any of these is an explicit design
     decision and must be acknowledged by updating this file.
  3. Interval KPI parity: libs.metrics.compute_interval_kpis recomputed
     on the ground-truth milestones matches the days_* fields baked
     into the NCDA export. Guards against drift between the shared
     metrics library and the export pipeline.

See DI-LEO-AI-125, DO-LEO-AI-125, R-LEO-AI-085, VT-LEO-AI-120.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from libs.metrics import compute_interval_kpis

REPO_ROOT = Path(__file__).resolve().parents[1]
GT_PATH = REPO_ROOT / "data" / "ground_truth" / "clean_episode_ground_truth.json"
NCDA_PATH = REPO_ROOT / "data" / "ground_truth" / "ncda_export.json"

# -- Baselines -----------------------------------------------------------
# These numbers were frozen on 2026-04-16 from the current pipeline. Any
# change is an intentional design decision: update here AND document the
# reason in the commit message.
EXPECTED_EPISODE_COUNT = 117
EXPECTED_PATIENT_COUNT = 90

EXPECTED_OUTCOME_COUNTS: dict[str | None, int] = {
    None: 55,
    "benign": 31,
    "cancer": 31,
}

EXPECTED_STATUS_COUNTS: dict[str, int] = {
    "closed": 104,
    "investigating": 10,
    "active": 3,
}

EXPECTED_REFERRAL_TYPE_COUNTS: dict[str, int] = {
    "gp_initiated": 114,
    "ae_initiated": 3,
}

# Subset of cancer types that must appear with their recorded episode count.
# Smaller buckets (2-3 records) are left out as they are noise-sensitive.
EXPECTED_CANCER_TYPE_MIN_COUNTS: dict[str, int] = {
    "breast": 29,
    "lower_gi": 17,
    "head_neck": 13,
    "skin": 13,
    "lung": 12,
    "urology": 11,
}

VALID_OUTCOMES = {None, "cancer", "benign", "unknown"}
VALID_STATUSES = {"active", "investigating", "closed", "merged", "completed"}
VALID_REFERRAL_TYPES = {
    "gp_initiated",
    "ae_initiated",
    "specialist_initiated",
    "screening",
    "self_presented",
    "unknown",
}


# -- Fixtures ------------------------------------------------------------


def _require_file(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"Ground-truth fixture missing: {path}")


@pytest.fixture(scope="module")
def ground_truth() -> list[dict[str, Any]]:
    _require_file(GT_PATH)
    with GT_PATH.open() as fh:
        data = json.load(fh)
    assert isinstance(data, list)
    return data


@pytest.fixture(scope="module")
def ncda_export() -> dict[str, Any]:
    _require_file(NCDA_PATH)
    with NCDA_PATH.open() as fh:
        data = json.load(fh)
    assert isinstance(data, dict)
    return data


# -- Cardinality ---------------------------------------------------------


class TestCardinality:
    def test_ground_truth_record_count(self, ground_truth):
        assert len(ground_truth) == EXPECTED_EPISODE_COUNT

    def test_ncda_episode_count(self, ncda_export):
        assert ncda_export.get("episode_count") == EXPECTED_EPISODE_COUNT
        assert len(ncda_export["episodes"]) == EXPECTED_EPISODE_COUNT

    def test_ncda_patient_count(self, ncda_export):
        assert ncda_export.get("patient_count") == EXPECTED_PATIENT_COUNT

    def test_unique_patients_match(self, ground_truth):
        unique = {r["patient_id"] for r in ground_truth}
        assert len(unique) == EXPECTED_PATIENT_COUNT

    def test_ground_truth_and_ncda_join_perfectly(
        self, ground_truth, ncda_export
    ):
        gt_keys = {_join_key(r) for r in ground_truth}
        ncda_keys = {_join_key(r) for r in ncda_export["episodes"]}
        assert gt_keys == ncda_keys, (
            "GT and NCDA export must align on "
            "(patient, cancer_type, referral)"
        )


# -- Schema --------------------------------------------------------------


_REQUIRED_GT_FIELDS = (
    "patient_id",
    "cancer_type",
    "referral_type",
    "expected_status",
    "referral",
)


class TestSchema:
    def test_required_fields_present(self, ground_truth):
        for idx, record in enumerate(ground_truth):
            for field in _REQUIRED_GT_FIELDS:
                assert field in record, (
                    f"record {idx} patient {record.get('patient_id')}"
                    f" missing required field {field!r}"
                )

    def test_outcomes_are_valid(self, ground_truth):
        seen = {r.get("diagnosis_outcome") for r in ground_truth}
        assert seen.issubset(VALID_OUTCOMES), (
            f"unexpected outcomes: {seen - VALID_OUTCOMES}"
        )

    def test_statuses_are_valid(self, ground_truth):
        seen = {r.get("expected_status") for r in ground_truth}
        assert seen.issubset(VALID_STATUSES), (
            f"unexpected statuses: {seen - VALID_STATUSES}"
        )

    def test_referral_types_are_valid(self, ground_truth):
        seen = {r.get("referral_type") for r in ground_truth}
        assert seen.issubset(VALID_REFERRAL_TYPES), (
            f"unexpected referral types: {seen - VALID_REFERRAL_TYPES}"
        )

    def test_patient_ids_are_non_empty(self, ground_truth):
        for record in ground_truth:
            pid = str(record.get("patient_id") or "").strip()
            assert pid, "empty patient_id detected in ground truth"


# -- Distribution tripwires ---------------------------------------------


class TestDistributionTripwires:
    def test_outcome_counts_match_baseline(self, ground_truth):
        counts = _count_by(ground_truth, "diagnosis_outcome")
        assert counts == EXPECTED_OUTCOME_COUNTS, _drift_msg(
            "outcome", counts, EXPECTED_OUTCOME_COUNTS
        )

    def test_status_counts_match_baseline(self, ground_truth):
        counts = _count_by(ground_truth, "expected_status")
        assert counts == EXPECTED_STATUS_COUNTS, _drift_msg(
            "status", counts, EXPECTED_STATUS_COUNTS
        )

    def test_referral_type_counts_match_baseline(self, ground_truth):
        counts = _count_by(ground_truth, "referral_type")
        assert counts == EXPECTED_REFERRAL_TYPE_COUNTS, _drift_msg(
            "referral_type", counts, EXPECTED_REFERRAL_TYPE_COUNTS
        )

    def test_cancer_type_minimum_coverage(self, ground_truth):
        counts = _count_by(ground_truth, "cancer_type")
        for cancer_type, expected in EXPECTED_CANCER_TYPE_MIN_COUNTS.items():
            got = counts.get(cancer_type, 0)
            assert got == expected, (
                f"cancer_type {cancer_type!r} count drifted:"
                f" got {got}, expected {expected}"
            )


# -- Interval KPI parity ------------------------------------------------


class TestIntervalKPIParity:
    """libs.metrics.compute_interval_kpis recomputed from GT dates must
    match the days_* fields baked into ncda_export.json for every episode
    where both anchors are present.
    """

    def test_days_presentation_to_referral_matches(self, ground_truth, ncda_export):
        self._assert_parity(
            ground_truth, ncda_export, metric="days_presentation_to_referral"
        )

    def test_days_referral_to_diagnosis_matches(self, ground_truth, ncda_export):
        self._assert_parity(
            ground_truth, ncda_export, metric="days_referral_to_diagnosis"
        )

    def test_days_diagnosis_to_treatment_matches(self, ground_truth, ncda_export):
        # NCDA export does not always include this field (it's per-episode
        # treatment_start). Only check when the export has a non-null value.
        ncda_by_key = {_join_key(r): r for r in ncda_export["episodes"]}
        mismatches: list[str] = []
        for record in ground_truth:
            exported = ncda_by_key.get(_join_key(record)) or {}
            expected = exported.get("days_diagnosis_to_treatment")
            if expected is None:
                continue
            recomputed = compute_interval_kpis(
                {
                    "diagnosis_date": record.get("diagnosis_date"),
                    "treatment_started": record.get("treatment_start"),
                }
            ).get("days_diagnosis_to_treatment")
            if recomputed != expected:
                mismatches.append(
                    f"{_join_key(record)}: ncda={expected} recomputed={recomputed}"
                )
        assert not mismatches, "\n".join(mismatches[:10])

    def _assert_parity(
        self,
        ground_truth: list[dict[str, Any]],
        ncda_export: dict[str, Any],
        metric: str,
    ) -> None:
        ncda_by_key = {_join_key(r): r for r in ncda_export["episodes"]}
        mismatches: list[str] = []
        for record in ground_truth:
            exported = ncda_by_key.get(_join_key(record)) or {}
            expected = exported.get(metric)
            if expected is None:
                continue
            milestones = _record_to_milestones(record)
            recomputed = compute_interval_kpis(milestones).get(metric)
            if recomputed != expected:
                mismatches.append(
                    f"{_join_key(record)}: ncda={expected} recomputed={recomputed}"
                )
        assert not mismatches, (
            f"{len(mismatches)} parity mismatches on {metric}:\n"
            + "\n".join(mismatches[:10])
        )


# -- Helpers -------------------------------------------------------------


def _join_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("patient_id") or ""),
        str(record.get("cancer_type") or ""),
        str(record.get("referral") or ""),
    )


def _count_by(records: list[dict[str, Any]], field: str) -> dict[Any, int]:
    out: dict[Any, int] = {}
    for record in records:
        key = record.get(field)
        out[key] = out.get(key, 0) + 1
    return out


def _record_to_milestones(record: dict[str, Any]) -> dict[str, Any]:
    """Project a ground-truth record onto the milestone alias set
    accepted by libs.metrics.compute_interval_kpis.
    """
    return {
        "presentation_date": record.get("first_presentation"),
        "referral_date": record.get("referral"),
        "diagnosis_date": record.get("diagnosis_date"),
        "treatment_started": record.get("treatment_start"),
    }


def _drift_msg(
    label: str, got: dict[Any, int], expected: dict[Any, int]
) -> str:
    return (
        f"{label} distribution drifted from baseline:\n"
        f"  expected: {expected}\n"
        f"  got:      {got}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
