"""DI-5CAC6D73: Normalise EpisodeOfCare.cancer_type / suspected_site
to the canonical NCDA vocabulary.

Pre-2026 the Haiku Episode Engine segmenter emitted free-text values
for ``suspected_site`` (``breast``, ``upper gi``, ``urological``,
``gastric/oesophageal``, ...). The dashboard taxonomy and NCDA forms
use a fixed list of ~30 cancer types, so the same disease was being
split across multiple chart bars and audits could not be filtered
reliably.

This script rewrites every non-canonical value in the live graph to its
canonical NCDA spelling using
``libs.oncology.cancer_types.normalise_cancer_type``. It is idempotent:
a second run finds zero rows and is a no-op.

Usage::

    python scripts/migrations/2026_normalise_cancer_types.py
                                  # dry-run (default)
    python scripts/migrations/2026_normalise_cancer_types.py --commit
                                  # actually write

The script never deletes data; it only updates the ``cancer_type``,
``suspected_site``, and ``updated_at`` properties on
``EpisodeOfCare`` nodes.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from typing import Any

from libs.neo4j_client.client import PatientGraphClient
from libs.oncology.cancer_types import (
    CANONICAL_CANCER_TYPE_SET,
    normalise_cancer_type,
)

logger = logging.getLogger("normalise_cancer_types")


_LIST_RAW_Q = """
MATCH (ep:EpisodeOfCare)
RETURN ep.episode_id      AS episode_id,
       ep.cancer_type     AS cancer_type,
       ep.suspected_site  AS suspected_site
"""

_REWRITE_Q = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
SET ep.cancer_type     = $cancer_type,
    ep.suspected_site  = $suspected_site,
    ep.updated_at      = datetime()
RETURN ep.episode_id AS episode_id
"""


def _needs_rewrite(value: str | None) -> bool:
    if value is None or value == "":
        return True
    return value not in CANONICAL_CANCER_TYPE_SET


def _classify_rows(rows: list[dict[str, Any]]) -> tuple[list[dict], dict]:
    """Return (pending_updates, summary_counts).

    ``pending_updates`` is a list of dicts ready for ``_REWRITE_Q``.
    ``summary_counts`` is ``{(raw_cancer_type, raw_suspected_site):
    {"canonical": (...), "n": int}}`` for reporting.
    """

    pending: list[dict] = []
    summary: dict[tuple, dict] = defaultdict(
        lambda: {"canonical": None, "n": 0}
    )
    for row in rows:
        raw_ct = row.get("cancer_type")
        raw_site = row.get("suspected_site")
        canonical_ct = normalise_cancer_type(raw_ct)
        canonical_site = normalise_cancer_type(raw_site or raw_ct)
        if not _needs_rewrite(raw_ct) and not _needs_rewrite(raw_site):
            continue
        pending.append(
            {
                "episode_id": row["episode_id"],
                "cancer_type": canonical_ct,
                "suspected_site": canonical_site,
            }
        )
        key = (raw_ct or "<null>", raw_site or "<null>")
        summary[key]["n"] += 1
        summary[key]["canonical"] = (canonical_ct, canonical_site)
    return pending, summary


def _print_summary(summary: dict, commit: bool) -> None:
    if not summary:
        logger.info(
            "[ok] every EpisodeOfCare already carries canonical NCDA values"
        )
        return
    verb = "rewrote" if commit else "would rewrite"
    logger.info(
        "[%s] %d distinct (cancer_type, suspected_site) pairs need normalisation:",
        "commit" if commit else "dry-run",
        len(summary),
    )
    sorted_items = sorted(summary.items(), key=lambda kv: -kv[1]["n"])
    for (raw_ct, raw_site), data in sorted_items:
        canonical_ct, canonical_site = data["canonical"]
        logger.info(
            "  %s (%d): cancer_type %r -> %r ; suspected_site %r -> %r",
            verb,
            data["n"],
            raw_ct,
            canonical_ct,
            raw_site,
            canonical_site,
        )


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

    rows = client.run(_LIST_RAW_Q) or []
    pending, summary = _classify_rows([dict(r) for r in rows])
    _print_summary(summary, args.commit)

    if not pending:
        return 0

    if not args.commit:
        logger.info(
            "[dry-run] re-run with --commit to apply %d episode rewrites",
            len(pending),
        )
        return 0

    written = 0
    for upd in pending:
        result = client.run(_REWRITE_Q, **upd) or []
        if result:
            written += 1
    logger.info("[commit] rewrote %d EpisodeOfCare nodes", written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
