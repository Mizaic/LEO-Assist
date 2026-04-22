"""Canonical MECE lifecycle classifier for hero-card metrics (DI-105A4EC7).

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Every ``EpisodeOfCare`` falls into exactly one of four lifecycle buckets:

  - ``cancer_excluded``    status = closed_benign (cancer ruled out)
  - ``confirmed_cancer``   has a diagnosis(_confirmed) milestone AND
                            letter_inferred_benign != true
  - ``in_review``          status = review (engine flagged for clinician)
  - ``active``             everything else (in flight, no decision yet)

The priority chain is fixed: closed_benign wins over confirmed_cancer
(a benign closure means the current pathway is clinically resolved as
not-cancer regardless of any historic diagnosis milestone). Confirmed
cancer wins over review (a confirmed cancer flagged for review still
counts as confirmed). Review wins over the catch-all active bucket.

The four-bucket sum equals the total cohort size by construction. The
contract is checked in :mod:`tests.episodes.test_lifecycle` and in
``services/analytics_api/tests/test_audit_summary.py``.

Two surfaces consume this module:

  - ``services/analytics_api/app/routers/audit.py`` -- counts per
    bucket for the dashboard hero cards.
  - ``tests`` -- exhaustive truth-table validation.

The Cypher snippet :data:`HERO_BUCKET_CASE` mirrors the same priority
chain so analytics queries can compute buckets in a single pass without
a round-trip to Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from libs.episodes.status import CLOSED_STATUSES, EpisodeStatus, normalise as normalise_status


class HeroBucket(str, Enum):
    """The four MECE lifecycle buckets shown as dashboard hero cards."""

    ACTIVE = "active"
    IN_REVIEW = "in_review"
    CANCER_EXCLUDED = "cancer_excluded"
    CONFIRMED_CANCER = "confirmed_cancer"


HERO_BUCKETS: tuple[str, ...] = tuple(b.value for b in HeroBucket)


def classify_hero_bucket(
    status: str | None,
    has_diagnosis_milestone: bool,
    letter_inferred_benign: bool = False,
) -> HeroBucket:
    """Return the single MECE bucket an episode falls into.

    Parameters
    ----------
    status:
        Raw ``EpisodeOfCare.status`` value (the canonical spelling -- run
        through ``libs.episodes.status.normalise`` first if you may have
        legacy values).
    has_diagnosis_milestone:
        ``True`` when the episode has at least one
        ``diagnosis`` or ``diagnosis_confirmed`` milestone.
    letter_inferred_benign:
        ``True`` when ``ep.letter_inferred_benign`` is true. Defaults
        to false because most episodes do not set the flag.
    """

    if status == EpisodeStatus.CLOSED_BENIGN.value:
        return HeroBucket.CANCER_EXCLUDED
    if has_diagnosis_milestone and not letter_inferred_benign:
        return HeroBucket.CONFIRMED_CANCER
    if status == EpisodeStatus.REVIEW.value:
        return HeroBucket.IN_REVIEW
    return HeroBucket.ACTIVE


# -- Cypher mirror ---------------------------------------------------------

HERO_BUCKET_CASE: str = (
    "CASE "
    "WHEN {alias}.status = 'closed_benign' THEN 'cancer_excluded' "
    "WHEN {has_diag} AND coalesce({alias}.letter_inferred_benign, false) "
    "  = false THEN 'confirmed_cancer' "
    "WHEN {alias}.status = 'review' THEN 'in_review' "
    "ELSE 'active' "
    "END"
)
"""Cypher CASE snippet that mirrors :func:`classify_hero_bucket`.

Format with two named placeholders: ``alias`` is the bound EpisodeOfCare
variable in the caller's query (typically ``ep``); ``has_diag`` is a
Cypher boolean expression that is true iff the episode has at least one
``diagnosis`` / ``diagnosis_confirmed`` milestone, e.g.::

    EXISTS {{ MATCH (:Encounter)-[r:IS_PART_OF]->(ep)
              WHERE r.milestone_type IN ['diagnosis','diagnosis_confirmed'] }}

Use :func:`build_hero_bucket_case` to get a fully formatted snippet for
the canonical ``ep`` alias and the canonical diagnosis-milestone test.
"""


def build_hero_bucket_case(alias: str = "ep") -> str:
    """Return :data:`HERO_BUCKET_CASE` formatted for ``alias``."""

    has_diag = (
        "EXISTS { "
        f"MATCH (:Encounter)-[__hb_dx:IS_PART_OF]->({alias}) "
        "WHERE __hb_dx.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
        "}"
    )
    return HERO_BUCKET_CASE.format(alias=alias, has_diag=has_diag)


# -- Bucket-flip safety helper --------------------------------------------


@dataclass(frozen=True)
class BucketFlip:
    """Result of comparing two lifecycle states for the same episode.

    Used by:
      - the reconcile API to refuse a write when the proposed actions
        would silently move an episode into another hero bucket without
        explicit reviewer confirmation; and
      - the UI's bucket-flip warning banner so the reviewer is shown
        exactly what is changing before they sign off.
    """

    current_bucket: HeroBucket
    proposed_bucket: HeroBucket
    flips: bool


def would_flip_bucket(
    *,
    current_status: str | None,
    current_has_diagnosis_milestone: bool,
    current_letter_inferred_benign: bool = False,
    proposed_status: str | None,
    proposed_has_diagnosis_milestone: bool,
    proposed_letter_inferred_benign: bool = False,
) -> BucketFlip:
    """Return the current and proposed bucket and whether they differ.

    All three inputs come from the episode under review. ``current_*``
    is the live state read from Neo4j; ``proposed_*`` is the state
    that would result if every reconcile action in the request body
    were applied. The reconcile API uses ``flips`` to decide whether
    to require ``confirm_bucket_flip=True`` from the client.
    """

    current = classify_hero_bucket(
        current_status,
        current_has_diagnosis_milestone,
        current_letter_inferred_benign,
    )
    proposed = classify_hero_bucket(
        proposed_status,
        proposed_has_diagnosis_milestone,
        proposed_letter_inferred_benign,
    )
    return BucketFlip(
        current_bucket=current,
        proposed_bucket=proposed,
        flips=current != proposed,
    )


# ---------------------------------------------------------------------------
# Writer-side parity helpers (DI-C4CEFA32, R-2AA626E7)
#
# Every writer of EpisodeOfCare.status (manual create / update / close /
# merge / review, v2 detector, milestone recompute) MUST go through these
# helpers so the persisted vocabulary stays inside EpisodeStatus and the
# two parallel review-flag fields (needs_review and needs_human_review)
# stay in sync.
# ---------------------------------------------------------------------------


# v2 boundary detector emits its own internal vocabulary
# (open / closed / benign_closure) plus an `intent` flag and a
# `needs_human_review` boolean. This map projects that internal state
# onto the canonical EpisodeStatus.
_V2_BOUNDARY_TO_CANONICAL: dict[tuple[str, bool], str] = {
    ("benign_closure", False): EpisodeStatus.CLOSED_BENIGN.value,
    ("benign_closure", True): EpisodeStatus.CLOSED_BENIGN.value,
    ("closed", False): EpisodeStatus.COMPLETED.value,
    ("closed", True): EpisodeStatus.COMPLETED.value,
    ("open", False): EpisodeStatus.ACTIVE.value,
    ("open", True): EpisodeStatus.REVIEW.value,
}


def canonical_status_from_v2_boundary(
    boundary_status: str,
    needs_human_review: bool,
) -> str:
    """Translate v2 boundary vocabulary to canonical EpisodeStatus.

    Falls back to :data:`EpisodeStatus.REVIEW` for any unknown
    boundary state so an upstream regression cannot persist a
    non-canonical status string. Always returns a member of
    :data:`libs.episodes.status.ENGINE_OUTPUT_STATUSES`.
    """

    raw = (boundary_status or "").strip().lower()
    return _V2_BOUNDARY_TO_CANONICAL.get(
        (raw, bool(needs_human_review)), EpisodeStatus.REVIEW.value
    )


# Statuses that recompute_episode_status is allowed to flip. The full
# vocabulary in libs.episodes.status.EpisodeStatus is wider, but the
# recompute path only ever derives one of these four engine-output
# values; if the current status is anything else (merged, excluded,
# stale_*, etc.) the curator or another sub-system made the call and
# we never overwrite.
RECOMPUTE_RESPECTED_STATUSES: frozenset[str] = frozenset(
    {
        EpisodeStatus.ACTIVE.value,
        EpisodeStatus.REVIEW.value,
        EpisodeStatus.COMPLETED.value,
        EpisodeStatus.CLOSED_BENIGN.value,
    }
)


def is_reviewed(props: dict | None) -> bool:
    """True when the episode has a curator sign-off recorded.

    A curator sign-off is the presence of ``reviewed_at`` (set by
    the mission-control review endpoint). The reviewed status MUST
    be respected by every downstream automated writer.
    """

    if not props:
        return False
    raw = props.get("reviewed_at")
    if raw is None:
        return False
    if isinstance(raw, str):
        return raw.strip() != ""
    return True


def canonical_review_props(reviewer_email: str) -> dict:
    """Property map for marking an EpisodeOfCare as reviewed.

    Writes both legacy ``needs_review`` and canonical
    ``needs_human_review`` fields so the two flags stay in lockstep
    until ``needs_review`` can be retired.
    """

    return {
        "reviewed_by": reviewer_email or "",
        "needs_review": False,
        "needs_human_review": False,
    }


# ---------------------------------------------------------------------------
# Review verdict model (DI-E2498DF6, R-2AA626E7)
#
# A first-class verdict written atomically when a curator signs off on an
# EpisodeOfCare. Closes a real hole in the pre-verdict curator UX where
# "Mark reviewed", "Close pathway" and "Override status" were three
# disconnected actions; reviewers were able to leave an episode with
# reviewed_at set but status unchanged, or status changed but no reviewer
# stamp. Capturing the verdict as a single canonical field eliminates
# the ambiguity and lets the active-learning loop consume the human
# decision unambiguously.
# ---------------------------------------------------------------------------


class ReviewVerdict(str, Enum):
    """What a curator decided when they signed an episode off.

    Every value is ASCII-only and snake_case. Mirrored in TypeScript at
    ``services/ui/src/lib/episodeStatus.ts`` as
    ``REVIEW_VERDICT_VALUES``. The contract test in
    ``tests/contracts/test_episode_status_vocabulary.py`` asserts the two
    stay aligned.
    """

    CONFIRMED_ACTIVE = "confirmed_active"
    CONFIRMED_COMPLETED = "confirmed_completed"
    CONFIRMED_BENIGN = "confirmed_benign"
    CONFIRMED_MERGED = "confirmed_merged"
    REJECTED = "rejected"


REVIEW_VERDICT_VALUES: tuple[str, ...] = tuple(v.value for v in ReviewVerdict)


# Canonical projection from a verdict to the resulting EpisodeStatus.
# The sign-off endpoint writes the mapped status atomically in the same
# Cypher transaction that records the verdict itself, so the graph can
# never end up with a verdict that disagrees with its status.
VERDICT_TO_STATUS: dict[str, str] = {
    ReviewVerdict.CONFIRMED_ACTIVE.value: EpisodeStatus.ACTIVE.value,
    ReviewVerdict.CONFIRMED_COMPLETED.value: EpisodeStatus.COMPLETED.value,
    ReviewVerdict.CONFIRMED_BENIGN.value: EpisodeStatus.CLOSED_BENIGN.value,
    ReviewVerdict.CONFIRMED_MERGED.value: EpisodeStatus.MERGED.value,
    ReviewVerdict.REJECTED.value: EpisodeStatus.EXCLUDED.value,
}


# Inverse map used by the backfill migration to infer a verdict from an
# already-signed-off episode's current status. "active", "review" and
# "in_progress" all collapse to CONFIRMED_ACTIVE because by the time a
# reviewer has stamped reviewed_at the pathway is, by construction, one
# the reviewer has confirmed is still in flight.
STATUS_TO_VERDICT: dict[str, str] = {
    EpisodeStatus.ACTIVE.value: ReviewVerdict.CONFIRMED_ACTIVE.value,
    EpisodeStatus.REVIEW.value: ReviewVerdict.CONFIRMED_ACTIVE.value,
    EpisodeStatus.IN_PROGRESS.value: ReviewVerdict.CONFIRMED_ACTIVE.value,
    EpisodeStatus.COMPLETED.value: ReviewVerdict.CONFIRMED_COMPLETED.value,
    EpisodeStatus.CLOSED.value: ReviewVerdict.CONFIRMED_COMPLETED.value,
    EpisodeStatus.CLOSED_BENIGN.value: ReviewVerdict.CONFIRMED_BENIGN.value,
    EpisodeStatus.MERGED.value: ReviewVerdict.CONFIRMED_MERGED.value,
    EpisodeStatus.EXCLUDED.value: ReviewVerdict.REJECTED.value,
}


def verdict_from_legacy_status(status: str | None) -> tuple[str, bool]:
    """Infer a review verdict from an episode's current status.

    Returns ``(verdict, inferred)`` where ``inferred`` is True when the
    status was not directly in :data:`STATUS_TO_VERDICT` and the caller
    should record a one-line audit_notes entry explaining the fallback.
    Legacy aliases registered in ``LEGACY_STATUS_REWRITES`` (e.g.
    ``in_review`` -> ``review``) are normalised before the lookup so a
    known-good alias counts as a direct map, not an inferred fallback.
    Unknown statuses collapse to ``CONFIRMED_ACTIVE`` so a signed-off
    episode is never left without a verdict.
    """

    if status is None:
        return ReviewVerdict.CONFIRMED_ACTIVE.value, True
    canonical = normalise_status(status) or status
    direct = STATUS_TO_VERDICT.get(canonical)
    if direct is not None:
        return direct, False
    # stale_* closures, closed_related, closed_phantom -> collapse to
    # confirmed_completed so the curator's sign-off is preserved as a
    # closure rather than flipping it open.
    if canonical in CLOSED_STATUSES:
        return ReviewVerdict.CONFIRMED_COMPLETED.value, True
    return ReviewVerdict.CONFIRMED_ACTIVE.value, True


def canonical_signoff_props(
    verdict: str,
    reviewer_email: str,
    audit_notes: str | None = None,
    audit_flag: bool = False,
) -> dict:
    """Property map for an atomic curator sign-off.

    Called by the PATCH /sign-off endpoint and by the backfill
    migration (with ``audit_notes=None`` so it only fills in the
    missing verdict without clobbering existing notes).

    Raises ``ValueError`` when ``verdict`` is not a member of
    :data:`REVIEW_VERDICT_VALUES` so the API layer can return a 400.
    The returned dict carries every field the graph needs to keep
    status, the review-flag pair and the verdict in lockstep. The
    actual ``reviewed_at`` timestamp is written by the SET clause in
    the Cypher (``datetime()``) so a single transaction stamps time
    and verdict together.
    """

    canonical_verdict = (verdict or "").strip()
    if canonical_verdict not in REVIEW_VERDICT_VALUES:
        raise ValueError(
            f"verdict must be one of {list(REVIEW_VERDICT_VALUES)}; "
            f"got {verdict!r}"
        )
    mapped_status = VERDICT_TO_STATUS[canonical_verdict]
    props: dict = {
        "review_verdict": canonical_verdict,
        "status": mapped_status,
        "status_source": "curator_signoff",
        "reviewed_by": reviewer_email or "",
        "needs_review": False,
        "needs_human_review": False,
        "audit_flag": bool(audit_flag),
    }
    if audit_notes is not None:
        props["audit_notes"] = audit_notes
    return props


# Cypher SET fragment used by the /sign-off endpoint. All fields are
# written in one statement so status/verdict/reviewed_at cannot drift.
SIGNOFF_SET_FRAGMENT: str = (
    "SET ep.review_verdict = $review_verdict, "
    "    ep.status = $status, "
    "    ep.status_source = $status_source, "
    "    ep.status_updated_at = datetime(), "
    "    ep.reviewed_by = $reviewed_by, "
    "    ep.reviewed_at = datetime(), "
    "    ep.audit_notes = $audit_notes, "
    "    ep.audit_flag = $audit_flag, "
    "    ep.needs_review = false, "
    "    ep.needs_human_review = false, "
    "    ep.last_updated = datetime() "
)


# Allowed canonical statuses for the "Close pathway" curator action.
# These are the only values the close endpoint will accept on the
# wire. Other vocabulary (merged, stale_*, excluded) belongs to
# specialised endpoints (merge, archive) and is not exposed via the
# generic close button in the UI.
MANUAL_CLOSE_STATUSES: frozenset[str] = frozenset(
    {
        EpisodeStatus.COMPLETED.value,
        EpisodeStatus.CLOSED.value,
        EpisodeStatus.CLOSED_BENIGN.value,
    }
)


def canonical_close_props(
    status: str,
    reason: str,
    actor_email: str = "manual",
) -> dict:
    """Property map for closing an EpisodeOfCare.

    Raises ``ValueError`` if ``status`` is not in
    :data:`MANUAL_CLOSE_STATUSES` so the API layer can return a
    400. Writes both legacy ``needs_review`` and canonical
    ``needs_human_review`` to keep the two flags in lockstep.
    """

    canonical = (status or "").strip().lower()
    if canonical not in MANUAL_CLOSE_STATUSES:
        raise ValueError(
            f"close status must be one of {sorted(MANUAL_CLOSE_STATUSES)}; "
            f"got {status!r}"
        )
    return {
        "status": canonical,
        "agent_reasoning": reason or "",
        "completed_by": actor_email or "manual",
        "needs_review": False,
        "needs_human_review": False,
    }


def canonical_merge_props(
    primary_episode_id: str,
    reasoning: str,
) -> dict:
    """Property map for the secondary side of a merge."""

    return {
        "status": EpisodeStatus.MERGED.value,
        "merged_into": primary_episode_id,
        "merge_reasoning": reasoning or "",
        "needs_review": False,
        "needs_human_review": False,
    }


def respect_reviewed_audit_line(
    target_status: str | None,
    current_status: str | None,
    source: str,
) -> str:
    """One-line audit_notes entry written when recompute is suppressed.

    Used by ``recompute_episode_status`` (and any future automated
    writer) so a clinician auditing the trail can see exactly why the
    status was NOT updated and what the new evidence would have
    flipped it to.
    """

    return (
        f"recompute skipped: reviewed verdict respected; source={source}; "
        f"would_flip {current_status or 'null'} -> "
        f"{target_status or 'null'}"
    )
