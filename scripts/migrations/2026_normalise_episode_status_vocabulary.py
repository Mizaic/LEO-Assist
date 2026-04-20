"""DI-LEO-AI-529: Normalise EpisodeOfCare.status to canonical vocabulary.

Pre-2026 the Haiku Episode Engine writer emitted ``benign_closed`` for
benign-closure episodes, but every dashboard, the canonical DI-085
spec, and the UI vocabulary use ``closed_benign``. The mismatch caused
correctly-closed benign pathways to appear under "active episodes" on
the audit dashboard.

This script rewrites every legacy spelling in
``LEGACY_STATUS_REWRITES`` to its canonical form. It is idempotent: a
second run finds zero rows and is a no-op.

Usage::

    python scripts/migrations/2026_normalise_episode_status_vocabulary.py \
        --commit                 # actually write
    python scripts/migrations/2026_normalise_episode_status_vocabulary.py
                                  # dry-run (default)

The script never deletes data and never touches any other property on
the EpisodeOfCare node.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from libs.episodes.status import LEGACY_STATUS_REWRITES, EpisodeStatus
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger("normalise_episode_status_vocabulary")

_COUNT_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = $legacy
RETURN count(ep) AS n
"""

_REWRITE_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = $legacy
SET ep.status = $canonical,
    ep.updated_at = datetime()
RETURN count(ep) AS n
"""

_INVALID_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status IS NOT NULL
  AND NOT ep.status IN $legal
RETURN ep.status AS status, count(ep) AS n
ORDER BY n DESC
"""


def _legal_statuses() -> list[str]:
    return [s.value for s in EpisodeStatus]


def _count(client: PatientGraphClient, legacy: str) -> int:
    rows = client.run(_COUNT_Q, legacy=legacy) or []
    if not rows:
        return 0
    return int(rows[0].get("n") or 0)


def _rewrite(
    client: PatientGraphClient, legacy: str, canonical: str
) -> int:
    rows = client.run(_REWRITE_Q, legacy=legacy, canonical=canonical) or []
    if not rows:
        return 0
    return int(rows[0].get("n") or 0)


def _list_invalid(client: PatientGraphClient) -> list[dict[str, Any]]:
    rows = client.run(_INVALID_Q, legal=_legal_statuses()) or []
    return [dict(r) for r in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually rewrite (default is dry-run).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    client = PatientGraphClient()

    total_rewrites = 0
    for legacy, canonical in LEGACY_STATUS_REWRITES.items():
        n = _count(client, legacy)
        if n == 0:
            logger.info("[ok] %r: 0 rows -- nothing to do", legacy)
            continue
        if args.commit:
            updated = _rewrite(client, legacy, canonical)
            logger.info(
                "[commit] %r -> %r: rewrote %d rows", legacy, canonical, updated
            )
            total_rewrites += updated
        else:
            logger.info(
                "[dry-run] %r -> %r: would rewrite %d rows",
                legacy,
                canonical,
                n,
            )
            total_rewrites += n

    invalid = _list_invalid(client)
    if invalid:
        logger.warning(
            "[warn] %d EpisodeOfCare nodes carry a status outside the "
            "canonical vocabulary (libs/episodes/status.py):",
            sum(int(r.get("n") or 0) for r in invalid),
        )
        for row in invalid:
            logger.warning("  %r: %d rows", row.get("status"), row.get("n"))
    else:
        logger.info(
            "[ok] every EpisodeOfCare.status value is in the canonical set"
        )

    if not args.commit and total_rewrites:
        logger.info(
            "[dry-run] re-run with --commit to apply %d rewrites", total_rewrites
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
