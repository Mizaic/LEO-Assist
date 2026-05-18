"""Canonical EpisodeOfCare status vocabulary (DI-LEO-AI-529).

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Single source of truth for every status string an EpisodeOfCare node may
carry. Importers MUST NOT reintroduce string literals like "active",
"closed_benign", "completed" etc. anywhere in production code -- always
import from this module so the writer (producer) and the dashboard /
mission-control / UI (consumers) cannot drift.

Mirrored in TypeScript at ``services/ui/src/lib/episodeStatus.ts``. The
contract test ``tests/contracts/test_episode_status_vocabulary.py``
parses the TS file and asserts the two stay aligned.

Vocabulary
----------
ENGINE OUTPUT (statuses the Haiku Episode Engine writer is allowed to emit
for a freshly written EpisodeOfCare):

    ACTIVE             -- cancer / multi-site episode still in flight
    REVIEW             -- engine flagged needs_human_review
    COMPLETED          -- treatment_completed milestone present
    CLOSED_BENIGN      -- engine classified the episode as benign

LEGACY-RULE OUTPUT (statuses that may exist on EpisodeOfCare nodes written
by the now-deleted rule-based detector and that the dashboard MUST still
treat as "closed" so historical pathways do not silently re-open):

    MERGED                -- duplicate pathway absorbed into another
    CLOSED_RELATED        -- duplicate pathway closed
    CLOSED_PHANTOM        -- removed because no clinical evidence
    STALE_NO_DIAGNOSIS    -- timed out before diagnosis
    STALE_POST_SPECIALIST -- specialist seen, no diagnosis recorded
    CLOSED                -- generic closed (very old data)
    EXCLUDED              -- excluded from cohort

LEGACY-RULE OPEN (still in flight under the legacy schema):

    IN_PROGRESS           -- still being investigated

If you need a brand-new status value, add it here FIRST, run the contract
test, then update the TS mirror.
"""

from __future__ import annotations

from enum import Enum


class EpisodeStatus(str, Enum):
    """Every legal value of ``EpisodeOfCare.status`` in the patient graph."""

    ACTIVE = "active"
    REVIEW = "review"
    COMPLETED = "completed"
    CLOSED_BENIGN = "closed_benign"

    MERGED = "merged"
    CLOSED_RELATED = "closed_related"
    CLOSED_PHANTOM = "closed_phantom"
    STALE_NO_DIAGNOSIS = "stale_no_diagnosis"
    STALE_POST_SPECIALIST = "stale_post_specialist"
    CLOSED = "closed"
    EXCLUDED = "excluded"

    IN_PROGRESS = "in_progress"


# -- Producer contract -----------------------------------------------------

ENGINE_OUTPUT_STATUSES: frozenset[str] = frozenset(
    {
        EpisodeStatus.ACTIVE.value,
        EpisodeStatus.REVIEW.value,
        EpisodeStatus.COMPLETED.value,
        EpisodeStatus.CLOSED_BENIGN.value,
    }
)
"""The only statuses the Haiku Episode Engine writer is allowed to emit.

Anything outside this set in a freshly written episode is a writer bug.
"""


# -- Consumer contracts ----------------------------------------------------

OPEN_STATUSES: frozenset[str] = frozenset(
    {
        EpisodeStatus.ACTIVE.value,
        EpisodeStatus.REVIEW.value,
        EpisodeStatus.IN_PROGRESS.value,
    }
)
"""Statuses considered 'still in flight' by every dashboard.

A patient with at least one open EpisodeOfCare is on an active pathway.
"""

CLOSED_STATUSES: frozenset[str] = frozenset(
    {
        EpisodeStatus.COMPLETED.value,
        EpisodeStatus.CLOSED.value,
        EpisodeStatus.CLOSED_BENIGN.value,
        EpisodeStatus.MERGED.value,
        EpisodeStatus.EXCLUDED.value,
        EpisodeStatus.CLOSED_RELATED.value,
        EpisodeStatus.CLOSED_PHANTOM.value,
        EpisodeStatus.STALE_NO_DIAGNOSIS.value,
        EpisodeStatus.STALE_POST_SPECIALIST.value,
    }
)
"""Statuses the audit/dashboard treat as 'no longer active'.

Used by ``services/analytics_api/app/routers/audit.py`` to compute the
'active episodes' headline. Anything in this set must NOT be counted as
active even if it appears under a different spelling -- always normalise
through this set.
"""

# Closure reasons surfaced as filter chips and on the timeline. A subset
# of CLOSED_STATUSES that have a meaningful clinical narrative (we hide
# admin-only closures like merged/closed_phantom from reviewers).
CLOSURE_REASON_STATUSES: tuple[str, ...] = (
    EpisodeStatus.CLOSED_BENIGN.value,
    EpisodeStatus.STALE_NO_DIAGNOSIS.value,
    EpisodeStatus.STALE_POST_SPECIALIST.value,
    EpisodeStatus.CLOSED_RELATED.value,
)

# Statuses always hidden from the patient list (admin/cleanup only).
ALWAYS_EXCLUDE_STATUSES: tuple[str, ...] = (
    EpisodeStatus.MERGED.value,
    EpisodeStatus.CLOSED_PHANTOM.value,
)


# -- Migration: legacy aliases ---------------------------------------------

LEGACY_STATUS_REWRITES: dict[str, str] = {
    # Pre-2026 the Haiku writer emitted "benign_closed" but every
    # downstream dashboard, the canonical DI-085 spec, and the UI
    # vocabulary use "closed_benign". This map is consulted by the
    # idempotent migration in
    # scripts/migrations/2026_normalise_episode_status_vocabulary.py.
    "benign_closed": EpisodeStatus.CLOSED_BENIGN.value,
}


def normalise(raw: str | None) -> str | None:
    """Return the canonical spelling for a legacy status value.

    Pure function, safe to call on every read path. Returns ``None``
    unchanged so callers can preserve missing-status semantics.
    """

    if raw is None:
        return None
    return LEGACY_STATUS_REWRITES.get(raw, raw)


def is_open(raw: str | None) -> bool:
    """True when an episode is still in flight."""
    return normalise(raw) in OPEN_STATUSES


def is_closed(raw: str | None) -> bool:
    """True when an episode is no longer active."""
    return normalise(raw) in CLOSED_STATUSES
