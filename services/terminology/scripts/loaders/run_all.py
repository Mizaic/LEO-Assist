"""
Orchestrator: run SNOMED and dm+d terminology load phases.

Usage (from repo root):
    python -m services.terminology.scripts.loaders [--phases 1,2,3,5]

Phases:
    1  SNOMED core (Concept, Description, Language, Relationship)
    2  SNOMED maps (ExtendedMap -> ICD-10, SimpleMap -> Read)
    3  SNOMED inferred attribute projections
    5  dm+d drug extension (VTM, VMP, AMP, VMPP, AMPP)

Neo4j connection comes from secrets/.env:
    KNOWLEDGE_GRAPH_NEO4J_URI
    KNOWLEDGE_GRAPH_NEO4J_USERNAME
    KNOWLEDGE_GRAPH_NEO4J_PASSWORD
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

from .dmd_drugs import load_dmd
from .file_finder import DmdFiles, SnomedFiles
from .schema import ensure_schema
from .snomed_concept import load_concepts
from .snomed_description import load_descriptions
from .snomed_language import load_language_refset
from .snomed_map import load_extended_map, load_simple_map
from .snomed_attribute_projection import load_inferred_attribute_relationships
from .snomed_relationship import load_relationships

logger = logging.getLogger(__name__)


def _load_neo4j_config() -> tuple[str, str, str]:
    """Load Neo4j connection details from secrets/.env, then env vars."""
    secrets_env = Path("secrets") / ".env"
    if secrets_env.exists():
        load_dotenv(secrets_env)
        logger.info("Loaded secrets from %s", secrets_env)

    uri = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_URI", "")
    user = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "")
    password = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")

    if not all([uri, user, password]):
        raise RuntimeError(
            "Missing KNOWLEDGE_GRAPH_NEO4J_URI / _USERNAME / _PASSWORD. "
            "Set in secrets/.env or environment."
        )
    return uri, user, password


async def _load_if_found(loader, driver, path: Path | None, label: str) -> int:
    if path is None:
        logger.warning("SKIP %s - file not found", label)
        return 0
    return await loader(driver, path)


async def run_phase_1(driver, files: SnomedFiles) -> None:
    """Phase 1: SNOMED core - concepts, descriptions, language, relationships."""
    logger.info("=" * 60)
    logger.info("PHASE 1: SNOMED Core")
    logger.info("=" * 60)

    await _load_if_found(load_concepts, driver, files.int_concept(), "INT Concepts")
    await _load_if_found(load_concepts, driver, files.ukcl_concept(), "UKCL Concepts")
    await _load_if_found(load_concepts, driver, files.uked_concept(), "UKED Concepts")
    await _load_if_found(load_concepts, driver, files.ukcr_concept(), "UKCR Concepts")

    await _load_if_found(
        load_descriptions,
        driver,
        files.int_description(),
        "INT Descriptions",
    )
    await _load_if_found(
        load_descriptions,
        driver,
        files.ukcl_description(),
        "UKCL Descriptions",
    )
    await _load_if_found(
        load_descriptions,
        driver,
        files.uked_description(),
        "UKED Descriptions",
    )
    await _load_if_found(
        load_descriptions,
        driver,
        files.ukcr_description(),
        "UKCR Descriptions",
    )

    await _load_if_found(
        load_language_refset,
        driver,
        files.ukcl_language(),
        "UKCL Language",
    )
    await _load_if_found(
        load_language_refset,
        driver,
        files.uked_language(),
        "UKED Language",
    )
    await _load_if_found(
        load_language_refset,
        driver,
        files.ukcr_language(),
        "UKCR Language",
    )

    await _load_if_found(
        load_relationships,
        driver,
        files.int_relationship(),
        "INT Relationships",
    )
    await _load_if_found(
        load_relationships,
        driver,
        files.ukcl_relationship(),
        "UKCL Relationships",
    )
    await _load_if_found(
        load_relationships,
        driver,
        files.uked_relationship(),
        "UKED Relationships",
    )
    await _load_if_found(
        load_relationships,
        driver,
        files.ukcr_relationship(),
        "UKCR Relationships",
    )


async def run_phase_2(driver, files: SnomedFiles) -> None:
    """Phase 2: SNOMED maps - ICD-10 and Read codes."""
    logger.info("=" * 60)
    logger.info("PHASE 2: SNOMED Maps")
    logger.info("=" * 60)

    await _load_if_found(
        load_extended_map,
        driver,
        files.int_extended_map(),
        "INT ExtendedMap (ICD-10)",
    )
    await _load_if_found(
        load_extended_map,
        driver,
        files.ukcl_extended_map(),
        "UKCL ExtendedMap (ICD-10 UK)",
    )
    await _load_if_found(
        load_extended_map,
        driver,
        files.uked_extended_map(),
        "UKED ExtendedMap (ICD-10 UK Edition)",
    )
    await _load_if_found(
        load_extended_map,
        driver,
        files.ukcr_extended_map(),
        "UKCR ExtendedMap (ICD-10 UK Clinical Refsets)",
    )
    await _load_if_found(
        load_simple_map,
        driver,
        files.int_simple_map(),
        "INT SimpleMap (CTV3)",
    )
    await _load_if_found(
        load_simple_map,
        driver,
        files.uked_simple_map(),
        "UKED SimpleMap (CTV3 UK Edition)",
    )
    await _load_if_found(
        load_simple_map,
        driver,
        files.ukcr_simple_map(),
        "UKCR SimpleMap (CTV3 UK Clinical Refsets)",
    )


async def run_phase_3(driver) -> None:
    """Phase 3: materialize readable SNOMED attribute relationships."""
    logger.info("=" * 60)
    logger.info("PHASE 3: SNOMED Attribute Projections")
    logger.info("=" * 60)
    await load_inferred_attribute_relationships(driver)


async def run_phase_5(driver, dmd: DmdFiles) -> None:
    """Phase 5: dm+d drug extension."""
    logger.info("=" * 60)
    logger.info("PHASE 5: dm+d Drug Extension")
    logger.info("=" * 60)

    dmd_dir = dmd.dmd_dir()
    if dmd_dir is None:
        logger.warning("SKIP dm+d - directory not found")
        return
    await load_dmd(driver, dmd_dir)


async def main(external_content: Path, phases: set[int]) -> None:
    uri, user, password = _load_neo4j_config()
    logger.info("Connecting to Neo4j at %s", uri)

    snomed_files = SnomedFiles(external_content)
    dmd_files = DmdFiles(external_content)

    all_found = {
        **snomed_files.all_found(),
        **dmd_files.all_found(),
    }
    for name, path in all_found.items():
        status = str(path) if path else "NOT FOUND"
        logger.info("  %-25s %s", name, status)

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    try:
        await ensure_schema(driver)

        t0 = time.monotonic()
        if 1 in phases:
            await run_phase_1(driver, snomed_files)
        if 2 in phases:
            await run_phase_2(driver, snomed_files)
        if 3 in phases:
            await run_phase_3(driver)
        if 5 in phases:
            await run_phase_5(driver, dmd_files)
        elapsed = time.monotonic() - t0
        logger.info("All phases complete in %.1fs", elapsed)
    finally:
        await driver.close()


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Load SNOMED/dm+d terminology data into Neo4j"
    )
    parser.add_argument(
        "--external-content",
        type=Path,
        default=Path("external_content"),
        help="Path to external_content/ directory",
    )
    parser.add_argument(
        "--phases",
        default="1,2,3,5",
        help="Comma-separated phase numbers to run (default: 1,2,3,5)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    phases = {int(p.strip()) for p in args.phases.split(",")}
    asyncio.run(main(args.external_content, phases))


if __name__ == "__main__":
    cli()
