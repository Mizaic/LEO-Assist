#!/usr/bin/env python3
"""Check encounter vector index and embedding coverage in Patient Neo4j.

Usage:
    python scripts/check_encounter_embeddings.py
    python scripts/check_encounter_embeddings.py --patient-id 4622879921
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env")

from neo4j import GraphDatabase


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-id", help="Scope to a single patient")
    args = parser.parse_args()

    uri = os.environ.get("NEO4J_URI", "").strip()
    user = os.environ.get("NEO4J_USER", "").strip()
    password = os.environ.get("NEO4J_PASSWORD", "").strip()
    if not all([uri, user, password]):
        print("ERROR: Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD in secrets/.env")
        sys.exit(1)

    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session() as session:
            # 1. Check if encounter_vector_index exists
            result = session.run(
                "SHOW INDEXES WHERE name = $name AND type = 'VECTOR'",
                name="encounter_vector_index",
            )
            indexes = list(result)
            if indexes:
                idx = indexes[0]
                print("encounter_vector_index: EXISTS")
                print(f"  state: {idx.get('state', '?')}")
                print(f"  type: {idx.get('type', '?')}")
                print(f"  labelsOrTypes: {idx.get('labelsOrTypes', '?')}")
                print(f"  properties: {idx.get('properties', '?')}")
            else:
                print("encounter_vector_index: NOT FOUND")
                print("  Run embedding reindex from visual-report-builder clinical-ai")
                print(
                    "  (POST /embeddings/reindex) to create index and populate embeddings"
                )

            # 2. Encounter counts (index uses 'vector', embedding_manager writes 'embedding')
            if args.patient_id:
                q = """
                    MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
                    WHERE toString(p.id) = $pid
                    RETURN count(e) AS total,
                           count(e.embedding) AS with_embedding,
                           count(e.vector) AS with_vector
                """
                params = {"pid": args.patient_id}
            else:
                q = """
                    MATCH (e:Encounter)
                    RETURN count(e) AS total,
                           count(e.embedding) AS with_embedding,
                           count(e.vector) AS with_vector
                """
                params = {}

            row = session.run(q, params).single()
            total = row["total"] if row else 0
            with_emb = row["with_embedding"] if row else 0
            with_vec = row["with_vector"] if row else 0

            scope = (
                f"patient {args.patient_id}" if args.patient_id else "all encounters"
            )
            print(f"\nEncounter counts ({scope}):")
            print(f"  total: {total}")
            print(f"  with embedding (e.embedding): {with_emb}")
            print(f"  with vector (e.vector, used by index): {with_vec}")
            pct_vec = round(100 * with_vec / total, 1) if total else 0
            print(f"  vector coverage: {pct_vec}%")

            if total > 0 and with_vec == 0:
                print(
                    "\n  No vectors found. Index uses e.vector; run embedding reindex."
                )
            elif total > 0 and with_vec < total:
                print(
                    f"\n  {total - with_vec} encounters missing vectors (indexed property)."
                )
    finally:
        driver.close()


if __name__ == "__main__":
    main()
