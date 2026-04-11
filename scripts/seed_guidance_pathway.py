"""Seed the NICE → Rules PlanDefinition pathway into Neo4j.

This creates the pathway that appears in /admin/pathways, showing the
NICE → AppropriatenessRule AI pipeline as a first-class editable workflow.

Usage:
    python -m scripts.seed_guidance_pathway

Idempotent — uses MERGE on the pathway name so re-running is safe.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_ROOT = Path(__file__).resolve().parent.parent
from dotenv import load_dotenv

load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_ROOT / "secrets" / ".env", override=False)
try:
    from libs.keyvault.loader import load_keyvault_secrets

    load_keyvault_secrets()
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ── Pathway definition ─────────────────────────────────────────────────────────
#
# Three steps reflecting the actual runtime:
#
#  1. guidance_rule_extraction — the LangGraph subgraph registered in the registry.
#     This handles: prompt loading, LLM consensus, Terminology API SNOMED coding.
#     It is per-recommendation; the generator iterates over all recs for the guideline.
#
#  2. nice_guideline_inspect — read-only view step (informational in the canvas;
#     actual Neo4j reads happen inside the generator service).
#
#  3. human_review_gate — the HITL step; rules sit in pending_review until a
#     human approves them at /admin/guidance.

_PATHWAY_NAME = "NICE Guideline → Appropriateness Rules"
_PATHWAY_ID = "nice-guidance-rule-pipeline-v1"

_PATHWAY_PAYLOAD = {
    "id": _PATHWAY_ID,
    "name": _PATHWAY_NAME,
    "status": "active",
    "description": (
        "Converts NICE guideline recommendations stored in Neo4j into "
        "SNOMED-coded AppropriatenessRules for bitmap patient matching. "
        "Uses dual-model AI consensus with the guidance_rule_extraction prompt "
        "(editable at /admin/prompts) and resolves clinical terms to SNOMED "
        "concepts via the Terminology API. All generated rules require human "
        "review before they are activated."
    ),
    "trigger": {
        "type": "admin-action",
        "event": "nice-rules-generate",
    },
    "actions": [
        {
            "id": "step_extract_criteria",
            "subgraphId": "guidance_rule_extraction",
            "label": "Extract Clinical Criteria (AI)",
            "nodeType": "action",
            "sequence": 1,
            "position": {"x": 160, "y": 200},
            "config": {
                "subgraphId": "guidance_rule_extraction",
                "label": "Extract Clinical Criteria (AI)",
                "description": (
                    "For each NICE recommendation: loads the guidance_rule_extraction "
                    "prompt from /admin/prompts, runs dual-model AI consensus to extract "
                    "patient criteria (findings/disorders) and the recommended action "
                    "(procedure), then resolves each term to a SNOMED concept via the "
                    "Terminology API."
                ),
                "inputSource": "knowledge_graph",
                "outputTarget": "knowledge_graph",
                "enableVerification": False,
                "maxRetries": 2,
                "timeout": 300,
                "promptConfigId": "",
                "promptConfigName": "guidance_rule_extraction",
                "params": {
                    "semantic_tags_criteria": [
                        "finding",
                        "disorder",
                        "observable entity",
                        "situation",
                    ],
                    "semantic_tags_action": ["procedure"],
                    "max_criteria_terms": 5,
                    "consensus_model_small": "aws:small",
                    "consensus_model_big": "aws:big",
                },
            },
        },
        {
            "id": "step_human_review",
            "subgraphId": "human_review_gate",
            "label": "Human Review (HITL)",
            "nodeType": "action",
            "sequence": 2,
            "position": {"x": 520, "y": 200},
            "config": {
                "subgraphId": "human_review_gate",
                "label": "Human Review (HITL)",
                "description": (
                    "All AI-generated rules are placed in pending_review status. "
                    "A clinician reviews each rule at /admin/guidance — approving "
                    "activates the rule and triggers bitmap recompilation; "
                    "rejecting discards the rule. Rules with a predecessor show "
                    "a diff view of what changed."
                ),
                "inputSource": "previous_step",
                "outputTarget": "knowledge_graph",
                "enableVerification": False,
                "maxRetries": 0,
                "timeout": 0,
                "params": {
                    "review_url": "/admin/guidance",
                    "rule_status_gate": "pending_review",
                },
            },
        },
        {
            "id": "step_compile_bitmap",
            "subgraphId": "rest_connector",
            "label": "Compile Bitmaps",
            "nodeType": "action",
            "sequence": 3,
            "position": {"x": 880, "y": 200},
            "config": {
                "subgraphId": "rest_connector",
                "label": "Compile Bitmaps",
                "description": (
                    "After human approval, POST /terminology/guidelines/compile "
                    "recompiles the active ruleset into compressed SNOMED bitmaps "
                    "stored in Redis. The evaluator then uses these bitmaps for "
                    "real-time patient matching."
                ),
                "inputSource": "previous_step",
                "outputTarget": "redis",
                "enableVerification": False,
                "maxRetries": 2,
                "timeout": 120,
                "params": {
                    "method": "POST",
                    "url": "${TERMINOLOGY_API_URL}/terminology/guidelines/compile",
                },
            },
        },
    ],
    "edges": [
        {"source": "step_extract_criteria", "target": "step_human_review"},
        {"source": "step_human_review", "target": "step_compile_bitmap"},
    ],
    "meta": {
        "seeded": True,
        "seededBy": "scripts/seed_guidance_pathway.py",
        "promptConfigName": "guidance_rule_extraction",
        "bitmapStore": "redis",
        "snomed_coding": "terminology_api",
    },
}

# ── Cypher ─────────────────────────────────────────────────────────────────────

_UPSERT_PATHWAY = """
MERGE (p:PlanDefinition {id: $id})
ON CREATE SET
    p.rawJson   = $raw_json,
    p.status    = $status,
    p.name      = $name,
    p.source    = 'seed',
    p.isGlobal  = true,
    p.createdAt = datetime(),
    p.updatedAt = datetime()
ON MATCH SET
    p.rawJson   = CASE WHEN coalesce(p.source, 'seed') = 'seed' THEN $raw_json  ELSE p.rawJson  END,
    p.status    = CASE WHEN coalesce(p.source, 'seed') = 'seed' THEN $status    ELSE p.status   END,
    p.name      = CASE WHEN coalesce(p.source, 'seed') = 'seed' THEN $name      ELSE p.name     END,
    p.updatedAt = datetime()
RETURN p.id AS id, coalesce(p.source, 'seed') AS source
"""


def main() -> None:
    from neo4j import GraphDatabase

    uri = os.getenv(
        "KNOWLEDGE_GRAPH_NEO4J_URI", os.getenv("NEO4J_URI", "bolt://localhost:7687")
    )
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", os.getenv("NEO4J_USER", "neo4j"))
    password = os.getenv(
        "KNOWLEDGE_GRAPH_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD", "password")
    )

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            result = session.run(
                _UPSERT_PATHWAY,
                id=_PATHWAY_PAYLOAD["id"],
                raw_json=json.dumps(_PATHWAY_PAYLOAD),
                status=_PATHWAY_PAYLOAD["status"],
                name=_PATHWAY_PAYLOAD["name"],
            )
            record = result.single()
            if record:
                source = record.get("source", "seed")
                action = (
                    "created"
                    if source == "seed"
                    else "skipped (user-edited — not overwritten)"
                )
                logger.info("  %s — %s", _PATHWAY_ID, action)
            else:
                logger.info("  %s — no record returned", _PATHWAY_ID)
    finally:
        driver.close()

    logger.info("Done. The pathway now appears in /admin/pathways.")
    logger.info(
        "Run 'python -m scripts.seed_prompt_configs' to ensure the "
        "guidance_rule_extraction PromptConfig is also seeded."
    )


if __name__ == "__main__":
    main()
