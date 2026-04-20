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

from libs.episodes.status import EpisodeStatus


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
