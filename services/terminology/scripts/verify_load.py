"""Verify loaded terminology data: node counts, properties, sample records."""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase


CHECKS = [
    (
        "Concept node counts (active vs inactive)",
        """
        MATCH (c:Concept)
        RETURN c.active AS active, count(*) AS cnt
        ORDER BY active DESC
        """,
    ),
    (
        "Concept sample (active, with FSN and semantic_tag)",
        """
        MATCH (c:Concept)
        WHERE c.active = true AND c.fsn IS NOT NULL AND c.semantic_tag IS NOT NULL
        RETURN c.id AS id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
               c.effective_time AS effective_time, c.module_id AS module_id
        LIMIT 3
        """,
    ),
    (
        "Term node count + property check",
        """
        MATCH (t:Term)
        WITH count(*) AS total,
             count(t.surface_form) AS has_surface,
             count(t.normalized_form) AS has_normalized,
             count(t.term_type) AS has_type,
             count(t.language_code) AS has_lang
        RETURN total, has_surface, has_normalized, has_type, has_lang
        """,
    ),
    (
        "Term sample (with DESCRIBES relationship)",
        """
        MATCH (t:Term)-[d:DESCRIBES]->(c:Concept)
        WHERE d.acceptability = 'preferred' AND c.active = true
        RETURN t.surface_form AS term, t.normalized_form AS normalized,
               t.term_type AS type, d.acceptability AS acceptability,
               c.id AS concept_id
        LIMIT 3
        """,
    ),
    (
        "Icd10Code count + sample with mapping",
        """
        MATCH (c:Concept)-[m:MAPS_TO_ICD10]->(icd:Icd10Code)
        WHERE c.active = true
        RETURN icd.code AS icd10, c.id AS snomed_id, c.fsn AS snomed_fsn,
               m.map_advice AS advice
        LIMIT 3
        """,
    ),
    (
        "ReadCode count + sample with mapping",
        """
        MATCH (c:Concept)-[:MAPS_TO_READ]->(r:ReadCode)
        WHERE c.active = true
        RETURN r.code AS read_code, r.version AS version,
               c.id AS snomed_id, c.fsn AS snomed_fsn
        LIMIT 3
        """,
    ),
    (
        "IS_A relationships count",
        """
        MATCH ()-[r:IS_A]->()
        RETURN count(r) AS is_a_count
        """,
    ),
    (
        "HAS_RELATIONSHIP count (defining attributes)",
        """
        MATCH ()-[r:HAS_RELATIONSHIP]->()
        RETURN count(r) AS attr_count
        """,
    ),
    (
        "IS_A sample (hierarchy check)",
        """
        MATCH (child:Concept)-[:IS_A]->(parent:Concept)
        WHERE child.active = true AND parent.active = true
              AND child.fsn IS NOT NULL AND parent.fsn IS NOT NULL
        RETURN child.fsn AS child, parent.fsn AS parent
        LIMIT 3
        """,
    ),
    (
        "DESCRIBES relationship count + acceptability breakdown",
        """
        MATCH ()-[d:DESCRIBES]->()
        RETURN d.acceptability AS acceptability, count(*) AS cnt
        ORDER BY cnt DESC
        """,
    ),
    (
        "Diabetes mellitus lookup test",
        """
        MATCH (t:Term)-[:DESCRIBES]->(c:Concept)
        WHERE t.normalized_form = 'diabetes mellitus'
        OPTIONAL MATCH (c)-[:MAPS_TO_ICD10]->(icd:Icd10Code)
        RETURN c.id AS snomed, c.fsn AS fsn,
               collect(DISTINCT icd.code) AS icd10_codes
        LIMIT 5
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
