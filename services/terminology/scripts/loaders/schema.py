"""
Neo4j schema setup: constraints, indexes, and fulltext indexes.

Run once before loading data. Idempotent — safe to re-run.
"""

from __future__ import annotations

import logging

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

CONSTRAINTS = [
    "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT term_id IF NOT EXISTS FOR (t:Term) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT umls_cui IF NOT EXISTS FOR (u:UmlsConcept) REQUIRE u.cui IS UNIQUE",
    "CREATE CONSTRAINT icd10_code IF NOT EXISTS FOR (i:Icd10Code) REQUIRE i.code IS UNIQUE",
    "CREATE CONSTRAINT read_code IF NOT EXISTS FOR (r:ReadCode) REQUIRE r.code IS UNIQUE",
    "CREATE CONSTRAINT drug_id IF NOT EXISTS FOR (d:DrugConcept) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT surface_form IF NOT EXISTS FOR (s:SurfaceForm) REQUIRE s.form IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX term_normalized IF NOT EXISTS FOR (t:Term) ON (t.normalized_form)",
    "CREATE INDEX surface_normalized IF NOT EXISTS FOR (s:SurfaceForm) ON (s.normalized)",
    "CREATE INDEX concept_active IF NOT EXISTS FOR (c:Concept) ON (c.active)",
]

FULLTEXT_INDEXES = [
    (
        "term_fulltext",
        "CREATE FULLTEXT INDEX term_fulltext IF NOT EXISTS "
        "FOR (t:Term) ON EACH [t.surface_form]",
    ),
]


async def ensure_schema(driver: AsyncDriver) -> None:
    """Create all constraints and indexes. Idempotent."""
    async with driver.session() as session:
        for stmt in CONSTRAINTS:
            logger.info("Schema: %s", stmt[:60])
            await session.run(stmt)

        for stmt in INDEXES:
            logger.info("Schema: %s", stmt[:60])
            await session.run(stmt)

        for name, stmt in FULLTEXT_INDEXES:
            logger.info("Schema: fulltext %s", name)
            await session.run(stmt)

    logger.info("Schema setup complete")
