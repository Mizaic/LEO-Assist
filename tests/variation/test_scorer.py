"""Unit tests for libs.variation.scorer.

Atlas trace: VT-3B37176C (acceptance: flags episodes with any milestone
interval above peer P75; suppresses cohorts with sample_size < min).
"""

from __future__ import annotations

from libs.variation.cohort_percentiles import MilestonePercentile
from libs.variation.scorer import (
    MilestoneObservation,
    score_episode,
)


def _pct(from_step, to_step, p25, p50, p75, sample_size=50):
    return MilestonePercentile(
        from_step=from_step,
        to_step=to_step,
        p25=float(p25),
        p50=float(p50),
        p75=float(p75),
        sample_size=sample_size,
    )


def test_scorer_flags_interval_above_p75():
    observations = [
        MilestoneObservation(
            from_step="referral",
            to_step="first_seen",
            interval_days=30.0,
            observed_at="2026-01-02",
        )
    ]
    percentiles = [_pct("referral", "first_seen", 5, 10, 20)]

    result = score_episode(
        episode_id="ep-1",
        community_id=7,
        observations=observations,
        percentiles=percentiles,
    )

    assert result is not None
    assert result.variation_flag is True
    assert result.outlier_steps == ["referral->first_seen"]
    assert result.first_divergence == "referral->first_seen"
    assert result.variation_score == 1.0
    assert result.compared_pairs == 1


def test_scorer_does_not_flag_below_p25():
    # Faster-than-peer is not clinically harmful -> no flag.
    observations = [
        MilestoneObservation(
            from_step="referral",
            to_step="first_seen",
            interval_days=2.0,
            observed_at="2026-01-02",
        )
    ]
    percentiles = [_pct("referral", "first_seen", 5, 10, 20)]

    result = score_episode(
        episode_id="ep-2",
        community_id=7,
        observations=observations,
        percentiles=percentiles,
    )

    assert result is not None
    assert result.variation_flag is False
    assert result.outlier_steps == []
    assert result.first_divergence is None
    assert result.variation_score == 0.0


def test_scorer_skips_small_cohorts():
    # Cohort below min_sample_size should not produce a comparison.
    observations = [
        MilestoneObservation(
            from_step="referral",
            to_step="first_seen",
            interval_days=50.0,
        )
    ]
    percentiles = [_pct("referral", "first_seen", 5, 10, 20, sample_size=3)]

    result = score_episode(
        episode_id="ep-3",
        community_id=7,
        observations=observations,
        percentiles=percentiles,
        min_sample_size=20,
    )

    assert result is None


def test_scorer_first_divergence_is_earliest_outlier():
    observations = [
        MilestoneObservation("referral", "first_seen", 5.0, observed_at="2026-01-01"),
        MilestoneObservation("first_seen", "biopsy", 60.0, observed_at="2026-01-10"),
        MilestoneObservation("biopsy", "mdt", 40.0, observed_at="2026-02-01"),
    ]
    percentiles = [
        _pct("referral", "first_seen", 2, 4, 7),
        _pct("first_seen", "biopsy", 10, 15, 20),
        _pct("biopsy", "mdt", 5, 10, 15),
    ]

    result = score_episode(
        episode_id="ep-4",
        community_id=1,
        observations=observations,
        percentiles=percentiles,
    )

    assert result is not None
    assert result.variation_flag is True
    assert set(result.outlier_steps) == {"first_seen->biopsy", "biopsy->mdt"}
    assert result.first_divergence == "first_seen->biopsy"
    assert result.compared_pairs == 3
    assert result.variation_score == round(2 / 3, 4)


def test_scorer_returns_none_when_no_observations():
    percentiles = [_pct("referral", "first_seen", 5, 10, 20)]
    result = score_episode(
        episode_id="ep-5",
        community_id=7,
        observations=[],
        percentiles=percentiles,
    )
    assert result is None


def test_scorer_returns_none_when_no_matching_pairs():
    # Cohort has no data on the observed pair -> cannot score.
    observations = [
        MilestoneObservation("mdt", "treatment", 50.0),
    ]
    percentiles = [_pct("referral", "first_seen", 5, 10, 20)]
    result = score_episode(
        episode_id="ep-6",
        community_id=7,
        observations=observations,
        percentiles=percentiles,
    )
    assert result is None
