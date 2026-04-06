"""Delete 23 false-positive 'No evidence of cancer found' DOCUMENTS codings.

These are routine screening results (cervical smear negatives, FIT/FOBT negatives,
HPV not detected) that the LLM incorrectly mapped to 395100000.

The concept 395100000 | No evidence of cancer found (situation) is ONLY valid
for post-investigation discharge from an active cancer pathway, not for
routine population screening negatives.

Also removes the patient-level HAS_SITUATION relationship if no other encounters
for that patient link to the concept.

Run:
    python scripts/investigations/_delete_screening_false_positives.py --dry-run
    python scripts/investigations/_delete_screening_false_positives.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

CONCEPT_ID = 395100000

# Phrases that definitively identify a routine screening result rather than
# a post-pathway cancer discharge.  Match is case-insensitive substring.
SCREENING_EVIDENCE_PATTERNS = [
    "negative cervical cytology",
    "cervical smear: negative",
    "cervical smear - negative",
    "cervical cytology screening test",
    "cytology laboratory test",
    "hpv test: high risk hpv not detected",
    "hpv test: high risk hpv not detected.",
    "overall negative result",
    "sent following an overall negative result",
    "negative fit",
    "fobt normal",
    "bowel cancer screening",
    "normal recall",
]

_Q_FIND = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE c.conceptId = $cid
RETURN
    toString(p.id)  AS patient_id,
    toString(e.id)  AS encounter_id,
    r.evidence_sentence AS evs,
    r.evidence          AS ev
"""

_Q_DELETE_DOC = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(e.id) = $eid AND c.conceptId = $cid
DELETE r
"""

_Q_COUNT_REMAINING_DOC = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid AND c.conceptId = $cid
RETURN count(r) AS n
"""

_Q_DELETE_HAS_SITUATION = """
MATCH (p:Patient)-[r:HAS_SITUATION]->(c)
WHERE toString(p.id) = $pid AND c.conceptId = $cid
DELETE r
"""


def is_screening_evidence(evidence: str) -> bool:
    ev_lower = (evidence or "").lower()
    return any(p in ev_lower for p in SCREENING_EVIDENCE_PATTERNS)


def main(dry_run: bool) -> None:
    from libs.neo4j_client.client import PatientGraphClient
    client = PatientGraphClient()

    to_delete: list[dict] = []

    print(f"Finding all DOCUMENTS codings for conceptId={CONCEPT_ID} ...")
    with client.session() as session:
        rows = list(session.run(_Q_FIND, cid=CONCEPT_ID))

    for r in rows:
        evidence = (r["evs"] or r["ev"] or "").strip()
        if is_screening_evidence(evidence):
            to_delete.append({
                "patient_id": r["patient_id"],
                "encounter_id": r["encounter_id"],
                "evidence": evidence[:100],
            })

    print(f"Total codings found       : {len(rows)}")
    print(f"Identified for deletion   : {len(to_delete)}")
    print()

    if not to_delete:
        print("Nothing to delete.")
        client.close()
        return

    print(f"{'DRY RUN - ' if dry_run else ''}Deleting DOCUMENTS relationships ...")
    print()

    deleted_docs = 0
    deleted_has  = 0

    with client.session() as session:
        for item in to_delete:
            eid = item["encounter_id"]
            pid = item["patient_id"]
            ev  = item["evidence"]
            tag = "[DRY]" if dry_run else "[DEL]"
            print(f"  {tag} enc={eid[:8]}...  ev={ev[:70]!r}")

            if not dry_run:
                session.run(_Q_DELETE_DOC, eid=eid, cid=CONCEPT_ID)
                deleted_docs += 1

                # Remove HAS_SITUATION only if no other encounters still link
                remaining = session.run(
                    _Q_COUNT_REMAINING_DOC, pid=pid, cid=CONCEPT_ID
                ).single()
                if remaining and remaining["n"] == 0:
                    session.run(_Q_DELETE_HAS_SITUATION, pid=pid, cid=CONCEPT_ID)
                    deleted_has += 1
                    print(f"         -> also removed HAS_SITUATION for patient {pid}")

    print()
    if dry_run:
        print(f"DRY RUN complete. Would delete {len(to_delete)} DOCUMENTS relationships.")
        print("Re-run without --dry-run to apply.")
    else:
        print(f"Deleted {deleted_docs} DOCUMENTS relationships.")
        print(f"Deleted {deleted_has} HAS_SITUATION patient relationships.")

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Delete screening false-positive 395100000 codings"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be deleted without making changes"
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
