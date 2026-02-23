"""Final verification: all phases loaded, all node types, cross-links working."""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase


CHECKS = [
    (
        "Node counts by label",
        """
        CALL db.labels() YIELD label
        CALL {
            WITH label
            CALL db.stats.retrieve('GRAPH COUNTS') YIELD nodeCount
            RETURN nodeCount
        }
        RETURN label, nodeCount
        ORDER BY nodeCount DESC
        """,
    ),
    (
        "Node counts (fallback)",
        """
        MATCH (n)
        WITH labels(n) AS lbls
        UNWIND lbls AS lbl
        RETURN lbl AS label, count(*) AS cnt
        ORDER BY cnt DESC
        """,
    ),
    (
        "Relationship counts by type",
        """
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, count(*) AS cnt
        ORDER BY cnt DESC
        """,
    ),
    (
        "ReadCode nodes: count by version",
        """
        MATCH (r:ReadCode)
        RETURN r.version AS version, count(*) AS cnt
        ORDER BY cnt DESC
        """,
    ),
    (
        "ReadCode nodes with terms (enriched by DMWB)",
        """
        MATCH (r:ReadCode)
        WHERE r.term IS NOT NULL AND r.term <> ''
        RETURN count(r) AS with_term
        """,
    ),
    (
        "Icd10Code with terms (enriched by DMWB)",
        """
        MATCH (i:Icd10Code)
        WHERE i.term IS NOT NULL AND i.term <> ''
        RETURN count(i) AS with_term
        """,
    ),
    (
        "DrugConcept counts by type",
        """
        MATCH (d:DrugConcept)
        RETURN d.type AS drug_type, count(*) AS cnt
        ORDER BY cnt DESC
        """,
    ),
    (
        "SurfaceForm counts by source",
        """
        MATCH (s:SurfaceForm)
        RETURN s.source AS source, count(*) AS cnt
        ORDER BY cnt DESC
        """,
    ),
    (
        "End-to-end: 'chest pain' lookup",
        """
        MATCH (t:Term)-[:DESCRIBES]->(c:Concept)
        WHERE t.normalized_form = 'chest pain' AND c.active = true
        OPTIONAL MATCH (c)<-[:SAME_AS]-(u:UmlsConcept)
        OPTIONAL MATCH (c)-[:MAPS_TO_ICD10]->(icd:Icd10Code)
        OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
        RETURN c.id AS snomed, c.fsn AS fsn,
               u.cui AS cui, u.semantic_types AS sem_types,
               collect(DISTINCT icd.code) AS icd10,
               collect(DISTINCT rd.code) AS read_codes
        LIMIT 3
        """,
    ),
    (
        "Drug lookup: 'Paracetamol'",
        """
        MATCH (d:DrugConcept)
        WHERE d.name = 'Paracetamol' AND d.type = 'VTM'
        OPTIONAL MATCH (child:DrugConcept)-[:IS_A]->(d)
        RETURN d.id AS vtm_id, d.name AS vtm_name,
               count(child) AS child_count,
               collect(child.name)[..3] AS sample_children
        """,
    ),
    (
        "Surface form to concept lookup: 'diabetes'",
        """
        MATCH (sf:SurfaceForm)
        WHERE sf.normalized = 'diabetes'
        OPTIONAL MATCH (t:Term)
        WHERE t.normalized_form = sf.normalized
        OPTIONAL MATCH (t)-[:DESCRIBES]->(c:Concept {active: true})
        RETURN sf.form AS surface_form, sf.source AS source,
               count(DISTINCT c) AS matching_concepts
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
                try:
                    result = await session.run(cypher)
                    records = await result.data()
                except Exception as e:
                    print(f"  ERROR: {e}")
                    continue
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
