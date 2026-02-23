"""Verify Phase 3: UMLS crosswalk loaded correctly."""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase


CHECKS = [
    (
        "UmlsConcept node count",
        "MATCH (u:UmlsConcept) RETURN count(u) AS cnt",
    ),
    (
        "SAME_AS relationships (CUI->SNOMED)",
        "MATCH ()-[r:SAME_AS]->() RETURN count(r) AS cnt",
    ),
    (
        "UmlsConcept->MAPS_TO_ICD10 relationships",
        "MATCH (u:UmlsConcept)-[r:MAPS_TO_ICD10]->() RETURN count(r) AS cnt",
    ),
    (
        "UmlsConcept->MAPS_TO_READ relationships",
        "MATCH (u:UmlsConcept)-[r:MAPS_TO_READ]->() RETURN count(r) AS cnt",
    ),
    (
        "UmlsConcepts with semantic types",
        """
        MATCH (u:UmlsConcept)
        WHERE u.semantic_types IS NOT NULL AND size(u.semantic_types) > 0
        RETURN count(u) AS cnt
        """,
    ),
    (
        "Sample UmlsConcept with semantic types",
        """
        MATCH (u:UmlsConcept)-[:SAME_AS]->(c:Concept)
        WHERE u.semantic_types IS NOT NULL AND c.active = true
        RETURN u.cui AS cui, u.preferred_name AS name,
               u.semantic_types AS types, c.id AS snomed
        LIMIT 3
        """,
    ),
    (
        "End-to-end: diabetes mellitus (Term->Concept->UmlsConcept->ICD10)",
        """
        MATCH (t:Term)-[:DESCRIBES]->(c:Concept)<-[:SAME_AS]-(u:UmlsConcept)
        WHERE t.normalized_form = 'diabetes mellitus' AND c.active = true
        OPTIONAL MATCH (c)-[:MAPS_TO_ICD10]->(icd:Icd10Code)
        RETURN c.id AS snomed, c.fsn AS fsn, u.cui AS cui,
               u.preferred_name AS umls_name,
               u.semantic_types AS sem_types,
               collect(DISTINCT icd.code) AS icd10
        LIMIT 3
        """,
    ),
    (
        "End-to-end: hypertension lookup",
        """
        MATCH (t:Term)-[:DESCRIBES]->(c:Concept)<-[:SAME_AS]-(u:UmlsConcept)
        WHERE t.normalized_form = 'hypertension' AND c.active = true
        OPTIONAL MATCH (c)-[:MAPS_TO_ICD10]->(icd:Icd10Code)
        OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
        RETURN c.id AS snomed, c.fsn AS fsn, u.cui AS cui,
               u.semantic_types AS sem_types,
               collect(DISTINCT icd.code) AS icd10,
               collect(DISTINCT rd.code) AS read_codes
        LIMIT 3
        """,
    ),
]


async def main():
    load_dotenv(Path("secrets") / ".env")
    uri = os.environ["CODING_GRAPH_NEO4J_URI"]
    user = os.environ["CODING_GRAPH_NEO4J_USERNAME"]
    pw = os.environ["CODING_GRAPH_NEO4J_PASSWORD"]

    driver = AsyncGraphDatabase.driver(uri, auth=(user, pw))
    try:
        async with driver.session() as session:
            for title, cypher in CHECKS:
                print(f"\n{'=' * 60}")
                print(f"  {title}")
                print(f"{'=' * 60}")
                result = await session.run(cypher)
                records = await result.data()
                if not records:
                    print("  (no results)")
                for rec in records:
                    for k, v in rec.items():
                        print(f"  {k}: {v}")
                    if len(records) > 1:
                        print("  ---")
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
