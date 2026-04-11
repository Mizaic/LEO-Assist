"""Delete patient-graph Encounter nodes outside the 2024-01-01 to 2025-12-31 window.

Retained: encounters whose date falls on or between 2024-01-01 and 2025-12-31 (inclusive).
Deleted:  encounters with a non-null date strictly before 2024-01-01 or strictly after
          2025-12-31.
Skipped:  encounters where e.date IS NULL (reported in dry-run; never deleted).

Deletion is performed in dependency order so no orphan rows are left behind:

  1. EncounterCandidate subgraph (ReviewTask, Approval, Change nodes).
  2. TrainingLabel and linked CodingReview nodes.
  3. DOCUMENTS relationships on the target Encounter nodes.
  4. IS_PART_OF relationships (removed automatically by DETACH DELETE in step 5).
  5. Encounter nodes + HAS_ENCOUNTER relationships (DETACH DELETE, batched).
  6. Patient shortcut hygiene: patient-to-concept relationships no longer backed
     by any remaining Encounter DOCUMENTS.

EpisodeOfCare list-property consistency
---------------------------------------
DETACH DELETE removes IS_PART_OF edges. However EpisodeOfCare nodes may still
carry deleted encounter IDs in list properties such as referral_encounter_ids,
diagnosis_encounter_id, and exclusion_encounter_id. After running this script
you should re-run scripts/remediate_episodes.py (or the analysis-worker episode
build) for the affected patient IDs, or use the advisory Cypher below in a
separate maintenance pass.

Knowledge-graph CodingDecision rows
-------------------------------------
CodingDecision nodes live in the knowledge graph (KNOWLEDGE_GRAPH_NEO4J_URI)
and carry encounter_id. This script deletes them for all removed encounters by
running batched MATCH / DETACH DELETE against KnowledgeGraphClient.

Usage
-----
  # Dry-run (default): shows what would be deleted, no changes made.
  python scripts/investigations/_delete_out_of_window_encounters.py

  # Apply:
  python scripts/investigations/_delete_out_of_window_encounters.py --apply

  # Apply and export deleted encounter IDs for audit trail:
  python scripts/investigations/_delete_out_of_window_encounters.py --apply --export-ids deleted_ids.jsonl

  # Override the window (ISO dates, inclusive on both ends):
  python scripts/investigations/_delete_out_of_window_encounters.py --keep-from 2024-01-01 --keep-to 2025-12-31
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# -- Constants ---------------------------------------------------------------

DEFAULT_KEEP_FROM = "2024-01-01"
DEFAULT_KEEP_TO = "2025-12-31"
BATCH_SIZE = 500

# -- Cypher: audit / dry-run -------------------------------------------------

_Q_COUNT_TARGET = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.date IS NOT NULL
  AND (date(e.date) < date($keep_from) OR date(e.date) > date($keep_to))
RETURN count(DISTINCT e) AS encounter_count, count(DISTINCT p) AS patient_count
"""

_Q_COUNT_NULL_DATE = """
MATCH (e:Encounter)
WHERE e.date IS NULL
RETURN count(e) AS null_date_count
"""

_Q_SAMPLE_NULL_DATE = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.date IS NULL
RETURN toString(e.id) AS encounter_id, toString(p.id) AS patient_id
LIMIT 5
"""

_Q_COUNT_CANDIDATES = """
MATCH (c:EncounterCandidate)
WHERE c.encounter_id IN $enc_ids
RETURN count(c) AS candidate_count
"""

_Q_COUNT_TRAINING_LABELS = """
MATCH (t:TrainingLabel)
WHERE t.encounter_id IN $enc_ids
RETURN count(t) AS label_count
"""

_Q_COUNT_CODING_REVIEWS = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE t.encounter_id IN $enc_ids
RETURN count(cr) AS review_count
"""

_Q_COUNT_IS_PART_OF = """
MATCH (e:Encounter)-[:IS_PART_OF]->()
WHERE e.date IS NOT NULL
  AND (date(e.date) < date($keep_from) OR date(e.date) > date($keep_to))
RETURN count(*) AS is_part_of_count
"""

_Q_COUNT_ALERTS = """
MATCH (a:SafetyNetAlert)-[:TRIGGERED_AT]->(e:Encounter)
WHERE e.date IS NOT NULL
  AND (date(e.date) < date($keep_from) OR date(e.date) > date($keep_to))
RETURN count(a) AS alert_count
"""

_Q_COUNT_DOCUMENTS = """
MATCH (e:Encounter)-[:DOCUMENTS]->()
WHERE e.date IS NOT NULL
  AND (date(e.date) < date($keep_from) OR date(e.date) > date($keep_to))
RETURN count(*) AS doc_count
"""

# -- Cypher: collect target IDs in pages -------------------------------------

_Q_PAGE_ENCOUNTER_IDS = """
MATCH (e:Encounter)
WHERE e.date IS NOT NULL
  AND (date(e.date) < date($keep_from) OR date(e.date) > date($keep_to))
RETURN toString(e.id) AS encounter_id
ORDER BY e.id
SKIP $skip LIMIT $limit
"""

# -- Cypher: deletion steps --------------------------------------------------

_Q_DELETE_CANDIDATES = """
UNWIND $enc_ids AS eid
MATCH (c:EncounterCandidate)
WHERE toString(c.encounter_id) = eid
OPTIONAL MATCH (c)-[:HAS_TASK]->(t:ReviewTask)
OPTIONAL MATCH (t)-[:HAS_APPROVAL]->(a:Approval)
OPTIONAL MATCH (c)-[:HAS_CHANGE]->(chg:Change)
WITH collect(DISTINCT c) + collect(DISTINCT t) +
     collect(DISTINCT a) + collect(DISTINCT chg) AS nodes
UNWIND nodes AS n
DETACH DELETE n
RETURN count(n) AS deleted
"""

_Q_DELETE_TRAINING_LABELS = """
UNWIND $enc_ids AS eid
MATCH (t:TrainingLabel)
WHERE toString(t.encounter_id) = eid
OPTIONAL MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t)
WITH collect(DISTINCT t) + collect(DISTINCT cr) AS nodes
UNWIND nodes AS n
DETACH DELETE n
RETURN count(n) AS deleted
"""

_Q_DELETE_ENCOUNTERS_BATCH = """
MATCH (e:Encounter)
WHERE toString(e.id) IN $enc_ids
DETACH DELETE e
RETURN count(e) AS deleted
"""

_Q_DELETE_PATIENT_SHORTCUTS = """
MATCH (p:Patient)-[r]->(s)
WHERE type(r) IN [
    'HAS_FINDING', 'HAS_DISORDER', 'HAS_SITUATION',
    'HAS_OBSERVABLE', 'HAS_PROCEDURE', 'HAS_CONCEPT'
]
  AND NOT (p)-[:HAS_ENCOUNTER]->(:Encounter)-[:DOCUMENTS]->(s)
DELETE r
RETURN count(r) AS deleted
"""

# -- Cypher: knowledge graph CodingDecision cleanup --------------------------

_Q_DELETE_CODING_DECISIONS = """
UNWIND $enc_ids AS eid
MATCH (d:CodingDecision)
WHERE d.encounter_id = eid
DETACH DELETE d
RETURN count(d) AS deleted
"""


# -- Helpers -----------------------------------------------------------------


def _collect_all_ids(session, keep_from: str, keep_to: str) -> list[str]:
    """Page through all target encounter IDs without loading everything at once."""
    all_ids: list[str] = []
    skip = 0
    while True:
        rows = list(
            session.run(
                _Q_PAGE_ENCOUNTER_IDS,
                keep_from=keep_from,
                keep_to=keep_to,
                skip=skip,
                limit=BATCH_SIZE,
            )
        )
        batch = [r["encounter_id"] for r in rows]
        all_ids.extend(batch)
        if len(batch) < BATCH_SIZE:
            break
        skip += BATCH_SIZE
    return all_ids


def _chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def _run_batched(session, query: str, all_ids: list[str], label: str) -> int:
    total = 0
    for i, chunk in enumerate(_chunks(all_ids, BATCH_SIZE), 1):
        row = session.run(query, enc_ids=chunk).single()
        n = (row or {}).get("deleted", 0)
        total += n
        log.info(
            "  %s batch %d/%d -> %d deleted",
            label,
            i,
            -(-len(all_ids) // BATCH_SIZE),
            n,
        )
    return total


def _run_batched_kg(kg_client, query: str, all_ids: list[str], label: str) -> int:
    total = 0
    chunks = list(_chunks(all_ids, BATCH_SIZE))
    for i, chunk in enumerate(chunks, 1):
        with kg_client.session() as session:
            row = session.run(query, enc_ids=chunk).single()
        n = (row or {}).get("deleted", 0)
        total += n
        log.info("  %s batch %d/%d -> %d deleted", label, i, len(chunks), n)
    return total


# -- Dry-run -----------------------------------------------------------------


def _dry_run(session, keep_from: str, keep_to: str, all_ids: list[str]) -> None:
    log.info("--- DRY-RUN AUDIT ---")

    row = session.run(_Q_COUNT_TARGET, keep_from=keep_from, keep_to=keep_to).single()
    log.info(
        "Encounters to delete: %d across %d distinct patients",
        row["encounter_count"],
        row["patient_count"],
    )

    null_row = session.run(_Q_COUNT_NULL_DATE).single()
    log.info(
        "Encounters with NULL date (will be skipped): %d", null_row["null_date_count"]
    )
    if null_row["null_date_count"]:
        samples = list(session.run(_Q_SAMPLE_NULL_DATE))
        for s in samples:
            log.info(
                "  null-date sample: enc=%s patient=%s",
                s["encounter_id"],
                s["patient_id"],
            )

    doc_row = session.run(
        _Q_COUNT_DOCUMENTS, keep_from=keep_from, keep_to=keep_to
    ).single()
    log.info("DOCUMENTS relationships to remove: %d", doc_row["doc_count"])

    if all_ids:
        cand_row = session.run(_Q_COUNT_CANDIDATES, enc_ids=all_ids).single()
        log.info("EncounterCandidate rows to remove: %d", cand_row["candidate_count"])

        lbl_row = session.run(_Q_COUNT_TRAINING_LABELS, enc_ids=all_ids).single()
        log.info("TrainingLabel rows to remove: %d", lbl_row["label_count"])

        rev_row = session.run(_Q_COUNT_CODING_REVIEWS, enc_ids=all_ids).single()
        log.info("CodingReview rows to remove: %d", rev_row["review_count"])

    isp_row = session.run(
        _Q_COUNT_IS_PART_OF, keep_from=keep_from, keep_to=keep_to
    ).single()
    log.info("IS_PART_OF edges to remove: %d", isp_row["is_part_of_count"])

    alert_row = session.run(
        _Q_COUNT_ALERTS, keep_from=keep_from, keep_to=keep_to
    ).single()
    log.info("SafetyNetAlert.TRIGGERED_AT edges affected: %d", alert_row["alert_count"])

    log.info("--- END DRY-RUN (no changes made) ---")
    log.info("Re-run with --apply to delete.")


# -- Apply -------------------------------------------------------------------


def _apply(pg_session, all_ids: list[str]) -> dict[str, int]:
    stats: dict[str, int] = {}

    log.info("Step 1/5: Deleting EncounterCandidate subgraphs ...")
    stats["candidates"] = _run_batched(
        pg_session, _Q_DELETE_CANDIDATES, all_ids, "candidates"
    )

    log.info("Step 2/5: Deleting TrainingLabel + CodingReview nodes ...")
    stats["training_labels"] = _run_batched(
        pg_session, _Q_DELETE_TRAINING_LABELS, all_ids, "training_labels"
    )

    log.info("Step 3/5: Deleting Encounter nodes (DETACH DELETE, batched) ...")
    stats["encounters"] = _run_batched(
        pg_session, _Q_DELETE_ENCOUNTERS_BATCH, all_ids, "encounters"
    )

    log.info("Step 4/5: Cleaning up stale patient shortcut relationships ...")
    row = pg_session.run(_Q_DELETE_PATIENT_SHORTCUTS).single()
    stats["shortcuts"] = (row or {}).get("deleted", 0)
    log.info("  Stale patient shortcuts removed: %d", stats["shortcuts"])

    return stats


def _apply_kg(all_ids: list[str]) -> int:
    try:
        from libs.neo4j_client.client import KnowledgeGraphClient

        kg = KnowledgeGraphClient()
        log.info("Step 5/5: Deleting CodingDecision nodes from knowledge graph ...")
        total = _run_batched_kg(
            kg, _Q_DELETE_CODING_DECISIONS, all_ids, "coding_decisions"
        )
        kg.close()
        return total
    except Exception as exc:  # noqa: BLE001
        log.warning("Knowledge graph CodingDecision cleanup skipped: %s", exc)
        return 0


# -- Main --------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the delete. Omit for dry-run (default).",
    )
    parser.add_argument(
        "--keep-from",
        default=DEFAULT_KEEP_FROM,
        help=f"Earliest date to KEEP (inclusive, ISO format). Default: {DEFAULT_KEEP_FROM}",
    )
    parser.add_argument(
        "--keep-to",
        default=DEFAULT_KEEP_TO,
        help=f"Latest date to KEEP (inclusive, ISO format). Default: {DEFAULT_KEEP_TO}",
    )
    parser.add_argument(
        "--export-ids",
        metavar="PATH",
        help="JSONL file to write deleted encounter IDs to before applying.",
    )
    args = parser.parse_args()

    keep_from = args.keep_from
    keep_to = args.keep_to

    log.info(
        "Window to KEEP: %s to %s (inclusive). Encounters outside this window will be deleted.",
        keep_from,
        keep_to,
    )

    from libs.neo4j_client.client import PatientGraphClient

    pg = PatientGraphClient()

    with pg.session() as session:
        log.info("Collecting target encounter IDs ...")
        all_ids = _collect_all_ids(session, keep_from, keep_to)
        log.info("Total encounters matching delete predicate: %d", len(all_ids))

        if not all_ids:
            log.info("Nothing to delete -- all encounters are within the window.")
            pg.close()
            return

        _dry_run(session, keep_from, keep_to, all_ids)

    if not args.apply:
        pg.close()
        return

    if args.export_ids:
        export_path = Path(args.export_ids)
        with export_path.open("w", encoding="utf-8") as fh:
            for enc_id in all_ids:
                fh.write(json.dumps({"encounter_id": enc_id}) + "\n")
        log.info("Exported %d encounter IDs to %s", len(all_ids), export_path)

    log.info("--- APPLYING DELETIONS ---")
    with pg.session() as session:
        stats = _apply(session, all_ids)

    kg_deleted = _apply_kg(all_ids)
    stats["coding_decisions"] = kg_deleted

    log.info("--- DELETION COMPLETE ---")
    log.info("  Encounters deleted       : %d", stats["encounters"])
    log.info("  Candidate rows removed   : %d", stats["candidates"])
    log.info("  TrainingLabel rows removed: %d", stats["training_labels"])
    log.info("  Patient shortcuts cleaned: %d", stats["shortcuts"])
    log.info("  CodingDecision rows (KG) : %d", stats["coding_decisions"])
    log.info("")
    log.info("IMPORTANT: EpisodeOfCare list properties (referral_encounter_ids,")
    log.info("  diagnosis_encounter_id, etc.) may still reference deleted encounter")
    log.info("  IDs. Run scripts/remediate_episodes.py for the affected patient IDs")
    log.info("  or run the analysis-worker episode build to regenerate episodes.")
    pg.close()


if __name__ == "__main__":
    main()
