"""Delete TrainingCandidate + GoldLabel nodes written during the v3 audit
that have assessment=no_clinical_content (source='audit_verified', empty
entities JSON).

These were written incorrectly -- admin encounters should never enter the KG.
Targets only records with empty entities (i.e. no_clinical_content entries).

Run:
    python scripts/investigations/_purge_ncc_kg_candidates.py --dry-run
    python scripts/investigations/_purge_ncc_kg_candidates.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402

COUNT_Q = """
MATCH (tc:TrainingCandidate {source: 'audit_verified'})
WHERE tc.entities IS NOT NULL AND trim(tc.entities) IN ('[]', '')
OPTIONAL MATCH (tc)-[:HAS_LABEL]->(gl:GoldLabel)
RETURN count(DISTINCT tc) AS candidates, count(DISTINCT gl) AS labels
"""

DELETE_Q = """
MATCH (tc:TrainingCandidate {source: 'audit_verified'})
WHERE tc.entities IS NOT NULL AND trim(tc.entities) IN ('[]', '')
OPTIONAL MATCH (tc)-[:HAS_LABEL]->(gl:GoldLabel)
DETACH DELETE tc, gl
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    kg = KnowledgeGraphClient()
    try:
        with kg.session() as s:
            row = s.run(COUNT_Q).single()
            candidates = row["candidates"] if row else 0
            labels = row["labels"] if row else 0

        print(
            f"Found {candidates} empty-entity TrainingCandidates, {labels} GoldLabels"
        )

        if candidates == 0:
            print("Nothing to delete.")
            return

        if args.dry_run:
            print("DRY RUN -- no changes made.")
            return

        with kg.session() as s:
            s.run(DELETE_Q)
        print(f"Deleted {candidates} TrainingCandidates and {labels} GoldLabels.")
    finally:
        kg.close()


if __name__ == "__main__":
    main()
