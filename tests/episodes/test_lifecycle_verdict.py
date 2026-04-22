"""VT-2487F804: review-verdict capture.

Pins the ReviewVerdict enum, the VERDICT_TO_STATUS projection, and the
canonical_signoff_props() property builder so that every writer of
EpisodeOfCare.review_verdict agrees on the single shape a curator's
sign-off produces.

Traces Atlas:
  DI: DI-E2498DF6
  DO: DO-2A124BA0
  VT: VT-2487F804
  R:  R-2AA626E7
"""

from __future__ import annotations

import pytest

from libs.episodes.lifecycle import (
    REVIEW_VERDICT_VALUES,
    SIGNOFF_SET_FRAGMENT,
    STATUS_TO_VERDICT,
    VERDICT_TO_STATUS,
    ReviewVerdict,
    canonical_signoff_props,
    verdict_from_legacy_status,
)
from libs.episodes.status import EpisodeStatus


# ---------------------------------------------------------------------------
# Enum membership
# ---------------------------------------------------------------------------


def test_review_verdict_members_are_stable_ascii_snake_case() -> None:
    assert set(REVIEW_VERDICT_VALUES) == {
        "confirmed_active",
        "confirmed_completed",
        "confirmed_benign",
        "confirmed_merged",
        "rejected",
    }
    for v in REVIEW_VERDICT_VALUES:
        assert v == v.lower()
        assert v.isascii()


def test_review_verdict_values_property_matches_enum() -> None:
    assert REVIEW_VERDICT_VALUES == tuple(v.value for v in ReviewVerdict)


# ---------------------------------------------------------------------------
# Verdict -> status projection
# ---------------------------------------------------------------------------


def test_verdict_to_status_covers_every_verdict() -> None:
    assert set(VERDICT_TO_STATUS.keys()) == set(REVIEW_VERDICT_VALUES)


def test_verdict_to_status_maps_to_canonical_statuses() -> None:
    canonical = {s.value for s in EpisodeStatus}
    for verdict, status in VERDICT_TO_STATUS.items():
        assert status in canonical, (
            f"verdict {verdict!r} maps to non-canonical status {status!r}"
        )


@pytest.mark.parametrize(
    "verdict, expected_status",
    [
        (ReviewVerdict.CONFIRMED_ACTIVE.value, EpisodeStatus.ACTIVE.value),
        (
            ReviewVerdict.CONFIRMED_COMPLETED.value,
            EpisodeStatus.COMPLETED.value,
        ),
        (
            ReviewVerdict.CONFIRMED_BENIGN.value,
            EpisodeStatus.CLOSED_BENIGN.value,
        ),
        (ReviewVerdict.CONFIRMED_MERGED.value, EpisodeStatus.MERGED.value),
        (ReviewVerdict.REJECTED.value, EpisodeStatus.EXCLUDED.value),
    ],
)
def test_each_verdict_maps_to_expected_status(
    verdict: str, expected_status: str
) -> None:
    assert VERDICT_TO_STATUS[verdict] == expected_status


# ---------------------------------------------------------------------------
# Status -> verdict inference (backfill)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status, expected_verdict, expected_inferred",
    [
        (
            EpisodeStatus.ACTIVE.value,
            ReviewVerdict.CONFIRMED_ACTIVE.value,
            False,
        ),
        (
            EpisodeStatus.REVIEW.value,
            ReviewVerdict.CONFIRMED_ACTIVE.value,
            False,
        ),
        (
            EpisodeStatus.IN_PROGRESS.value,
            ReviewVerdict.CONFIRMED_ACTIVE.value,
            False,
        ),
        (
            EpisodeStatus.COMPLETED.value,
            ReviewVerdict.CONFIRMED_COMPLETED.value,
            False,
        ),
        (
            EpisodeStatus.CLOSED.value,
            ReviewVerdict.CONFIRMED_COMPLETED.value,
            False,
        ),
        (
            EpisodeStatus.CLOSED_BENIGN.value,
            ReviewVerdict.CONFIRMED_BENIGN.value,
            False,
        ),
        (
            EpisodeStatus.MERGED.value,
            ReviewVerdict.CONFIRMED_MERGED.value,
            False,
        ),
        (
            EpisodeStatus.EXCLUDED.value,
            ReviewVerdict.REJECTED.value,
            False,
        ),
    ],
)
def test_verdict_from_known_status_is_direct(
    status: str, expected_verdict: str, expected_inferred: bool
) -> None:
    assert verdict_from_legacy_status(status) == (
        expected_verdict,
        expected_inferred,
    )


def test_verdict_from_stale_closure_collapses_to_completed_with_flag() -> None:
    # Historical stale_* closures are real closures the reviewer
    # signed off on; the backfill preserves the closure by flipping
    # to confirmed_completed and records that it had to infer.
    for stale in (
        EpisodeStatus.STALE_NO_DIAGNOSIS.value,
        EpisodeStatus.STALE_POST_SPECIALIST.value,
        EpisodeStatus.CLOSED_RELATED.value,
        EpisodeStatus.CLOSED_PHANTOM.value,
    ):
        verdict, inferred = verdict_from_legacy_status(stale)
        assert verdict == ReviewVerdict.CONFIRMED_COMPLETED.value
        assert inferred is True


def test_verdict_from_none_status_defaults_to_confirmed_active() -> None:
    verdict, inferred = verdict_from_legacy_status(None)
    assert verdict == ReviewVerdict.CONFIRMED_ACTIVE.value
    assert inferred is True


def test_verdict_from_truly_unknown_status_defaults_to_confirmed_active() -> None:
    verdict, inferred = verdict_from_legacy_status("not_a_status_we_know")
    assert verdict == ReviewVerdict.CONFIRMED_ACTIVE.value
    assert inferred is True


def test_verdict_from_legacy_alias_in_review_is_direct() -> None:
    # in_review is a known alias for review in LEGACY_STATUS_REWRITES;
    # it must count as a direct map (inferred=False) so the migration
    # doesn't add an audit_notes line for known-good legacy spellings.
    verdict, inferred = verdict_from_legacy_status("in_review")
    assert verdict == ReviewVerdict.CONFIRMED_ACTIVE.value
    assert inferred is False


def test_verdict_from_legacy_alias_benign_closed_is_direct() -> None:
    verdict, inferred = verdict_from_legacy_status("benign_closed")
    assert verdict == ReviewVerdict.CONFIRMED_BENIGN.value
    assert inferred is False


def test_status_to_verdict_covers_every_canonical_status() -> None:
    canonical = {s.value for s in EpisodeStatus}
    covered = set(STATUS_TO_VERDICT.keys())
    # Every canonical status is either in STATUS_TO_VERDICT directly
    # or handled by the CLOSED_STATUSES fallback in
    # verdict_from_legacy_status.
    uncovered = canonical - covered
    for s in uncovered:
        verdict, inferred = verdict_from_legacy_status(s)
        assert verdict in REVIEW_VERDICT_VALUES
        assert inferred is True


# ---------------------------------------------------------------------------
# canonical_signoff_props
# ---------------------------------------------------------------------------


def test_signoff_props_contains_every_required_field() -> None:
    props = canonical_signoff_props(
        verdict=ReviewVerdict.CONFIRMED_COMPLETED.value,
        reviewer_email="clinician@leo.example",
        audit_notes="Treatment finished 2025-12-03",
        audit_flag=False,
    )
    assert props == {
        "review_verdict": "confirmed_completed",
        "status": EpisodeStatus.COMPLETED.value,
        "status_source": "curator_signoff",
        "reviewed_by": "clinician@leo.example",
        "needs_review": False,
        "needs_human_review": False,
        "audit_flag": False,
        "audit_notes": "Treatment finished 2025-12-03",
    }


def test_signoff_props_without_notes_omits_audit_notes_key() -> None:
    props = canonical_signoff_props(
        verdict=ReviewVerdict.CONFIRMED_ACTIVE.value,
        reviewer_email="qa@leo.example",
    )
    assert "audit_notes" not in props
    assert props["review_verdict"] == "confirmed_active"
    assert props["status"] == EpisodeStatus.ACTIVE.value
    assert props["audit_flag"] is False


def test_signoff_props_rejects_unknown_verdict() -> None:
    with pytest.raises(ValueError, match="verdict must be one of"):
        canonical_signoff_props(
            verdict="maybe_cancer",
            reviewer_email="x@y.z",
        )


def test_signoff_props_rejects_blank_verdict() -> None:
    with pytest.raises(ValueError):
        canonical_signoff_props(verdict="", reviewer_email="x@y.z")


def test_signoff_props_trims_whitespace_around_verdict() -> None:
    props = canonical_signoff_props(
        verdict="  confirmed_benign  ",
        reviewer_email="x@y.z",
    )
    assert props["review_verdict"] == "confirmed_benign"
    assert props["status"] == EpisodeStatus.CLOSED_BENIGN.value


def test_signoff_props_preserves_audit_flag_when_set() -> None:
    props = canonical_signoff_props(
        verdict=ReviewVerdict.REJECTED.value,
        reviewer_email="x@y.z",
        audit_flag=True,
    )
    assert props["audit_flag"] is True
    assert props["status"] == EpisodeStatus.EXCLUDED.value


def test_signoff_props_blank_email_becomes_empty_string() -> None:
    props = canonical_signoff_props(
        verdict=ReviewVerdict.CONFIRMED_ACTIVE.value,
        reviewer_email="",
    )
    assert props["reviewed_by"] == ""


# ---------------------------------------------------------------------------
# Cypher fragment sanity
# ---------------------------------------------------------------------------


def test_signoff_set_fragment_references_every_prop_key() -> None:
    # Every property the endpoint sends as a parameter must be wired
    # into the SET clause, otherwise a field would silently not get
    # written.
    for param in (
        "$review_verdict",
        "$status",
        "$status_source",
        "$reviewed_by",
        "$audit_notes",
        "$audit_flag",
    ):
        assert param in SIGNOFF_SET_FRAGMENT, (
            f"SIGNOFF_SET_FRAGMENT missing {param}"
        )
    # And it MUST clear both review flags regardless of verdict.
    assert "ep.needs_review = false" in SIGNOFF_SET_FRAGMENT
    assert "ep.needs_human_review = false" in SIGNOFF_SET_FRAGMENT
    # Timestamps are written server-side via datetime(); never trust
    # the caller.
    assert "ep.reviewed_at = datetime()" in SIGNOFF_SET_FRAGMENT
    assert "ep.last_updated = datetime()" in SIGNOFF_SET_FRAGMENT
