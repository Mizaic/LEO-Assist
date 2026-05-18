"""DI-C4CEFA32: Unify EpisodeOfCare lifecycle across writers.

The pre-Phase-10 graph has three sources of EpisodeOfCare lifecycle
state writing in three different vocabularies:

  - the Haiku Episode Engine writer (canonical EpisodeStatus values)
  - the v2 detector (boundary vocabulary: open / closed / benign_closure)
  - the manual create endpoint (legacy "in_review" default)

It also has two parallel review-flag fields (``needs_review`` and
``needs_human_review``) that can drift -- patches set one but not the
other, so the v2 detector and the dashboards disagree about which
episodes need a clinician.

This migration projects every EpisodeOfCare onto the canonical
:class:`libs.episodes.status.EpisodeStatus` vocabulary AND backfills
both review-flag fields from each other so they are always equal.
The same logic the runtime writers use (DO-C5B5E91E) is applied here
so a re-run of the v2 detector after the migration is a no-op.

Default mode is dry-run: prints a per-bucket diff and exits 0
without writing. Pass ``--commit`` to actually apply.

Usage::

    python scripts/migrations/2026_unify_episode_lifecycle.py
    python scripts/migrations/2026_unify_episode_lifecycle.py --commit

Idempotent: a second run finds zero rows.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from libs.episodes.status import EpisodeStatus
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger("unify_episode_lifecycle")


# ---- status rewrites -----------------------------------------------------
#
# Map every legacy spelling to the canonical EpisodeStatus value. The
# v2 detector wrote `open` / `closed` / `benign_closure` for several
# months before DI-C4CEFA32 landed; the manual create endpoint wrote
# `in_review`. Everything else is already canonical.
_STATUS_REWRITES: dict[str, str] = {
    "in_review": EpisodeStatus.REVIEW.value,
    "open": EpisodeStatus.ACTIVE.value,
    "closed": EpisodeStatus.COMPLETED.value,
    "benign_closure": EpisodeStatus.CLOSED_BENIGN.value,
    # The legacy benign-closure spelling already covered by the
    # earlier 2026_normalise_episode_status_vocabulary migration; we
    # include it here so this script is safe to run on a graph that
    # was never migrated by the earlier script.
    "benign_closed": EpisodeStatus.CLOSED_BENIGN.value,
}


_COUNT_STATUS_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = $legacy
RETURN count(ep) AS n
"""

_REWRITE_STATUS_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = $legacy
  AND ep.reviewed_at IS NULL
SET ep.status = $canonical,
    ep.status_source = coalesce(
        ep.status_source, 'unify_lifecycle_migration'
    ),
    ep.last_updated = datetime()
RETURN count(ep) AS n
"""

_REWRITE_STATUS_REVIEWED_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = $legacy
  AND ep.reviewed_at IS NOT NULL
RETURN count(ep) AS n
"""


# ---- review-flag backfill ------------------------------------------------
#
# Pull both fields into lockstep. Logical OR: if either field said the
# episode needs review, the unified state needs review.

_FLAG_DRIFT_Q = """
MATCH (ep:EpisodeOfCare)
WHERE coalesce(ep.needs_review, false)
   <> coalesce(ep.needs_human_review, false)
RETURN count(ep) AS n
"""

_FLAG_BACKFILL_Q = """
MATCH (ep:EpisodeOfCare)
WHERE coalesce(ep.needs_review, false)
   <> coalesce(ep.needs_human_review, false)
WITH ep,
     coalesce(ep.needs_review, false)
        OR coalesce(ep.needs_human_review, false) AS unified
SET ep.needs_review = unified,
    ep.needs_human_review = unified,
    ep.last_updated = datetime()
RETURN count(ep) AS n
"""


# ---- residual invalid statuses ------------------------------------------

_INVALID_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status IS NOT NULL
  AND NOT ep.status IN $legal
RETURN ep.status AS status, count(ep) AS n
ORDER BY n DESC
"""


def _legal_statuses() -> list[str]:
    return [s.value for s in EpisodeStatus]


def _scalar(rows: list[dict[str, Any]] | None, key: str) -> int:
    if not rows:
        return 0
    return int(rows[0].get(key) or 0)


def _rewrite_statuses(
    client: PatientGraphClient, commit: bool
) -> tuple[int, int]:
    total_changes = 0
    skipped_reviewed = 0
    for legacy, canonical in _STATUS_REWRITES.items():
        n = _scalar(client.run(_COUNT_STATUS_Q, legacy=legacy), "n")
        if n == 0:
            continue
        reviewed = _scalar(
            client.run(_REWRITE_STATUS_REVIEWED_Q, legacy=legacy), "n"
        )
        skipped_reviewed += reviewed
        eligible = n - reviewed
        if commit:
            updated = _scalar(
                client.run(
                    _REWRITE_STATUS_Q, legacy=legacy, canonical=canonical
                ),
                "n",
            )
            logger.info(
                "[commit] status %r -> %r: rewrote %d rows "
                "(skipped %d reviewed)",
                legacy,
                canonical,
                updated,
                reviewed,
            )
            total_changes += updated
        else:
            logger.info(
                "[dry-run] status %r -> %r: would rewrite %d rows "
                "(skipped %d reviewed)",
                legacy,
                canonical,
                eligible,
                reviewed,
            )
            total_changes += eligible
    return total_changes, skipped_reviewed


def _backfill_review_flags(
    client: PatientGraphClient, commit: bool
) -> int:
    n = _scalar(client.run(_FLAG_DRIFT_Q), "n")
    if n == 0:
        logger.info("[ok] needs_review / needs_human_review already in lockstep")
        return 0
    if commit:
        updated = _scalar(client.run(_FLAG_BACKFILL_Q), "n")
        logger.info(
            "[commit] review-flag drift: backfilled %d rows", updated
        )
        return updated
    logger.info(
        "[dry-run] review-flag drift: would backfill %d rows", n
    )
    return n


def _report_invalid(client: PatientGraphClient) -> int:
    rows = client.run(_INVALID_Q, legal=_legal_statuses()) or []
    if not rows:
        logger.info(
            "[ok] every EpisodeOfCare.status value is in the canonical set"
        )
        return 0
    total = sum(int(r.get("n") or 0) for r in rows)
    logger.warning(
        "[warn] %d EpisodeOfCare nodes carry a status outside the "
        "canonical vocabulary (libs/episodes/status.py):",
        total,
    )
    for row in rows:
        logger.warning("  %r: %d rows", row.get("status"), row.get("n"))
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually apply changes (default is dry-run).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    client = PatientGraphClient()

    status_changes, reviewed_skips = _rewrite_statuses(client, args.commit)
    flag_changes = _backfill_review_flags(client, args.commit)
    residual = _report_invalid(client)

    total = status_changes + flag_changes
    if not args.commit and total:
        logger.info(
            "[dry-run] re-run with --commit to apply %d total changes "
            "(status=%d, review_flags=%d; %d reviewed-status rows skipped)",
            total,
            status_changes,
            flag_changes,
            reviewed_skips,
        )
    elif args.commit:
        logger.info(
            "[done] applied %d total changes (status=%d, review_flags=%d; "
            "%d reviewed-status rows skipped, %d residual invalid statuses)",
            total,
            status_changes,
            flag_changes,
            reviewed_skips,
            residual,
        )
    else:
        logger.info("[ok] no changes required")
    return 0


if __name__ == "__main__":
    sys.exit(main())
