"""Tests for the reviewed-guard and anchor-stability helpers.

These two transforms run after ``reduce_episode_candidates`` in the full
NCDA detector pipeline and prevent the detector from re-emitting episodes
that a curator already triaged or churning the eid for unchanged
clinical realities.
"""

from __future__ import annotations

from scripts.ncda._episode_guards import (
    apply_reviewed_guard,
    episode_id_hash,
    stabilise_anchor_eids,
)


def _candidate(
    *,
    pid: str = "P1",
    site: str = "breast",
    cohort: str = "1a",
    ftr_date: str | None = "2025-03-10",
    dx_date: str | None = "2025-03-25",
    eid_extra: dict | None = None,
) -> dict:
    return {
        "patient_id": pid,
        "cohort": cohort,
        "site": site,
        "ftr": {"encounter_date": ftr_date} if ftr_date else None,
        "dx": {"encounter_date": dx_date} if dx_date else None,
        **(eid_extra or {}),
    }


def _reviewed(
    *,
    pid: str = "P1",
    cancer_type: str = "Breast",
    referral_date: str = "2025-03-10",
    end_date: str = "2025-04-15",
    episode_id: str = "ep-manual-aaa",
    verdict: str = "confirmed_completed",
) -> dict:
    return {
        "patient_id": pid,
        "source": "",
        "cancer_type": cancer_type,
        "referral_date": referral_date,
        "end_date": end_date,
        "episode_id": episode_id,
        "review_verdict": verdict,
    }


# ---------------------------------------------------------------------------
# apply_reviewed_guard
# ---------------------------------------------------------------------------

def test_reviewed_guard_suppresses_overlapping_same_site_candidate():
    cand = _candidate(site="breast")
    rev = _reviewed(cancer_type="Breast")
    kept, suppressed = apply_reviewed_guard([cand], [rev])
    assert kept == []
    assert len(suppressed) == 1
    assert suppressed[0]["_suppressed_by"]["reviewed_episode_id"] == "ep-manual-aaa"


def test_reviewed_guard_maps_cancer_type_to_detector_site():
    """Reviewed cancer_type=Prostate must cover detector site=urological."""
    cand = _candidate(site="urological", ftr_date="2025-04-10", dx_date="2025-04-30")
    rev = _reviewed(
        cancer_type="Prostate",
        referral_date="2025-04-15",
        end_date="2025-05-10",
        episode_id="ep-manual-prostate",
    )
    kept, suppressed = apply_reviewed_guard([cand], [rev])
    assert kept == []
    assert suppressed[0]["_suppressed_by"]["reviewed_cancer_type"] == "Prostate"


def test_reviewed_guard_keeps_candidate_for_different_site():
    cand = _candidate(site="lower_gi")
    rev = _reviewed(cancer_type="Breast")
    kept, suppressed = apply_reviewed_guard([cand], [rev])
    assert len(kept) == 1
    assert suppressed == []


def test_reviewed_guard_keeps_candidate_outside_window():
    cand = _candidate(site="breast", ftr_date="2026-09-01", dx_date="2026-09-15")
    rev = _reviewed(
        cancer_type="Breast",
        referral_date="2025-03-10",
        end_date="2025-04-15",
    )
    kept, suppressed = apply_reviewed_guard([cand], [rev])
    assert len(kept) == 1
    assert suppressed == []


def test_reviewed_guard_unknown_review_site_covers_anything():
    """Reviewed Other / Unknown Primary is treated as a wildcard cover."""
    cand = _candidate(site="lower_gi", ftr_date="2025-03-10", dx_date="2025-03-15")
    rev = _reviewed(cancer_type="Other")
    kept, suppressed = apply_reviewed_guard([cand], [rev])
    assert kept == []
    assert suppressed[0]["_suppressed_by"]["reviewed_cancer_type"] == "Other"


def test_reviewed_guard_ignores_detector_source_episodes():
    """Only ``source != ncda_detector`` rows count as 'reviewed'."""
    cand = _candidate()
    rev = _reviewed()
    rev["source"] = "ncda_detector"
    kept, suppressed = apply_reviewed_guard([cand], [rev])
    assert len(kept) == 1
    assert suppressed == []


# ---------------------------------------------------------------------------
# stabilise_anchor_eids
# ---------------------------------------------------------------------------

def test_anchor_stabilisation_swaps_eid_when_within_window():
    """Detector eid drift of 1 day for same patient/site should re-use eid."""
    existing = {
        "patient_id": "P1",
        "source": "ncda_detector",
        "site": "urological",
        "episode_id": "OLD_EID",
        "referral_date": "2025-08-18",
        "end_date": None,
    }
    cand = _candidate(
        pid="P1",
        site="urological",
        ftr_date="2025-08-19",
        dx_date="2025-09-06",
    )
    out = stabilise_anchor_eids(
        [cand], [existing], eid_for_candidate=episode_id_hash, window_days=14
    )
    assert out[0]["_stable_eid"] == "OLD_EID"
    assert out[0]["_stable_eid_drift_days"] == 1


def test_anchor_stabilisation_does_not_swap_for_different_site():
    existing = {
        "patient_id": "P1",
        "source": "ncda_detector",
        "site": "lower_gi",
        "episode_id": "OLD_EID",
        "referral_date": "2025-08-18",
    }
    cand = _candidate(pid="P1", site="urological", ftr_date="2025-08-19")
    out = stabilise_anchor_eids(
        [cand], [existing], eid_for_candidate=episode_id_hash, window_days=14
    )
    assert "_stable_eid" not in out[0]


def test_anchor_stabilisation_does_not_swap_for_large_drift():
    existing = {
        "patient_id": "P1",
        "source": "ncda_detector",
        "site": "urological",
        "episode_id": "OLD_EID",
        "referral_date": "2024-01-01",
    }
    cand = _candidate(
        pid="P1", site="urological", ftr_date="2025-08-19", dx_date="2025-09-06"
    )
    out = stabilise_anchor_eids(
        [cand], [existing], eid_for_candidate=episode_id_hash, window_days=14
    )
    assert "_stable_eid" not in out[0]


def test_anchor_stabilisation_skips_when_eid_already_matches():
    """If the deterministic hash already matches an existing eid, no swap."""
    eid = episode_id_hash("P1", "urological", "2025-08-19")
    existing = {
        "patient_id": "P1",
        "source": "ncda_detector",
        "site": "urological",
        "episode_id": eid,
        "referral_date": "2025-08-19",
    }
    cand = _candidate(
        pid="P1", site="urological", ftr_date="2025-08-19", dx_date="2025-09-06"
    )
    out = stabilise_anchor_eids(
        [cand], [existing], eid_for_candidate=episode_id_hash, window_days=14
    )
    assert "_stable_eid" not in out[0]
