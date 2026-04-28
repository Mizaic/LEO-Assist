"""Tests for FTR clustering (ftr_clustering.py)."""

from __future__ import annotations

import pytest

from services.analysis_worker.app.ncda_detector.ftr_clustering import (
    CLUSTER_WINDOW_DAYS,
    FtrCluster,
    build_ftr_clusters,
    cluster_ftrs,
    site_signal,
)
from services.analysis_worker.app.ncda_detector.pair_generator import RoleScore


def _ftr(encounter_id: str, date: str, p: float = 0.8, text: str = "") -> RoleScore:
    return RoleScore(
        encounter_id=encounter_id,
        encounter_date=date,
        role_probabilities={"ftr": p, "dx": 0.05, "seen": 0.05, "treatment": 0.05, "none": 0.05},
        outcome=None,
        outcome_probability=None,
        text=text,
    )


def _dx(encounter_id: str, date: str) -> RoleScore:
    return RoleScore(
        encounter_id=encounter_id,
        encounter_date=date,
        role_probabilities={"ftr": 0.05, "dx": 0.9, "seen": 0.05, "treatment": 0.05, "none": 0.05},
        outcome="cancer_found",
        outcome_probability=0.9,
    )


# ---------------------------------------------------------------------------
# site_signal
# ---------------------------------------------------------------------------

def test_site_signal_prostate():
    assert site_signal("2WW referral for prostate cancer") == "prostate"


def test_site_signal_breast():
    assert site_signal("Fast Track referral to breast clinic") == "breast"


def test_site_signal_none_for_generic():
    assert site_signal("GP consultation - telephone") is None


def test_site_signal_skin():
    assert site_signal("urgent referral: suspected melanoma") == "skin"


# ---------------------------------------------------------------------------
# Same-day / 3-day clustering
# ---------------------------------------------------------------------------

def test_same_day_ftrs_collapsed_to_one():
    scores = [
        _ftr("E1", "2024-05-01", p=0.8),
        _ftr("E2", "2024-05-01", p=0.95),  # higher p - should win
        _dx("E3", "2024-06-01"),
    ]
    result = cluster_ftrs(scores)
    ftr_out = [s for s in result if s.role_probabilities.get("ftr", 0) >= 0.5]
    assert len(ftr_out) == 1, "Two same-day FTRs should collapse to one"
    assert ftr_out[0].encounter_id == "E2", "Highest-p FTR wins"


def test_three_day_span_collapsed():
    scores = [
        _ftr("E1", "2024-05-01"),
        _ftr("E2", "2024-05-02"),
        _ftr("E3", "2024-05-04"),  # 3 days from E1 — chains via E2
    ]
    result = cluster_ftrs(scores)
    ftr_out = [s for s in result if s.role_probabilities.get("ftr", 0) >= 0.5]
    assert len(ftr_out) == 1


def test_four_day_gap_gives_two_clusters():
    scores = [
        _ftr("E1", "2024-05-01"),
        _ftr("E2", "2024-05-05"),  # 4 days — too far
    ]
    result = cluster_ftrs(scores)
    ftr_out = [s for s in result if s.role_probabilities.get("ftr", 0) >= 0.5]
    assert len(ftr_out) == 2


# ---------------------------------------------------------------------------
# Different tumour sites -> separate clusters
# ---------------------------------------------------------------------------

def test_different_sites_kept_separate_even_within_3_days():
    scores = [
        _ftr("E1", "2024-05-01", text="2WW referral prostate"),
        _ftr("E2", "2024-05-02", text="urgent referral breast clinic"),
    ]
    result = cluster_ftrs(scores)
    ftr_out = [s for s in result if s.role_probabilities.get("ftr", 0) >= 0.5]
    assert len(ftr_out) == 2, "Different sites must not be merged"


def test_same_site_within_3_days_merged():
    scores = [
        _ftr("E1", "2024-05-01", text="2WW referral breast"),
        _ftr("E2", "2024-05-03", text="fast track breast clinic referral"),
    ]
    result = cluster_ftrs(scores)
    ftr_out = [s for s in result if s.role_probabilities.get("ftr", 0) >= 0.5]
    assert len(ftr_out) == 1


def test_unknown_site_compatible_with_known():
    """An encounter with no site signal is merged with a known-site one."""
    scores = [
        _ftr("E1", "2024-05-01", text="2WW referral"),            # unknown site
        _ftr("E2", "2024-05-01", text="fast track prostate"),     # prostate
    ]
    result = cluster_ftrs(scores)
    ftr_out = [s for s in result if s.role_probabilities.get("ftr", 0) >= 0.5]
    assert len(ftr_out) == 1


# ---------------------------------------------------------------------------
# Non-FTR scores pass through unchanged
# ---------------------------------------------------------------------------

def test_non_ftr_scores_pass_through():
    dx = _dx("D1", "2024-06-01")
    ftr = _ftr("E1", "2024-05-01")
    result = cluster_ftrs([ftr, dx])
    ids = {s.encounter_id for s in result}
    assert "D1" in ids


def test_empty_scores_returns_empty():
    assert cluster_ftrs([]) == []


def test_no_ftr_candidates_returns_all_unchanged():
    scores = [_dx("D1", "2024-06-01"), _dx("D2", "2024-07-01")]
    result = cluster_ftrs(scores)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# build_ftr_clusters diagnostic API
# ---------------------------------------------------------------------------

def test_build_clusters_reports_site():
    scores = [
        _ftr("E1", "2024-05-01", text="prostate fast track referral"),
        _ftr("E2", "2024-05-01", text="fast track 2WW prostate"),
    ]
    clusters = build_ftr_clusters(scores)
    assert len(clusters) == 1
    assert clusters[0].site == "prostate"
    assert len(clusters[0].members) == 2


def test_build_clusters_two_sites_two_clusters():
    scores = [
        _ftr("E1", "2024-05-01", text="breast clinic fast track"),
        _ftr("E2", "2024-05-02", text="lung cancer suspected referral"),
    ]
    clusters = build_ftr_clusters(scores)
    assert len(clusters) == 2
    sites = {c.site for c in clusters}
    assert "breast" in sites
    assert "lung" in sites


# ---------------------------------------------------------------------------
# Threshold
# ---------------------------------------------------------------------------

def test_below_threshold_ftr_not_clustered():
    """Encounters below ftr_threshold pass straight through as non-FTR."""
    low = RoleScore(
        encounter_id="L1",
        encounter_date="2024-05-01",
        role_probabilities={"ftr": 0.4, "none": 0.6},
        outcome=None,
        outcome_probability=None,
    )
    result = cluster_ftrs([low], ftr_threshold=0.5)
    assert len(result) == 1
    assert result[0].encounter_id == "L1"


# ---------------------------------------------------------------------------
# Window constant sanity
# ---------------------------------------------------------------------------

def test_cluster_window_is_3_days():
    assert CLUSTER_WINDOW_DAYS == 3
