"""Seed all hardcoded Python prompts into Neo4j as PromptConfig nodes.

Usage:
    python -m scripts.seed_prompt_configs

Idempotent — uses MERGE on (name, version), so re-running is safe.
Only overwrites prompt text for nodes whose ``source`` is still ``seed``;
user-edited prompts are left untouched.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_ROOT = Path(__file__).resolve().parent.parent
from dotenv import load_dotenv
load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_ROOT / "secrets" / ".env", override=False)
try:
    from libs.keyvault.loader import load_keyvault_secrets
    load_keyvault_secrets()
except Exception:
    pass

from libs.cypher.prompt_config_queries import (
    CREATE_CONSTRAINT,
    CREATE_INDEX_NAME,
    UPSERT_SEED_PROMPT,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


SEED_PROMPTS: list[dict] = []


def _add(name: str, version: int, variable_path: str) -> None:
    """Resolve a prompt text from libs.prompts at import time."""
    parts = variable_path.rsplit(".", 1)
    mod = __import__(parts[0], fromlist=[parts[1]])
    text = getattr(mod, parts[1])
    SEED_PROMPTS.append({
        "name": name,
        "version": version,
        "system_prompt": text,
        "output_schema": "{}",
        "verification": False,
    })


_add("extraction", 1, "libs.prompts.extraction_v1.EXTRACTION_SYSTEM_V1")
_add("disambiguation", 1, "libs.prompts.disambiguation_v1.DISAMBIGUATION_SYSTEM_V1")
_add("episode_builder_system", 1, "libs.prompts.episode_builder_v1.EPISODE_BUILDER_SYSTEM_V1")
_add("episode_builder_task", 1, "libs.prompts.episode_builder_v1.EPISODE_BUILDER_TASK_V1")
_add("episode_consolidation_system", 1, "libs.prompts.episode_builder_v1.EPISODE_CONSOLIDATION_SYSTEM_V1")
_add("episode_consolidation_task", 1, "libs.prompts.episode_builder_v1.EPISODE_CONSOLIDATION_TASK_V1")
_add("encounter_classify", 1, "libs.prompts.encounter_classify_v1.ENCOUNTER_CLASSIFY_SYSTEM_V1")
_add("anchor_domain_review", 1, "libs.prompts.anchor_domain_review_v1.ANCHOR_DOMAIN_REVIEW_V1")
_add("exclusion_detect", 1, "libs.prompts.exclusion_detect_v1.EXCLUSION_DETECT_SYSTEM_V1")
_add("label_verification", 2, "libs.prompts.label_verification_v2.LABEL_VERIFICATION_V2")
_add("label_disambiguation", 1, "libs.prompts.label_disambiguation_v1.LABEL_DISAMBIGUATION_V1")


def main() -> None:
    from neo4j import GraphDatabase

    # PromptConfig nodes belong in the Knowledge Graph (AI system config, not patient data)
    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", os.getenv("NEO4J_USER", os.getenv("NEO4J_USERNAME", "neo4j")))
    password = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD", "password"))

    driver = GraphDatabase.driver(uri, auth=(user, password))

    with driver.session() as session:
        session.run(CREATE_CONSTRAINT)
        session.run(CREATE_INDEX_NAME)
        logger.info("Constraints & indexes ensured.")

    seeded = 0
    for prompt in SEED_PROMPTS:
        with driver.session() as session:
            result = session.run(
                UPSERT_SEED_PROMPT,
                id=str(uuid.uuid4()),
                name=prompt["name"],
                version=prompt["version"],
                system_prompt=prompt["system_prompt"],
                output_schema=prompt["output_schema"],
                verification=prompt["verification"],
                few_shot_examples="[]",
            ).single()
            source = result["source"] if result else "unknown"
            action = "created" if source == "seed" else "skipped (user-edited)"
            logger.info("  %s v%d — %s", prompt["name"], prompt["version"], action)
            seeded += 1

    driver.close()
    logger.info("Done. %d prompts processed.", seeded)


if __name__ == "__main__":
    main()
