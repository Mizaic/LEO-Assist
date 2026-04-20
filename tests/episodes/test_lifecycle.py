"""VT-LEO-AI-529: MECE hero-card lifecycle classifier.

Pins the priority chain in :mod:`libs.episodes.lifecycle` so the
dashboard's four hero cards always sum to the total cohort size and
no episode is double-counted.
"""

from __future__ import annotations

import re

import pytest

from libs.episodes.lifecycle import (
    HERO_BUCKET_CASE,
    HERO_BUCKETS,
    BucketFlip,
    HeroBucket,
    build_hero_bucket_case,
    classify_hero_bucket,
    would_flip_bucket,
)
from libs.episodes.status import EpisodeStatus


# (status, has_diagnosis_milestone, letter_inferred_benign, expected bucket)
_TRUTH_TABLE: tuple[tuple[str | None, bool, bool, HeroBucket], ...] = (
    # closed_benign always wins, even with a diagnosis milestone
    (EpisodeStatus.CLOSED_BENIGN.value, True, False, HeroBucket.CANCER_EXCLUDED),
    (EpisodeStatus.CLOSED_BENIGN.value, False, False, HeroBucket.CANCER_EXCLUDED),
    (EpisodeStatus.CLOSED_BENIGN.value, True, True, HeroBucket.CANCER_EXCLUDED),
    # diagnosis milestone -> confirmed cancer (unless letter inferred benign)
    (EpisodeStatus.ACTIVE.value, True, False, HeroBucket.CONFIRMED_CANCER),
    (EpisodeStatus.COMPLETED.value, True, False, HeroBucket.CONFIRMED_CANCER),
    (EpisodeStatus.REVIEW.value, True, False, HeroBucket.CONFIRMED_CANCER),
    # letter_inferred_benign drops a diagnosis milestone back to its
    # status-based bucket -- never silently classed as confirmed cancer.
    (EpisodeStatus.ACTIVE.value, True, True, HeroBucket.ACTIVE),
    (EpisodeStatus.REVIEW.value, True, True, HeroBucket.IN_REVIEW),
    (EpisodeStatus.COMPLETED.value, True, True, HeroBucket.ACTIVE),
    # status = review with no diagnosis milestone -> in_review
    (EpisodeStatus.REVIEW.value, False, False, HeroBucket.IN_REVIEW),
    # everything else -> active (catch-all)
    (EpisodeStatus.ACTIVE.value, False, False, HeroBucket.ACTIVE),
    (EpisodeStatus.COMPLETED.value, False, False, HeroBucket.ACTIVE),
    (EpisodeStatus.IN_PROGRESS.value, False, False, HeroBucket.ACTIVE),
    (EpisodeStatus.STALE_NO_DIAGNOSIS.value, False, False, HeroBucket.ACTIVE),
    (EpisodeStatus.MERGED.value, False, False, HeroBucket.ACTIVE),
    (None, False, False, HeroBucket.ACTIVE),
    ("garbage_value", False, False, HeroBucket.ACTIVE),
)


@pytest.mark.parametrize(
    "status,has_dx,letter_benign,expected", _TRUTH_TABLE
)
def test_hero_bucket_truth_table(
    status: str | None,
    has_dx: bool,
    letter_benign: bool,
    expected: HeroBucket,
):
    """VT-529-TC-001: every (status, dx, letter_benign) combination in
    the truth table maps to exactly one bucket."""
    assert classify_hero_bucket(status, has_dx, letter_benign) is expected


def test_hero_buckets_are_mece_for_synthetic_cohort():
    """VT-529-TC-002: a synthetic cohort covering every status/diagnosis
    combination produces bucket counts that sum exactly to the cohort
    size (mutually exclusive + collectively exhaustive)."""

    statuses = [s.value for s in EpisodeStatus] + [None, "garbage_value"]
    cohort: list[tuple[str | None, bool, bool]] = []
    for status in statuses:
        for has_dx in (True, False):
            for letter_benign in (True, False):
                cohort.append((status, has_dx, letter_benign))

    counts: dict[HeroBucket, int] = {b: 0 for b in HeroBucket}
    for status, has_dx, letter_benign in cohort:
        counts[classify_hero_bucket(status, has_dx, letter_benign)] += 1

    assert sum(counts.values()) == len(cohort), counts
    assert all(c >= 1 for c in counts.values()), counts


def test_hero_buckets_string_constants_match_enum():
    """VT-529-TC-003: HERO_BUCKETS string tuple stays aligned with the
    HeroBucket enum (no drift between Python labels and the audit
    response field names)."""
    assert HERO_BUCKETS == tuple(b.value for b in HeroBucket)


def test_cypher_snippet_mirrors_priority_chain():
    """VT-529-TC-004: the Cypher CASE snippet checks closed_benign,
    then diagnosis-milestone-with-letter-flag, then review, then falls
    through to active in that exact order."""

    cypher = build_hero_bucket_case("ep")

    closed_benign_pos = cypher.index("closed_benign")
    confirmed_pos = cypher.index("confirmed_cancer")
    review_pos = cypher.index("'review'")
    active_pos = cypher.index("'active'")

    assert closed_benign_pos < confirmed_pos < review_pos < active_pos

    # Letter-inferred-benign clause must guard the confirmed bucket so
    # the Cypher path matches the Python truth table.
    assert "letter_inferred_benign" in cypher
    # Each of the four buckets must be quoted exactly once in the snippet.
    for bucket in HERO_BUCKETS:
        assert cypher.count(f"'{bucket}'") == 1, bucket


def test_cypher_snippet_uses_provided_alias():
    """VT-529-TC-005: alias substitution wires the caller's bound
    variable into the CASE expression and the diagnosis sub-query."""
    snippet = build_hero_bucket_case("episode")
    assert "episode.status" in snippet
    assert "(:Encounter)-[__hb_dx:IS_PART_OF]->(episode)" in snippet
    # The default alias must NOT leak through when a different alias is asked for.
    assert not re.search(r"\bep\.status\b", snippet)


def test_template_only_has_two_named_placeholders():
    """VT-529-TC-006: the raw template exposes exactly the documented
    placeholders so callers cannot accidentally inject extra fields."""
    placeholders = re.findall(r"\{(\w+)\}", HERO_BUCKET_CASE)
    assert sorted(set(placeholders)) == ["alias", "has_diag"]


# -- would_flip_bucket -----------------------------------------------------


def test_would_flip_bucket_returns_dataclass_with_both_buckets() -> None:
    """The reconcile API and the UI banner both consume the structured
    result, so the helper must always return a BucketFlip with the
    current and proposed bucket labels populated."""

    result = would_flip_bucket(
        current_status=EpisodeStatus.REVIEW.value,
        current_has_diagnosis_milestone=False,
        proposed_status=EpisodeStatus.REVIEW.value,
        proposed_has_diagnosis_milestone=False,
    )

    assert isinstance(result, BucketFlip)
    assert result.current_bucket is HeroBucket.IN_REVIEW
    assert result.proposed_bucket is HeroBucket.IN_REVIEW
    assert result.flips is False


def test_would_flip_bucket_review_to_confirmed_cancer() -> None:
    """Adding a confirmed diagnosis milestone moves an in_review episode
    into the confirmed_cancer bucket."""

    result = would_flip_bucket(
        current_status=EpisodeStatus.REVIEW.value,
        current_has_diagnosis_milestone=False,
        proposed_status=EpisodeStatus.REVIEW.value,
        proposed_has_diagnosis_milestone=True,
    )
    assert result.current_bucket is HeroBucket.IN_REVIEW
    assert result.proposed_bucket is HeroBucket.CONFIRMED_CANCER
    assert result.flips is True


def test_would_flip_bucket_review_to_cancer_excluded() -> None:
    result = would_flip_bucket(
        current_status=EpisodeStatus.REVIEW.value,
        current_has_diagnosis_milestone=False,
        proposed_status=EpisodeStatus.CLOSED_BENIGN.value,
        proposed_has_diagnosis_milestone=False,
    )
    assert result.proposed_bucket is HeroBucket.CANCER_EXCLUDED
    assert result.flips is True


def test_would_flip_bucket_confirmed_to_excluded_via_letter_flag() -> None:
    """Setting letter_inferred_benign on an episode that already has a
    diagnosis milestone moves it from confirmed_cancer back into the
    cancer_excluded family, even with the same raw status."""

    result = would_flip_bucket(
        current_status=EpisodeStatus.ACTIVE.value,
        current_has_diagnosis_milestone=True,
        current_letter_inferred_benign=False,
        proposed_status=EpisodeStatus.CLOSED_BENIGN.value,
        proposed_has_diagnosis_milestone=True,
        proposed_letter_inferred_benign=True,
    )
    assert result.current_bucket is HeroBucket.CONFIRMED_CANCER
    assert result.proposed_bucket is HeroBucket.CANCER_EXCLUDED
    assert result.flips is True


def test_would_flip_bucket_active_to_review() -> None:
    result = would_flip_bucket(
        current_status=EpisodeStatus.ACTIVE.value,
        current_has_diagnosis_milestone=False,
        proposed_status=EpisodeStatus.REVIEW.value,
        proposed_has_diagnosis_milestone=False,
    )
    assert result.current_bucket is HeroBucket.ACTIVE
    assert result.proposed_bucket is HeroBucket.IN_REVIEW
    assert result.flips is True


def test_would_flip_bucket_no_change_when_only_internal_state_moves() -> None:
    """Confirming an existing diagnosis without changing the bucket
    inputs must not be reported as a flip."""

    result = would_flip_bucket(
        current_status=EpisodeStatus.REVIEW.value,
        current_has_diagnosis_milestone=True,
        proposed_status=EpisodeStatus.REVIEW.value,
        proposed_has_diagnosis_milestone=True,
    )
    assert result.current_bucket is HeroBucket.CONFIRMED_CANCER
    assert result.proposed_bucket is HeroBucket.CONFIRMED_CANCER
    assert result.flips is False


@pytest.mark.parametrize(
    "current,proposed,should_flip",
    [
        (HeroBucket.ACTIVE, HeroBucket.IN_REVIEW, True),
        (HeroBucket.IN_REVIEW, HeroBucket.CONFIRMED_CANCER, True),
        (HeroBucket.CONFIRMED_CANCER, HeroBucket.CANCER_EXCLUDED, True),
        (HeroBucket.CANCER_EXCLUDED, HeroBucket.CANCER_EXCLUDED, False),
    ],
)
def test_would_flip_bucket_truth_table(
    current: HeroBucket,
    proposed: HeroBucket,
    should_flip: bool,
) -> None:
    """Tests every adjacent transition in the four-bucket lattice."""

    inputs_for = {
        HeroBucket.ACTIVE: (EpisodeStatus.ACTIVE.value, False, False),
        HeroBucket.IN_REVIEW: (EpisodeStatus.REVIEW.value, False, False),
        HeroBucket.CONFIRMED_CANCER: (EpisodeStatus.ACTIVE.value, True, False),
        HeroBucket.CANCER_EXCLUDED: (EpisodeStatus.CLOSED_BENIGN.value, False, False),
    }
    cs, cd, cb = inputs_for[current]
    ps, pd, pb = inputs_for[proposed]

    result = would_flip_bucket(
        current_status=cs,
        current_has_diagnosis_milestone=cd,
        current_letter_inferred_benign=cb,
        proposed_status=ps,
        proposed_has_diagnosis_milestone=pd,
        proposed_letter_inferred_benign=pb,
    )
    assert result.flips is should_flip
    assert result.current_bucket is current
    assert result.proposed_bucket is proposed
