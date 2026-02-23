"""
CLI script: export Neo4j terminology graph -> Entity JSONL -> TF-IDF/ANN index.

Usage::

    python -m services.terminology.scripts.build_index --output-dir data/
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


def _get_neo4j_driver():
    import os

    from neo4j import AsyncGraphDatabase

    secrets_env = Path(__file__).resolve().parents[3] / "secrets" / ".env"
    if secrets_env.exists():
        load_dotenv(secrets_env)

    uri = os.environ["CODING_GRAPH_NEO4J_URI"]
    user = os.environ["CODING_GRAPH_NEO4J_USERNAME"]
    password = os.environ["CODING_GRAPH_NEO4J_PASSWORD"]
    return AsyncGraphDatabase.driver(uri, auth=(user, password))


async def _run(output_dir: Path) -> None:
    from services.terminology.nlp.kb.kb_export import export_kb
    from services.terminology.nlp.kb.knowledge_base import KnowledgeBase
    from services.terminology.nlp.kb.candidate_generation import (
        create_tfidf_ann_index,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "entities.jsonl"

    driver = _get_neo4j_driver()
    try:
        logger.info("Step 1/3: Exporting Neo4j -> JSONL")
        count = await export_kb(driver, jsonl_path)
        logger.info("Exported %d entities", count)
    finally:
        await driver.close()

    logger.info("Step 2/3: Loading knowledge base from JSONL")
    kb = KnowledgeBase.from_jsonl(jsonl_path)

    logger.info("Step 3/3: Building TF-IDF + ANN index")
    create_tfidf_ann_index(kb, output_dir)

    logger.info("Done. Artifacts in %s", output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Neo4j terminology and build TF-IDF/ANN index"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("services/terminology/data"),
        help="Directory to write artifacts (default: services/terminology/data)",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.output_dir))


if __name__ == "__main__":
    main()
