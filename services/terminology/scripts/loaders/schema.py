"""
Neo4j schema setup: constraints, indexes, and fulltext indexes.

Run once before loading data. Idempotent — safe to re-run.
"""

from __future__ import annotations

import logging
import os

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

CONSTRAINTS = [
    "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT term_id IF NOT EXISTS FOR (t:Term) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT icd10_code IF NOT EXISTS FOR (i:Icd10Code) REQUIRE i.code IS UNIQUE",
    "CREATE CONSTRAINT opcs4_code IF NOT EXISTS FOR (o:OpcsCode) REQUIRE o.code IS UNIQUE",
    "CREATE CONSTRAINT read_code IF NOT EXISTS FOR (r:ReadCode) REQUIRE r.code IS UNIQUE",
    "CREATE CONSTRAINT drug_id IF NOT EXISTS FOR (d:DrugConcept) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT surface_form_norm IF NOT EXISTS FOR (s:SurfaceForm) REQUIRE s.normalized IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX term_normalized IF NOT EXISTS FOR (t:Term) ON (t.normalized_form)",
    "CREATE INDEX concept_active IF NOT EXISTS FOR (c:Concept) ON (c.active)",
    "CREATE INDEX surface_form_text IF NOT EXISTS FOR (s:SurfaceForm) ON (s.form)",
    "CREATE INDEX icd10_level IF NOT EXISTS FOR (i:Icd10Code) ON (i.level)",
    "CREATE INDEX opcs4_level IF NOT EXISTS FOR (o:OpcsCode) ON (o.level)",
]

FULLTEXT_INDEXES = [
    (
        "term_fulltext",
        "CREATE FULLTEXT INDEX term_fulltext IF NOT EXISTS "
        "FOR (t:Term) ON EACH [t.surface_form]",
    ),
    (
        "surface_form_fulltext",
        "CREATE FULLTEXT INDEX surface_form_fulltext IF NOT EXISTS "
        "FOR (s:SurfaceForm) ON EACH [s.form]",
    ),
]


def _vector_index_stmt() -> tuple[str, str]:
    dim = int(os.environ.get("VECTOR_DIMENSION", "768"))
    index_name = "term_embedding_idx"
    stmt = (
        f"CREATE VECTOR INDEX {index_name} IF NOT EXISTS "
        "FOR (t:Term) ON (t.embedding) "
        "OPTIONS {indexConfig: {"
        f"`vector.dimensions`: {dim}, "
        "`vector.similarity_function`: 'cosine'"
        "}}"
    )
    return index_name, stmt


def _surface_form_vector_index_stmt() -> tuple[str, str]:
    dim = int(os.environ.get("VECTOR_DIMENSION", "768"))
    index_name = "surface_form_embedding_idx"
    stmt = (
        f"CREATE VECTOR INDEX {index_name} IF NOT EXISTS "
        "FOR (s:SurfaceForm) ON (s.embedding) "
        "OPTIONS {indexConfig: {"
        f"`vector.dimensions`: {dim}, "
        "`vector.similarity_function`: 'cosine'"
        "}}"
    )
    return index_name, stmt


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

        vector_name, vector_stmt = _vector_index_stmt()
        logger.info("Schema: vector %s", vector_name)
        await session.run(vector_stmt)

        sf_vector_name, sf_vector_stmt = _surface_form_vector_index_stmt()
        logger.info("Schema: vector %s", sf_vector_name)
        await session.run(sf_vector_stmt)

    logger.info("Schema setup complete")
