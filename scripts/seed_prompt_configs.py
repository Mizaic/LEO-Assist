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
from typing import Any
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


def _add(
    name: str,
    version: int,
    variable_path: str,
    output_schema: str = "{}",
    few_shot_examples: list[dict] | None = None,
    max_few_shot: int = 20,
    description: str = "",
) -> None:
    """Resolve a prompt text from libs.prompts at import time."""
    parts = variable_path.rsplit(".", 1)
    mod = __import__(parts[0], fromlist=[parts[1]])
    text = getattr(mod, parts[1])
    SEED_PROMPTS.append({
        "name": name,
        "version": version,
        "description": description,
        "system_prompt": text,
        "output_schema": output_schema,
        "verification": False,
        "few_shot_examples": few_shot_examples or [],
        "max_few_shot": max_few_shot,
    })


# ── Extraction — structured output schema + example library ─────────────────
from libs.prompts.extraction_output_schema import EXTRACTION_OUTPUT_SCHEMA
from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES

_add(
    "extraction", 1,
    "libs.prompts.extraction_v1.EXTRACTION_SYSTEM_V1",
    output_schema=json.dumps(EXTRACTION_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_ex_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(EXTRACTION_EXAMPLES)
    ],
    max_few_shot=20,
    description=(
        "Extracts SNOMED CT-codable clinical entities from de-identified GP "
        "consultation text. Produces surface forms, semantic tags, assertions, "
        "and structured measurement fields for observable entities and staging scales."
    ),
)

# ── Disambiguation ────────────────────────────────────────────────────────────
from libs.prompts.disambiguation_output_schema import DISAMBIGUATION_OUTPUT_SCHEMA
from libs.prompts.disambiguation_examples import DISAMBIGUATION_EXAMPLES

_add(
    "disambiguation", 1,
    "libs.prompts.disambiguation_v1.DISAMBIGUATION_SYSTEM_V1",
    output_schema=json.dumps(DISAMBIGUATION_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_disambig_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(DISAMBIGUATION_EXAMPLES)
    ],
    max_few_shot=20,
    description="Disambiguates extracted entities against candidate SNOMED concepts.",
)

# ── Episode builder ────────────────────────────────────────────────────────────
from libs.prompts.episode_builder_output_schema import (
    EPISODE_BUILDER_OUTPUT_SCHEMA,
    EPISODE_CONSOLIDATION_OUTPUT_SCHEMA,
)
from libs.prompts.episode_builder_examples import EPISODE_BUILDER_EXAMPLES

_builder_examples = [
    {
        "id": f"seed_epbuild_{i:03d}",
        "input": ex["input"],
        "output": ex["output"],
        "deidentified": True,
        "category": ex.get("category", ""),
        "model_scope": ex.get("model_scope", "any"),
        "description": ex.get("description", ""),
        "core": bool(ex.get("core", False)),
    }
    for i, ex in enumerate(EPISODE_BUILDER_EXAMPLES)
    if ex.get("category", "").startswith("episode:")
]
_consolidation_examples = [
    {
        "id": f"seed_epcons_{i:03d}",
        "input": ex["input"],
        "output": ex["output"],
        "deidentified": True,
        "category": ex.get("category", ""),
        "model_scope": ex.get("model_scope", "any"),
        "description": ex.get("description", ""),
        "core": bool(ex.get("core", False)),
    }
    for i, ex in enumerate(EPISODE_BUILDER_EXAMPLES)
    if ex.get("category", "").startswith("consolidation:")
]

_add(
    "episode_builder_system", 1,
    "libs.prompts.episode_builder_v1.EPISODE_BUILDER_SYSTEM_V1",
    output_schema=json.dumps(EPISODE_BUILDER_OUTPUT_SCHEMA),
    few_shot_examples=_builder_examples,
    max_few_shot=20,
    description="System role for the episode builder — groups coded entities into clinical episodes.",
)
_add(
    "episode_builder_task", 1,
    "libs.prompts.episode_builder_v1.EPISODE_BUILDER_TASK_V1",
    output_schema=json.dumps(EPISODE_BUILDER_OUTPUT_SCHEMA),
    few_shot_examples=_builder_examples,
    max_few_shot=20,
    description="Task instructions for the episode builder — structures entities per clinical encounter.",
)
_add(
    "episode_consolidation_system", 1,
    "libs.prompts.episode_builder_v1.EPISODE_CONSOLIDATION_SYSTEM_V1",
    output_schema=json.dumps(EPISODE_CONSOLIDATION_OUTPUT_SCHEMA),
    few_shot_examples=_consolidation_examples,
    max_few_shot=20,
    description="System role for cross-encounter episode consolidation.",
)
_add(
    "episode_consolidation_task", 1,
    "libs.prompts.episode_builder_v1.EPISODE_CONSOLIDATION_TASK_V1",
    output_schema=json.dumps(EPISODE_CONSOLIDATION_OUTPUT_SCHEMA),
    few_shot_examples=_consolidation_examples,
    max_few_shot=20,
    description="Task instructions for consolidating episodes across multiple encounters.",
)

# ── Encounter classify ─────────────────────────────────────────────────────────
from libs.prompts.encounter_classify_output_schema import ENCOUNTER_CLASSIFY_OUTPUT_SCHEMA
from libs.prompts.encounter_classify_examples import ENCOUNTER_CLASSIFY_EXAMPLES

_add(
    "encounter_classify", 1,
    "libs.prompts.encounter_classify_v1.ENCOUNTER_CLASSIFY_SYSTEM_V1",
    output_schema=json.dumps(ENCOUNTER_CLASSIFY_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_encclass_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(ENCOUNTER_CLASSIFY_EXAMPLES)
    ],
    max_few_shot=20,
    description="Classifies encounters by type and clinical tier before extraction.",
)

# ── Anchor domain review ───────────────────────────────────────────────────────
from libs.prompts.anchor_domain_review_output_schema import ANCHOR_DOMAIN_REVIEW_OUTPUT_SCHEMA
from libs.prompts.anchor_domain_review_examples import ANCHOR_DOMAIN_REVIEW_EXAMPLES

_add(
    "anchor_domain_review", 1,
    "libs.prompts.anchor_domain_review_v1.ANCHOR_DOMAIN_REVIEW_V1",
    output_schema=json.dumps(ANCHOR_DOMAIN_REVIEW_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_anchor_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(ANCHOR_DOMAIN_REVIEW_EXAMPLES)
    ],
    max_few_shot=20,
    description="Reviews anchor training records: assigns clinical domains, validates SNOMED concepts, generates medspaCy TargetRules.",
)

# ── Exclusion detect ───────────────────────────────────────────────────────────
from libs.prompts.exclusion_detect_output_schema import EXCLUSION_DETECT_OUTPUT_SCHEMA
from libs.prompts.exclusion_detect_examples import EXCLUSION_DETECT_EXAMPLES

_add(
    "exclusion_detect", 1,
    "libs.prompts.exclusion_detect_v1.EXCLUSION_DETECT_SYSTEM_V1",
    output_schema=json.dumps(EXCLUSION_DETECT_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_excl_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(EXCLUSION_DETECT_EXAMPLES)
    ],
    max_few_shot=20,
    description="Classifies post-referral encounters as cancer_excluded / confirmed / still_investigating / pending_letter / not_relevant.",
)

# ── Label verification ─────────────────────────────────────────────────────────
from libs.prompts.label_verification_output_schema import LABEL_VERIFICATION_OUTPUT_SCHEMA
from libs.prompts.label_verification_examples import LABEL_VERIFICATION_EXAMPLES

_add(
    "label_verification", 2,
    "libs.prompts.label_verification_v2.LABEL_VERIFICATION_V2",
    output_schema=json.dumps(LABEL_VERIFICATION_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_labver_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(LABEL_VERIFICATION_EXAMPLES)
    ],
    max_few_shot=20,
    description="Verifies extracted label quality against the source text before gold-label persistence.",
)

# ── Label disambiguation ───────────────────────────────────────────────────────
from libs.prompts.label_disambiguation_output_schema import LABEL_DISAMBIGUATION_OUTPUT_SCHEMA
from libs.prompts.label_disambiguation_examples import LABEL_DISAMBIGUATION_EXAMPLES

_add(
    "label_disambiguation", 1,
    "libs.prompts.label_disambiguation_v1.LABEL_DISAMBIGUATION_V1",
    output_schema=json.dumps(LABEL_DISAMBIGUATION_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": f"seed_labdis_{i:03d}",
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": True,
            "category": ex.get("category", ""),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", False)),
        }
        for i, ex in enumerate(LABEL_DISAMBIGUATION_EXAMPLES)
    ],
    max_few_shot=20,
    description="Disambiguates uncertain NER labels using context from the full encounter — resolves model disagreements.",
)

# ── NICE → Rules: guidance rule extraction ────────────────────────────────────
from libs.prompts.guidance_rule_extraction_output_schema import (
    GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA,
    GUIDANCE_RULE_EXTRACTION_EXAMPLES,
)

_add(
    "guidance_rule_extraction", 1,
    "libs.prompts.guidance_rule_extraction_v1.GUIDANCE_RULE_EXTRACTION_SYSTEM_V1",
    output_schema=json.dumps(GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA),
    few_shot_examples=[
        {
            "id": ex["id"],
            "input": ex["input"],
            "output": ex["output"],
            "deidentified": ex.get("deidentified", True),
            "category": ex.get("category", "guidance_rule_extraction"),
            "model_scope": ex.get("model_scope", "any"),
            "description": ex.get("description", ""),
            "core": bool(ex.get("core", True)),
        }
        for ex in GUIDANCE_RULE_EXTRACTION_EXAMPLES
    ],
    max_few_shot=4,
    description=(
        "Extracts patient-level clinical criteria (present / absent) from a single "
        "NICE recommendation to produce an AppropriatenessRule for bitmap matching. "
        "Part of the NICE \u2192 Rules AI pipeline — editable at runtime via /admin/prompts."
    ),
)


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
                description=prompt.get("description", ""),
                system_prompt=prompt["system_prompt"],
                output_schema=prompt["output_schema"],
                verification=prompt["verification"],
                few_shot_examples=json.dumps(prompt.get("few_shot_examples", [])),
                max_few_shot=int(prompt.get("max_few_shot", 20)),
            ).single()
            source = result["source"] if result else "unknown"
            action = "created" if source == "seed" else "skipped (user-edited)"
            n_examples = len(prompt.get("few_shot_examples", []))
            logger.info(
                "  %s v%d — %s (%d examples)",
                prompt["name"], prompt["version"], action, n_examples,
            )
            seeded += 1

    driver.close()
    logger.info("Done. %d prompts processed.", seeded)


if __name__ == "__main__":
    main()
