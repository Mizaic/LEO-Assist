"""DI-E2498DF6: backfill EpisodeOfCare.review_verdict.

Every EpisodeOfCare signed off before the sign-off endpoint landed
has ``reviewed_at IS NOT NULL`` but no ``review_verdict``. This
script infers the verdict from the current ``status`` and writes it
in a single Cypher pass, keeping the reviewer's intent intact for
the active-learning loop.

Inference rule (libs.episodes.lifecycle.verdict_from_legacy_status):

  closed_benign                 -> confirmed_benign
  completed | closed            -> confirmed_completed
  merged                        -> confirmed_merged
  excluded                      -> rejected
  active | review | in_progress -> confirmed_active
  closed_related | closed_phantom | stale_no_diagnosis
    | stale_post_specialist     -> confirmed_completed (audit_notes appended)
  anything else or NULL         -> confirmed_active   (audit_notes appended)

Default is dry-run: prints a per-status breakdown and exits 0
without writing. Pass ``--commit`` to apply. Idempotent: a second
run finds zero rows.

Usage::

    python scripts/migrations/2026_backfill_review_verdict.py
    python scripts/migrations/2026_backfill_review_verdict.py --commit

Atlas trace: DI-E2498DF6, DO-2A124BA0, VT-2487F804, R-2AA626E7.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from libs.episodes.lifecycle import (
    REVIEW_VERDICT_VALUES,
    verdict_from_legacy_status,
)
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger("backfill_review_verdict")


_SCAN_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.reviewed_at IS NOT NULL
  AND (ep.review_verdict IS NULL OR ep.review_verdict = '')
WITH coalesce(ep.status, '__null__') AS status, count(ep) AS n
RETURN status AS status, n AS n
ORDER BY n DESC
"""


_WRITE_DIRECT_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.reviewed_at IS NOT NULL
  AND (ep.review_verdict IS NULL OR ep.review_verdict = '')
  AND coalesce(ep.status, '__null__') = $status
SET ep.review_verdict = $verdict,
    ep.status_source = coalesce(
        ep.status_source, 'verdict_backfill_migration'
    ),
    ep.last_updated = datetime()
RETURN count(ep) AS n
"""


_WRITE_INFERRED_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.reviewed_at IS NOT NULL
  AND (ep.review_verdict IS NULL OR ep.review_verdict = '')
  AND coalesce(ep.status, '__null__') = $status
SET ep.review_verdict = $verdict,
    ep.status_source = coalesce(
        ep.status_source, 'verdict_backfill_migration'
    ),
    ep.audit_notes = coalesce(ep.audit_notes, '') + $audit_suffix,
    ep.last_updated = datetime()
RETURN count(ep) AS n
"""


def _scalar(rows: list[dict[str, Any]] | None, key: str) -> int:
    if not rows:
        return 0
    return int(rows[0].get(key) or 0)


def _audit_suffix(status: str | None) -> str:
    label = status if status and status != "__null__" else "null"
    return f"\nverdict backfilled from legacy status {label}"


def _process_status_group(
    client: PatientGraphClient,
    status_sentinel: str,
    count: int,
    commit: bool,
) -> int:
    """Backfill verdict for a single (status, count) group."""

    real_status = None if status_sentinel == "__null__" else status_sentinel
    verdict, inferred = verdict_from_legacy_status(real_status)
    if verdict not in REVIEW_VERDICT_VALUES:  # defensive
        logger.warning(
            "[skip] status %r mapped to unknown verdict %r",
            real_status,
            verdict,
        )
        return 0

    label = real_status if real_status is not None else "null"
    if not commit:
        logger.info(
            "[dry-run] status=%s (n=%d) -> verdict=%s %s",
            label,
            count,
            verdict,
            "(inferred)" if inferred else "(direct)",
        )
        return count

    if inferred:
        written = _scalar(
            client.run(
                _WRITE_INFERRED_Q,
                status=status_sentinel,
                verdict=verdict,
                audit_suffix=_audit_suffix(real_status),
            ),
            "n",
        )
    else:
        written = _scalar(
            client.run(
                _WRITE_DIRECT_Q,
                status=status_sentinel,
                verdict=verdict,
            ),
            "n",
        )

    logger.info(
        "[commit] status=%s (n=%d) -> verdict=%s: wrote %d %s",
        label,
        count,
        verdict,
        written,
        "(inferred)" if inferred else "(direct)",
    )
    return written


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

    rows = client.run(_SCAN_Q) or []
    if not rows:
        logger.info(
            "[ok] every signed-off EpisodeOfCare already has a review_verdict"
        )
        return 0

    total = 0
    for row in rows:
        status_sentinel = str(row.get("status") or "__null__")
        n = int(row.get("n") or 0)
        total += _process_status_group(client, status_sentinel, n, args.commit)

    if not args.commit:
        logger.info(
            "[dry-run] re-run with --commit to apply %d total backfill(s)",
            total,
        )
    else:
        logger.info("[done] backfilled %d review_verdict value(s)", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
