"""Seed the three core PlanDefinitions and their ActivityDefinitions into Neo4j.

Usage:
    python -m scripts.seed_plan_definitions

Idempotent — uses MERGE on node IDs.

PlanDefinitions:
  1. gp-encounter-coding   — Primary care encounter NER extraction pipeline
  2. referral-assessment    — Referral document SBAR generation pipeline
  3. gold-training-audit    — Gold-standard NER training data pipeline

Each PlanDefinition has a sequence of Actions that reference ActivityDefinitions.
ActivityDefinitions map to subgraph IDs in the SubgraphRegistry.
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

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


ACTIVITY_DEFINITIONS = [
    {
        "id": "ad-extraction-llm",
        "resourceType": "ActivityDefinition",
        "name": "LLM Entity Extraction",
        "status": "active",
        "description": "Extract clinical entities from encounter text using LLM",
        "_subgraphId": "extraction",
        "dynamicValue": [
            {"path": "extraction_method", "expression": {"expression": "llm"}},
            {"path": "prompt_config_id", "expression": {"expression": ""}},
        ],
    },
    {
        "id": "ad-extraction-ner",
        "resourceType": "ActivityDefinition",
        "name": "NER Model Entity Extraction",
        "status": "active",
        "description": "Extract clinical entities from encounter text using trained NER model",
        "_subgraphId": "extraction",
        "dynamicValue": [
            {"path": "extraction_method", "expression": {"expression": "ner"}},
        ],
    },
    {
        "id": "ad-post-processing",
        "resourceType": "ActivityDefinition",
        "name": "Post-Processing Pipeline",
        "status": "active",
        "description": "9-layer post-processing: dedup, negation gate, disorder gate, etc.",
        "_subgraphId": "post_processing",
    },
    {
        "id": "ad-terminology",
        "resourceType": "ActivityDefinition",
        "name": "Terminology Resolution",
        "status": "active",
        "description": "Resolve extracted entities to SNOMED CT codes via terminology API",
        "_subgraphId": "terminology",
    },
    {
        "id": "ad-tier-classify",
        "resourceType": "ActivityDefinition",
        "name": "Tier Classification",
        "status": "active",
        "description": "Three-tier confidence classification for HITL routing",
        "_subgraphId": "tier_classify",
    },
    {
        "id": "ad-verification",
        "resourceType": "ActivityDefinition",
        "name": "Big-Model Verification",
        "status": "active",
        "description": "Verify extraction quality using a larger LLM with retry loop",
        "_subgraphId": "verification",
        "dynamicValue": [
            {"path": "model_tier", "expression": {"expression": "big"}},
            {"path": "max_retries", "expression": {"expression": "2"}},
            {"path": "confidence_threshold", "expression": {"expression": "0.8"}},
        ],
    },
    {
        "id": "ad-persist-patient",
        "resourceType": "ActivityDefinition",
        "name": "Persist to Patient Graph",
        "status": "active",
        "description": "Write coded entities and documents to patient graph",
        "_subgraphId": "persist",
        "dynamicValue": [
            {"path": "output_target", "expression": {"expression": "patient_graph"}},
        ],
    },
    {
        "id": "ad-persist-training",
        "resourceType": "ActivityDefinition",
        "name": "Persist to Gold Training",
        "status": "active",
        "description": "Write verified entities to gold training dataset",
        "_subgraphId": "persist",
        "dynamicValue": [
            {"path": "output_target", "expression": {"expression": "gold_training"}},
        ],
    },
    {
        "id": "ad-surface-form-validation",
        "resourceType": "ActivityDefinition",
        "name": "Surface Form Validation",
        "status": "active",
        "description": "Validate SNOMED mapping against extracted surface forms and create review tasks for low-confidence mismatches",
        "_subgraphId": "surface_form_validation",
        "dynamicValue": [
            {"path": "surface_form_validation_threshold", "expression": {"expression": "0.9"}},
        ],
    },
    {
        "id": "ad-anchor-detect",
        "resourceType": "ActivityDefinition",
        "name": "Anchor Detection",
        "status": "active",
        "description": "Detect cancer pathway anchor terms in coded entities",
        "_subgraphId": "anchor_detect",
    },
    {
        "id": "ad-episode-build",
        "resourceType": "ActivityDefinition",
        "name": "Episode Builder",
        "status": "active",
        "description": "Construct episodes of care from temporal entity sequences",
        "_subgraphId": "episode_build",
    },
    {
        "id": "ad-safety-net",
        "resourceType": "ActivityDefinition",
        "name": "Safety Netting",
        "status": "active",
        "description": "Detect missing follow-ups and safety netting signals",
        "_subgraphId": "safety_net",
    },
    {
        "id": "ad-quality-check",
        "resourceType": "ActivityDefinition",
        "name": "Quality Check",
        "status": "active",
        "description": "Detect quality issues and coding inconsistencies",
        "_subgraphId": "quality_check",
    },
    {
        "id": "ad-sbar",
        "resourceType": "ActivityDefinition",
        "name": "SBAR Generation",
        "status": "active",
        "description": "Generate SBAR clinical summary for referral documents",
        "_subgraphId": "sbar",
    },
    {
        "id": "ad-compliance",
        "resourceType": "ActivityDefinition",
        "name": "Compliance Evaluation",
        "status": "active",
        "description": "Evaluate referral compliance against pathway checklist",
        "_subgraphId": "compliance",
    },
    {
        "id": "ad-next-best-action",
        "resourceType": "ActivityDefinition",
        "name": "Next Best Action",
        "status": "active",
        "description": "Recommend clinical next-best-action based on patient state",
        "_subgraphId": "next_best_action",
    },
]


PLAN_DEFINITIONS = [
    {
        "id": "pd-gp-encounter-coding",
        "resourceType": "PlanDefinition",
        "name": "GP Encounter Coding",
        "status": "active",
        "description": "Primary care encounter NER extraction, terminology resolution, and persistence. Triggers on new encounter data. Includes optional analytics (anchor detection, episode building, safety netting, quality checks).",
        "action": [
            {
                "id": "act-extract",
                "title": "Extract Entities",
                "_sequence": 0,
                "_subgraphId": "extraction",
                "trigger": [{"type": "data-changed", "name": "encounter-created"}],
                "definitionCanonical": "ActivityDefinition/ad-extraction-llm",
            },
            {
                "id": "act-post-process",
                "title": "Post-Process",
                "_sequence": 1,
                "_subgraphId": "post_processing",
                "definitionCanonical": "ActivityDefinition/ad-post-processing",
                "relatedAction": [{"actionId": "act-extract", "relationship": "after-end"}],
            },
            {
                "id": "act-terminology",
                "title": "Resolve Terminology",
                "_sequence": 2,
                "_subgraphId": "terminology",
                "definitionCanonical": "ActivityDefinition/ad-terminology",
                "relatedAction": [{"actionId": "act-post-process", "relationship": "after-end"}],
            },
            {
                "id": "act-tier-classify",
                "title": "Classify Tiers",
                "_sequence": 3,
                "_subgraphId": "tier_classify",
                "definitionCanonical": "ActivityDefinition/ad-tier-classify",
                "relatedAction": [{"actionId": "act-terminology", "relationship": "after-end"}],
            },
            {
                "id": "act-persist",
                "title": "Persist to Patient Graph",
                "_sequence": 4,
                "_subgraphId": "persist",
                "definitionCanonical": "ActivityDefinition/ad-persist-patient",
                "relatedAction": [{"actionId": "act-tier-classify", "relationship": "after-end"}],
            },
            {
                "id": "act-anchor",
                "title": "Detect Anchors",
                "_sequence": 5,
                "_subgraphId": "anchor_detect",
                "definitionCanonical": "ActivityDefinition/ad-anchor-detect",
                "relatedAction": [{"actionId": "act-persist", "relationship": "after-end"}],
            },
            {
                "id": "act-episode",
                "title": "Build Episodes",
                "_sequence": 6,
                "_subgraphId": "episode_build",
                "definitionCanonical": "ActivityDefinition/ad-episode-build",
                "relatedAction": [{"actionId": "act-anchor", "relationship": "after-end"}],
            },
            {
                "id": "act-safety-net",
                "title": "Safety Netting",
                "_sequence": 7,
                "_subgraphId": "safety_net",
                "definitionCanonical": "ActivityDefinition/ad-safety-net",
                "relatedAction": [{"actionId": "act-episode", "relationship": "after-end"}],
            },
            {
                "id": "act-quality",
                "title": "Quality Check",
                "_sequence": 8,
                "_subgraphId": "quality_check",
                "definitionCanonical": "ActivityDefinition/ad-quality-check",
                "relatedAction": [{"actionId": "act-safety-net", "relationship": "after-end"}],
            },
        ],
    },
    {
        "id": "pd-referral-assessment",
        "resourceType": "PlanDefinition",
        "name": "Referral Assessment",
        "status": "active",
        "description": "Referral document processing: extract entities, resolve terminology, check compliance against guidance graph, generate SBAR summary with next-best-action recommendation.",
        "action": [
            {
                "id": "act-ref-extract",
                "title": "Extract Entities",
                "_sequence": 0,
                "_subgraphId": "extraction",
                "trigger": [{"type": "data-changed", "name": "referral-received"}],
                "definitionCanonical": "ActivityDefinition/ad-extraction-llm",
            },
            {
                "id": "act-ref-post-process",
                "title": "Post-Process",
                "_sequence": 1,
                "_subgraphId": "post_processing",
                "definitionCanonical": "ActivityDefinition/ad-post-processing",
                "relatedAction": [{"actionId": "act-ref-extract", "relationship": "after-end"}],
            },
            {
                "id": "act-ref-terminology",
                "title": "Resolve Terminology",
                "_sequence": 2,
                "_subgraphId": "terminology",
                "definitionCanonical": "ActivityDefinition/ad-terminology",
                "relatedAction": [{"actionId": "act-ref-post-process", "relationship": "after-end"}],
            },
            {
                "id": "act-ref-compliance",
                "title": "Compliance Check",
                "_sequence": 3,
                "_subgraphId": "compliance",
                "definitionCanonical": "ActivityDefinition/ad-compliance",
                "relatedAction": [{"actionId": "act-ref-terminology", "relationship": "after-end"}],
            },
            {
                "id": "act-ref-sbar",
                "title": "Generate SBAR",
                "_sequence": 4,
                "_subgraphId": "sbar",
                "definitionCanonical": "ActivityDefinition/ad-sbar",
                "relatedAction": [{"actionId": "act-ref-compliance", "relationship": "after-end"}],
            },
            {
                "id": "act-ref-nba",
                "title": "Next Best Action",
                "_sequence": 5,
                "_subgraphId": "next_best_action",
                "definitionCanonical": "ActivityDefinition/ad-next-best-action",
                "relatedAction": [{"actionId": "act-ref-sbar", "relationship": "after-end"}],
            },
            {
                "id": "act-ref-persist",
                "title": "Persist Results",
                "_sequence": 6,
                "_subgraphId": "persist",
                "definitionCanonical": "ActivityDefinition/ad-persist-patient",
                "relatedAction": [{"actionId": "act-ref-nba", "relationship": "after-end"}],
            },
        ],
    },
    {
        "id": "pd-gold-training-audit",
        "resourceType": "PlanDefinition",
        "name": "Gold Training Data",
        "status": "active",
        "description": "Gold-standard NER training pipeline: extract with LLM, verify with big model, persist verified results as gold training labels.",
        "action": [
            {
                "id": "act-gold-extract",
                "title": "Extract Entities (LLM)",
                "_sequence": 0,
                "_subgraphId": "extraction",
                "trigger": [{"type": "data-changed", "name": "training-run-requested"}],
                "definitionCanonical": "ActivityDefinition/ad-extraction-llm",
            },
            {
                "id": "act-gold-post-process",
                "title": "Post-Process",
                "_sequence": 1,
                "_subgraphId": "post_processing",
                "definitionCanonical": "ActivityDefinition/ad-post-processing",
                "relatedAction": [{"actionId": "act-gold-extract", "relationship": "after-end"}],
            },
            {
                "id": "act-gold-verify",
                "title": "Big-Model Verification",
                "_sequence": 2,
                "_subgraphId": "verification",
                "definitionCanonical": "ActivityDefinition/ad-verification",
                "relatedAction": [{"actionId": "act-gold-post-process", "relationship": "after-end"}],
            },
            {
                "id": "act-gold-terminology",
                "title": "Resolve Terminology",
                "_sequence": 3,
                "_subgraphId": "terminology",
                "definitionCanonical": "ActivityDefinition/ad-terminology",
                "relatedAction": [{"actionId": "act-gold-verify", "relationship": "after-end"}],
            },
            {
                "id": "act-gold-persist",
                "title": "Persist Gold Labels",
                "_sequence": 5,
                "_subgraphId": "persist",
                "definitionCanonical": "ActivityDefinition/ad-persist-training",
                "relatedAction": [{"actionId": "act-gold-surface-form-validation", "relationship": "after-end"}],
            },
            {
                "id": "act-gold-surface-form-validation",
                "title": "Surface Form Validation",
                "_sequence": 4,
                "_subgraphId": "surface_form_validation",
                "definitionCanonical": "ActivityDefinition/ad-surface-form-validation",
                "relatedAction": [{"actionId": "act-gold-terminology", "relationship": "after-end"}],
            },
        ],
    },
]


def _to_ui_format(pd_def: dict) -> dict:
    """Convert a FHIR PlanDefinition to the UI-friendly format expected by the pathway builder.

    The UI expects:
    - actions: [{id, subgraphId, label, position: {x, y}, config: {...}}]
    - edges: [{source, target}]
    - trigger: {event, description}

    This keeps the FHIR `action` array intact for the WorkflowEngine,
    and adds the UI properties alongside it.
    """
    fhir_actions = pd_def.get("action", [])
    ui_actions = []
    ui_edges = []

    for i, act in enumerate(fhir_actions):
        trigger = (act.get("trigger") or [{}])[0]
        trigger_event = trigger.get("name", "")
        definition_ref = act.get("definitionCanonical", "")
        activity_id = definition_ref.split("/")[-1] if definition_ref else ""

        ad_lookup = {a["id"]: a for a in ACTIVITY_DEFINITIONS}
        ad = ad_lookup.get(activity_id, {})
        dv = ad.get("dynamicValue", [])
        config = {}
        for v in dv:
            path = v.get("path", "")
            expr = v.get("expression", {}).get("expression", "")
            if path == "extraction_method":
                config["extractionMethod"] = expr
            elif path == "output_target":
                config["outputTarget"] = expr
            elif path == "model_tier":
                config["modelTier"] = expr
            elif path == "max_retries":
                config["maxRetries"] = int(expr) if expr.isdigit() else 2
            elif path == "confidence_threshold":
                try:
                    config["confidenceThreshold"] = float(expr)
                except ValueError:
                    pass

        ui_actions.append({
            "id": act["id"],
            "subgraphId": act.get("_subgraphId", ""),
            "label": act.get("title", act.get("_subgraphId", "")),
            "position": {"x": 250, "y": 80 + i * 120},
            "config": config,
        })

        for rel in act.get("relatedAction", []):
            source_id = rel.get("actionId", "")
            if source_id:
                ui_edges.append({"source": source_id, "target": act["id"]})

    result = dict(pd_def)
    result["actions"] = ui_actions
    result["edges"] = ui_edges

    first_trigger = {}
    for act in fhir_actions:
        triggers = act.get("trigger", [])
        if triggers:
            t = triggers[0]
            first_trigger = {"event": t.get("name", ""), "type": t.get("type", "")}
            break
    if first_trigger:
        result["trigger"] = first_trigger

    return result


UPSERT_ACTIVITY = """
MERGE (ad:ActivityDefinition {id: $id})
SET ad.rawJson = $raw,
    ad.name = $name,
    ad.status = $status,
    ad.subgraphId = $subgraph_id,
    ad.dynamicValues = $dynamic_values,
    ad.isGlobal = true
"""

UPSERT_PLAN = """
MERGE (pd:PlanDefinition {id: $id})
SET pd.rawJson = $raw,
    pd.name = $name,
    pd.status = $status,
    pd.isGlobal = true
"""

CLEAR_ACTIONS = """
MATCH (pd:PlanDefinition {id: $id})-[r:HAS_ACTION]->(a:Action)
DETACH DELETE a
"""

CREATE_ACTION = """
MATCH (pd:PlanDefinition {id: $plan_id})
CREATE (pd)-[:HAS_ACTION]->(a:Action {
  id: $action_id,
  trigger_type: $trigger_type,
  trigger_name: $trigger_name,
  condition: $condition,
  sequence: $sequence,
  subgraphId: $subgraph_id,
  relatedActions: $related_actions
})
"""

LINK_ACTIVITY = """
MATCH (a:Action {id: $action_id})
MATCH (ad:ActivityDefinition {id: $activity_id})
MERGE (a)-[:USES_DEFINITION]->(ad)
"""


COUNT_PLANS = "MATCH (pd:PlanDefinition) RETURN count(pd) AS cnt"


def seed_with_client(client) -> None:
    """Seed PlanDefinitions using an existing KnowledgeGraphClient (for startup hooks).

    Only seeds when no PlanDefinitions exist in Neo4j, to avoid
    overwriting user-modified pipelines.
    """
    try:
        client.run("CREATE CONSTRAINT plan_def_id IF NOT EXISTS FOR (pd:PlanDefinition) REQUIRE pd.id IS UNIQUE")
        client.run("CREATE CONSTRAINT activity_def_id IF NOT EXISTS FOR (ad:ActivityDefinition) REQUIRE ad.id IS UNIQUE")
        client.run("CREATE CONSTRAINT action_id IF NOT EXISTS FOR (a:Action) REQUIRE a.id IS UNIQUE")

        result = client.run(COUNT_PLANS)
        existing = result[0]["cnt"] if result else 0
        if existing > 0:
            logger.info("[Seed] Skipped — %d PlanDefinition(s) already present.", existing)
            return

        for ad in ACTIVITY_DEFINITIONS:
            dv = ad.get("dynamicValue", [])
            dv_json = json.dumps({v["path"]: v.get("expression", {}).get("expression") for v in dv}) if dv else None
            client.run(
                UPSERT_ACTIVITY,
                id=ad["id"], raw=json.dumps(ad), name=ad["name"],
                status=ad["status"], subgraph_id=ad.get("_subgraphId", ""),
                dynamic_values=dv_json,
            )

        for pd in PLAN_DEFINITIONS:
            ui_pd = _to_ui_format(pd)
            client.run(UPSERT_PLAN, id=pd["id"], raw=json.dumps(ui_pd), name=pd["name"], status=pd["status"])
            client.run(CLEAR_ACTIONS, id=pd["id"])
            for action in pd.get("action", []):
                trigger = (action.get("trigger") or [{}])[0]
                definition_ref = action.get("definitionCanonical", "")
                related_ids = [r.get("actionId", "") for r in (action.get("relatedAction") or [])]
                client.run(
                    CREATE_ACTION,
                    plan_id=pd["id"], action_id=action["id"],
                    trigger_type=trigger.get("type", ""), trigger_name=trigger.get("name", ""),
                    condition=None, sequence=action.get("_sequence", 0),
                    subgraph_id=action.get("_subgraphId", ""),
                    related_actions=related_ids,
                )
                if definition_ref:
                    activity_id = definition_ref.split("/")[-1]
                    client.run(LINK_ACTIVITY, action_id=action["id"], activity_id=activity_id)

        logger.info("[Seed] %d ActivityDefinitions, %d PlanDefinitions seeded.", len(ACTIVITY_DEFINITIONS), len(PLAN_DEFINITIONS))
    except Exception as exc:
        logger.warning("[Seed] PlanDefinition seed failed (non-fatal): %s", exc)


def main() -> None:
    from neo4j import GraphDatabase

    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", os.getenv("NEO4J_USER", "neo4j"))
    password = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD", "password"))

    driver = GraphDatabase.driver(uri, auth=(user, password))

    with driver.session() as session:
        session.run("CREATE CONSTRAINT plan_def_id IF NOT EXISTS FOR (pd:PlanDefinition) REQUIRE pd.id IS UNIQUE")
        session.run("CREATE CONSTRAINT activity_def_id IF NOT EXISTS FOR (ad:ActivityDefinition) REQUIRE ad.id IS UNIQUE")
        session.run("CREATE CONSTRAINT action_id IF NOT EXISTS FOR (a:Action) REQUIRE a.id IS UNIQUE")
    logger.info("Constraints ensured.")

    with driver.session() as session:
        result = session.run(COUNT_PLANS).single()
        existing = result["cnt"] if result else 0
    if existing > 0:
        logger.info("Skipped — %d PlanDefinition(s) already present.", existing)
        driver.close()
        return

    for ad in ACTIVITY_DEFINITIONS:
        dv = ad.get("dynamicValue", [])
        dv_json = json.dumps({v["path"]: v.get("expression", {}).get("expression") for v in dv}) if dv else None
        with driver.session() as session:
            session.run(
                UPSERT_ACTIVITY,
                id=ad["id"],
                raw=json.dumps(ad),
                name=ad["name"],
                status=ad["status"],
                subgraph_id=ad.get("_subgraphId", ""),
                dynamic_values=dv_json,
            )
        logger.info("  ActivityDefinition: %s", ad["name"])

    for pd in PLAN_DEFINITIONS:
        ui_pd = _to_ui_format(pd)
        with driver.session() as session:
            session.run(UPSERT_PLAN, id=pd["id"], raw=json.dumps(ui_pd), name=pd["name"], status=pd["status"])
            session.run(CLEAR_ACTIONS, id=pd["id"])

        for action in pd.get("action", []):
            trigger = (action.get("trigger") or [{}])[0]
            trigger_type = trigger.get("type", "")
            trigger_name = trigger.get("name", "")
            definition_ref = action.get("definitionCanonical", "")
            related_ids = [r.get("actionId", "") for r in (action.get("relatedAction") or [])]

            with driver.session() as session:
                session.run(
                    CREATE_ACTION,
                    plan_id=pd["id"],
                    action_id=action["id"],
                    trigger_type=trigger_type,
                    trigger_name=trigger_name,
                    condition=None,
                    sequence=action.get("_sequence", 0),
                    subgraph_id=action.get("_subgraphId", ""),
                    related_actions=related_ids,
                )
                if definition_ref:
                    activity_id = definition_ref.split("/")[-1]
                    session.run(LINK_ACTIVITY, action_id=action["id"], activity_id=activity_id)

        logger.info("  PlanDefinition: %s (%d actions)", pd["name"], len(pd.get("action", [])))

    driver.close()
    logger.info("Done. %d ActivityDefinitions, %d PlanDefinitions seeded.", len(ACTIVITY_DEFINITIONS), len(PLAN_DEFINITIONS))


if __name__ == "__main__":
    main()
