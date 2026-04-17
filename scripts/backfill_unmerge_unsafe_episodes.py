"""Backfill: unmerge EpisodeOfCare clusters that violate the new
multi-distinct-cancer-type safety guard introduced in DI-LEO-AI-137 /
R-LEO-AI-097.

Background
----------
The original ``pick_evidence_winner`` would, when no diagnosis-text
evidence existed AND multiple distinct known cancer_types were present
in a cluster, fall back to alphabetical tiebreak ("breast" < "melanoma"
won by name). That violated the DI-LEO-AI-137 safety criterion ("when
no deterministic winner exists, the merge is skipped"). The fix in
``libs/episodes/duplicate_resolver.py`` now skips such clusters.

This script reverses the historical bad merges so they match the new
behaviour. It is generic -- it does NOT operate on a specific patient
list. For every ``EpisodeOfCare`` with ``status='merged'``, the script:

1. Fetches the primary + dup as a 2-record cluster.
2. Re-runs ``pick_evidence_winner`` with the new logic.
3. If the new logic would NOT merge (returns None) -> the merge is
   reverted: the dup's status, merged_into, merged_at, merge_reasoning
   are cleared. IS_PART_OF edges that were migrated by MOVE_LINKS_Q
   cannot be reliably reattributed without re-running the episode
   builder, so the dup will end up empty until the next analysis pass
   reprocesses the patient. That is the correct fail-safe state.

Usage
-----
    python scripts/backfill_unmerge_unsafe_episodes.py --dry-run
    python scripts/backfill_unmerge_unsafe_episodes.py --apply

The script is idempotent: re-running it after --apply finds no further
unsafe merges to revert.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

from libs.episodes.duplicate_resolver import (  # noqa: E402
    EpisodeRecord,
    pick_evidence_winner,
)
from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_unmerge")


_FETCH_MERGED_PAIRS = """
MATCH (dup:EpisodeOfCare {status: 'merged'})
MATCH (primary:EpisodeOfCare {episode_id: dup.merged_into})
OPTIONAL MATCH (primary)<-[:HAS_EPISODE_OF_CARE]-(p:Patient)
RETURN
    toString(p.id)                               AS patient_id,
    toString(dup.episode_id)                     AS dup_id,
    toString(dup.cancer_type)                    AS dup_cancer_type,
    toString(dup.referral_date)                  AS dup_referral_date,
    toString(coalesce(dup.end_date,
                      dup.referral_date))        AS dup_end_date,
    toString(primary.episode_id)                 AS primary_id,
    toString(primary.cancer_type)                AS primary_cancer_type,
    toString(primary.referral_date)              AS primary_referral_date,
    toString(coalesce(primary.end_date,
                      primary.referral_date))    AS primary_end_date,
    toString(coalesce(dup.merge_reasoning, '')) AS old_reasoning
"""


_FETCH_DIAGNOSIS_TEXTS = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})<-[:IS_PART_OF]-(e:Encounter)
WHERE e.text IS NOT NULL AND trim(toString(e.text)) <> ''
RETURN collect(toString(e.text))[..50] AS texts
"""


_REVERT_MERGE = """
MATCH (dup:EpisodeOfCare {episode_id: $dup_id, status: 'merged'})
SET dup.status          = 'reopened_for_rebuild',
    dup.merged_into     = NULL,
    dup.merged_at       = NULL,
    dup.merge_reasoning = NULL,
    dup.unmerged_reason = $reason,
    dup.unmerged_at     = datetime()
RETURN dup.episode_id AS episode_id
"""


def _parse_date(value: str | None) -> date | None:
    if not value or value in ("None", "null", ""):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _build_record(
    episode_id: str,
    cancer_type: str,
    referral: str | None,
    end: str | None,
    texts: list[str],
) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id=episode_id,
        cancer_type=cancer_type or "unknown",
        referral_date=_parse_date(referral),
        end_date=_parse_date(end),
        status="completed",
        diagnosis_texts=texts,
        treatment_count=0,
    )


def _gather_texts(client: PatientGraphClient, episode_id: str) -> list[str]:
    with client.session() as session:
        rec = session.run(_FETCH_DIAGNOSIS_TEXTS, episode_id=episode_id).single()
    return list((rec or {}).get("texts") or [])


def _evaluate_merged_pair(
    client: PatientGraphClient, row: dict[str, Any]
) -> tuple[bool, str]:
    """Return (should_unmerge, reason). Re-runs pick_evidence_winner."""
    primary_texts = _gather_texts(client, row["primary_id"])
    dup_texts = _gather_texts(client, row["dup_id"])
    primary = _build_record(
        row["primary_id"],
        row["primary_cancer_type"],
        row["primary_referral_date"],
        row["primary_end_date"],
        primary_texts,
    )
    dup = _build_record(
        row["dup_id"],
        row["dup_cancer_type"],
        row["dup_referral_date"],
        row["dup_end_date"],
        dup_texts,
    )
    decision = pick_evidence_winner([primary, dup])
    if decision is None:
        reason = (
            f"DI-LEO-AI-137/R-LEO-AI-097 unmerge: cluster of "
            f"primary={row['primary_id']} ({row['primary_cancer_type']}) + "
            f"dup={row['dup_id']} ({row['dup_cancer_type']}) no longer "
            f"satisfies deterministic-winner rule under new pick_evidence_winner."
        )
        return True, reason
    return False, ""


def _revert_one(
    client: PatientGraphClient,
    dup_id: str,
    reason: str,
    apply_changes: bool,
) -> None:
    if not apply_changes:
        return
    with client.session() as session:
        session.run(_REVERT_MERGE, dup_id=dup_id, reason=reason)


def _summarise(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for r in rows:
        key = f"{r['primary_cancer_type']}<-{r['dup_cancer_type']}"
        summary[key] = summary.get(key, 0) + 1
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be unmerged without writing.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually revert unsafe merges in Neo4j.",
    )
    args = parser.parse_args()
    if args.dry_run == args.apply:
        parser.error("Specify exactly one of --dry-run or --apply.")

    client = PatientGraphClient()
    with client.session() as session:
        merged_rows = list(session.run(_FETCH_MERGED_PAIRS))
    logger.info("Fetched %d merged episode pairs.", len(merged_rows))

    to_unmerge: list[dict[str, Any]] = []
    for raw in merged_rows:
        row = dict(raw)
        try:
            should_unmerge, reason = _evaluate_merged_pair(client, row)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to evaluate dup=%s: %s", row.get("dup_id"), exc)
            continue
        if should_unmerge:
            row["unmerge_reason"] = reason
            to_unmerge.append(row)

    logger.info(
        "Identified %d / %d merges that violate new safety rule.",
        len(to_unmerge),
        len(merged_rows),
    )
    summary = _summarise(to_unmerge)
    for key, n in sorted(summary.items(), key=lambda kv: -kv[1]):
        logger.info("  %-40s %d", key, n)

    if args.dry_run:
        logger.info("Dry run -- no writes performed.")
        return 0

    for row in to_unmerge:
        _revert_one(client, row["dup_id"], row["unmerge_reason"], apply_changes=True)
    logger.info("Reverted %d merges.", len(to_unmerge))
    return 0


if __name__ == "__main__":
    sys.exit(main())
