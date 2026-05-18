"""Tests for full NCDA dry-run episode reduction."""

from __future__ import annotations

from scripts.ncda.run_full_cancer_episode_detection import reduce_episode_candidates


def _row(
    *,
    patient_id: str = "p",
    cohort: str,
    site: str | None,
    ftr_date: str | None = None,
    seen_date: str | None = None,
    dx_date: str | None = None,
    outcome: str | None = None,
) -> dict:
    return {
        "patient_id": patient_id,
        "pathway_index": 1,
        "cohort": cohort,
        "site": site,
        "diagnosis_route": "unknown" if cohort == "2" else "gp_surgery_fast_track",
        "route_rationale": [],
        "confidence": 1.0,
        "notes": [],
        "gap_ftr_dx_days": None,
        "gap_ftr_seen_days": None,
        "gap_dx_treatment_days": None,
        "ftr": {"encounter_date": ftr_date} if ftr_date else None,
        "seen": {"encounter_date": seen_date} if seen_date else None,
        "dx": {"encounter_date": dx_date, "outcome": outcome} if dx_date else None,
        "treatment": None,
        "n_encounters": 1,
        "n_labelled_non_none": 1,
    }


def test_reducer_separates_open_referrals_from_diagnosis_episodes() -> None:
    rows = [
        _row(cohort="1a", site="breast", ftr_date="2025-01-01", dx_date="2025-01-20", outcome="cancer_found"),
        _row(cohort="2", site="lung", ftr_date="2025-02-01"),
    ]

    episodes, open_referrals = reduce_episode_candidates(rows)

    assert [r["cohort"] for r in episodes] == ["1a"]
    assert [r["cohort"] for r in open_referrals] == ["2"]


def test_reducer_collapses_repeated_cohort_three_same_site_diagnoses() -> None:
    rows = [
        _row(cohort="3", site="breast", dx_date="2025-01-20", outcome="cancer_found"),
        _row(cohort="3", site="breast", dx_date="2025-03-20", outcome="cancer_found"),
        _row(cohort="3", site="lung", dx_date="2025-04-20", outcome="cancer_found"),
    ]

    episodes, open_referrals = reduce_episode_candidates(rows)

    assert not open_referrals
    assert [(r["site"], (r["dx"] or {})["encounter_date"]) for r in episodes] == [
        ("breast", "2025-01-20"),
        ("lung", "2025-04-20"),
    ]


def test_reducer_collapses_exact_duplicate_linked_pathways() -> None:
    rows = [
        _row(cohort="1a", site="breast", ftr_date="2025-01-01", dx_date="2025-01-20", outcome="cancer_found"),
        _row(cohort="1a", site="breast", ftr_date="2025-01-01", dx_date="2025-01-20", outcome="cancer_found"),
    ]

    episodes, open_referrals = reduce_episode_candidates(rows)

    assert len(episodes) == 1
    assert not open_referrals


def test_reducer_keeps_one_best_outcome_per_linked_ftr() -> None:
    rows = [
        _row(cohort="1b", site="breast", ftr_date="2025-01-01", dx_date="2025-01-10", outcome=None),
        _row(cohort="1a", site="breast", ftr_date="2025-01-01", dx_date="2025-01-20", outcome="cancer_found"),
        _row(cohort="1a", site="breast", ftr_date="2025-01-01", dx_date="2025-02-20", outcome="cancer_found"),
    ]

    episodes, open_referrals = reduce_episode_candidates(rows)

    assert len(episodes) == 1
    assert episodes[0]["cohort"] == "1a"
    assert (episodes[0]["dx"] or {})["encounter_date"] == "2025-01-20"
    assert not open_referrals


def test_reducer_collapses_near_duplicate_linked_referrals_to_same_dx() -> None:
    rows = [
        _row(cohort="1a", site="breast", ftr_date="2025-01-01", dx_date="2025-01-20", outcome="cancer_found"),
        _row(cohort="1a", site="breast", ftr_date="2025-01-02", dx_date="2025-01-20", outcome="cancer_found"),
    ]

    episodes, open_referrals = reduce_episode_candidates(rows)

    assert len(episodes) == 1
    assert (episodes[0]["ftr"] or {})["encounter_date"] == "2025-01-01"
    assert not open_referrals


def test_reducer_drops_unknown_site_cohort_three_when_specific_same_day_exists() -> None:
    rows = [
        _row(cohort="3", site=None, dx_date="2025-01-20", outcome="cancer_found"),
        _row(cohort="3", site="breast", dx_date="2025-01-20", outcome="cancer_found"),
    ]

    episodes, open_referrals = reduce_episode_candidates(rows)

    assert [(r["site"], (r["dx"] or {})["encounter_date"]) for r in episodes] == [
        ("breast", "2025-01-20")
    ]
    assert not open_referrals


def test_reducer_drops_unknown_site_cohort_three_within_30_days_of_specific() -> None:
    """Unknown-site cohort 3 rows within 30 days of a same-patient specific
    site row are usually the same diagnosis letter parsed twice."""
    rows = [
        _row(cohort="3", site=None, dx_date="2025-02-27", outcome="cancer_found"),
        _row(cohort="3", site="breast", dx_date="2025-03-14", outcome="cancer_found"),
    ]

    episodes, _ = reduce_episode_candidates(rows)

    assert [(r["site"], (r["dx"] or {})["encounter_date"]) for r in episodes] == [
        ("breast", "2025-03-14")
    ]


def test_reducer_keeps_unknown_site_cohort_three_far_from_specific() -> None:
    """Unknown-site rows more than 30 days from any specific-site row are
    likely a different cancer episode and should be retained for review."""
    rows = [
        _row(cohort="3", site=None, dx_date="2024-01-01", outcome="cancer_found"),
        _row(cohort="3", site="breast", dx_date="2025-06-01", outcome="cancer_found"),
    ]

    episodes, _ = reduce_episode_candidates(rows)

    sites = sorted(r["site"] or "unknown" for r in episodes)
    assert sites == ["breast", "unknown"]


def test_reducer_drops_cohort_three_after_linked_same_site_cancer() -> None:
    rows = [
        _row(cohort="1a", site="urological", ftr_date="2025-01-01", dx_date="2025-01-20", outcome="cancer_found"),
        _row(cohort="3", site="urological", dx_date="2025-03-20", outcome="cancer_found"),
        _row(cohort="3", site="lung", dx_date="2025-04-20", outcome="cancer_found"),
    ]

    episodes, open_referrals = reduce_episode_candidates(rows)

    assert [(r["cohort"], r["site"]) for r in episodes] == [
        ("1a", "urological"),
        ("3", "lung"),
    ]
    assert not open_referrals


def test_reducer_collapses_near_day_ftrs_sharing_seen_in() -> None:
    """Same site, FTRs 1 day apart, sharing a Seen-In date collapse to one
    cancer-found row (matches real-world admin re-send pattern)."""
    rows = [
        _row(
            cohort="1a",
            site="breast",
            ftr_date="2025-08-12",
            seen_date="2025-09-11",
            dx_date="2025-09-18",
            outcome="cancer_found",
        ),
        _row(
            cohort="1b",
            site="breast",
            ftr_date="2025-08-13",
            seen_date="2025-09-11",
            dx_date="2025-11-04",
            outcome=None,
        ),
    ]

    episodes, _ = reduce_episode_candidates(rows)

    assert len(episodes) == 1
    assert episodes[0]["cohort"] == "1a"
    assert (episodes[0]["dx"] or {})["outcome"] == "cancer_found"


def test_reducer_collapses_near_day_ftrs_sharing_dx() -> None:
    """Sharing the Dx encounter is also a strong same-pathway signal."""
    rows = [
        _row(
            cohort="1b",
            site="urological",
            ftr_date="2024-07-05",
            dx_date="2024-07-29",
            outcome="cancer_excluded",
        ),
        _row(
            cohort="1a",
            site="urological",
            ftr_date="2024-07-11",
            dx_date="2024-07-29",
            outcome="cancer_found",
        ),
    ]

    episodes, _ = reduce_episode_candidates(rows)

    assert len(episodes) == 1
    assert episodes[0]["cohort"] == "1a"


def test_reducer_does_not_collapse_when_seen_and_dx_differ() -> None:
    """If neither Seen-In nor Dx is shared, leave two episodes (different
    referral cycles for the same site, e.g. recurrent skin cancer)."""
    rows = [
        _row(
            cohort="1a",
            site="skin",
            ftr_date="2025-04-11",
            seen_date="2025-04-30",
            dx_date="2025-07-31",
            outcome="cancer_found",
        ),
        _row(
            cohort="1a",
            site="skin",
            ftr_date="2025-08-22",
            seen_date="2025-08-29",
            dx_date="2025-12-04",
            outcome="cancer_found",
        ),
    ]

    episodes, _ = reduce_episode_candidates(rows)

    assert len(episodes) == 2


def test_reducer_drops_outcomeless_1b_when_found_1a_exists() -> None:
    """1b with outcome=None for the same patient/site as a 1a cancer_found is
    almost always the linker reaching back to an interim/Seen-In encounter."""
    rows = [
        _row(
            cohort="1a",
            site="urological",
            ftr_date="2025-04-11",
            seen_date="2025-05-12",
            dx_date="2025-06-20",
            outcome="cancer_found",
        ),
        _row(
            cohort="1b",
            site="urological",
            ftr_date="2025-04-22",
            seen_date="2025-05-12",
            dx_date="2025-05-12",
            outcome=None,
        ),
    ]

    episodes, _ = reduce_episode_candidates(rows)

    assert len(episodes) == 1
    assert episodes[0]["cohort"] == "1a"


def test_reducer_does_not_drop_cohort3_based_on_other_patients() -> None:
    """Regression: an earlier version dropped a cohort-3 row whenever ANY
    patient had a same-site linked cancer-found episode at an earlier date.
    The drop must only consider the *same patient*."""
    rows = [
        _row(
            patient_id="patient_a",
            cohort="1a",
            site="skin",
            ftr_date="2024-01-01",
            dx_date="2024-02-01",
            outcome="cancer_found",
        ),
        _row(
            patient_id="patient_b",
            cohort="3",
            site="skin",
            dx_date="2025-05-12",
            outcome="cancer_found",
        ),
    ]

    episodes, _ = reduce_episode_candidates(rows)

    pids = sorted({(r["patient_id"], r["cohort"]) for r in episodes})
    assert pids == [("patient_a", "1a"), ("patient_b", "3")]


def test_reducer_keeps_outcomeless_1b_when_no_found_1a() -> None:
    """If there is no cancer_found 1a sibling, keep the outcomeless 1b so the
    reviewer can investigate."""
    rows = [
        _row(
            cohort="1b",
            site="lower_gi",
            ftr_date="2025-04-11",
            dx_date="2025-05-12",
            outcome=None,
        ),
    ]

    episodes, _ = reduce_episode_candidates(rows)

    assert len(episodes) == 1
    assert episodes[0]["cohort"] == "1b"
