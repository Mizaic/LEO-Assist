"""Tests for the regression-cohort builder.

Atlas trace:
  DI: DI-8A5FCF4F (Defence-in-depth episode detector with coverage fail-safe)
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-8A5FCF4F")
"""

from __future__ import annotations

from scripts.episode_v2 import build_regression_cohort as brc


def _candidate(
    patient_id: str,
    *,
    event_count: int = 5,
    sites: list[str] | None = None,
    statuses: list[str] | None = None,
    episodes: list[str] | None = None,
) -> dict:
    return {
        "patient_id": patient_id,
        "event_count": event_count,
        "event_types": ["EpisodeManualAttach"],
        "episode_ids": episodes or ["ep-x", "ep-y"],
        "sites": sites or ["breast"],
        "statuses": statuses or ["active"],
    }


def test_seed_case_is_first_and_9990001004():
    cohort = brc.build_cohort([], limit=10)
    assert cohort["cohort"][0]["patient_id"] == brc.SEED_PATIENT
    assert cohort["cohort"][0]["selection_reason"] == "seed"
    assert cohort["cohort"][0]["expected_episode_count_min"] == 3


def test_balanced_selection_prefers_variety():
    candidates = [
        _candidate(f"single-{i}", sites=["breast"], episodes=["ep-only"])
        for i in range(5)
    ] + [
        _candidate(f"multi-{i}", sites=["breast", "lung"]) for i in range(5)
    ] + [
        _candidate(
            f"benign-{i}",
            sites=["lung"],
            statuses=["benign_closure"],
        )
        for i in range(5)
    ]
    cohort = brc.build_cohort(candidates, limit=10)
    reasons = [c["selection_reason"] for c in cohort["cohort"][1:]]
    assert reasons.count("single_pathway") >= 3
    assert reasons.count("multi_pathway") >= 3
    assert reasons.count("benign_closure") >= 3


def test_seed_patient_excluded_from_candidates():
    candidates = [_candidate(brc.SEED_PATIENT)]
    cohort = brc.build_cohort(candidates, limit=10)
    extra = [c for c in cohort["cohort"][1:] if c["patient_id"] == brc.SEED_PATIENT]
    assert extra == []


def test_limit_caps_total_count():
    candidates = [_candidate(f"p-{i}") for i in range(50)]
    cohort = brc.build_cohort(candidates, limit=5)
    assert len(cohort["cohort"]) == 5


def test_empty_candidates_returns_seed_only():
    cohort = brc.build_cohort([], limit=10)
    assert len(cohort["cohort"]) == 1
    assert cohort["cohort"][0]["patient_id"] == brc.SEED_PATIENT


def test_classify_candidate_buckets():
    benign = _candidate("p", statuses=["benign_closure"])
    multi = _candidate("p", sites=["breast", "lung"])
    single = _candidate("p", sites=["breast"], episodes=["ep-only"])
    assert brc._classify_candidate(benign) == "benign_closure"
    assert brc._classify_candidate(multi) == "multi_pathway"
    assert brc._classify_candidate(single) == "single_pathway"
