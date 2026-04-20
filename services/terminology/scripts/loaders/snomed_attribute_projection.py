"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-B63973E7
  DI: DI-B4D56E92
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-B63973E7")

Phase 3: Materialize readable SNOMED attribute relationships.

This projects generic (:Concept)-[:HAS_RELATIONSHIP {type_id, group}]->(:Concept)
edges into stable, query-friendly relationship types based on typeId.

Key lab-domain relationships added (for observable/procedure/finding traversal):

    HAS_COMPONENT  (246093002) — procedure -[HAS_COMPONENT]-> observable_entity
        e.g. "MCH determination (procedure)" -> "MCH (observable entity)"

    INTERPRETS     (363713009) — finding -[INTERPRETS]-> observable_entity
        e.g. "Finding of MCH level (finding)" -> "MCH (observable entity)"

    HAS_ASSOCIATED_FINDING (246090004) — concept -[HAS_ASSOCIATED_FINDING]-> finding
        links procedures and situations to their associated findings.

These three enable the /concepts/{id}/related endpoint to navigate the full
procedure <-> observable_entity <-> finding family for any lab test.
"""

from __future__ import annotations

import logging
import re

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

TYPE_ID_TO_REL = {
    "363698007": "HAS_FINDING_SITE",
    "116676008": "HAS_ASSOCIATED_MORPHOLOGY",
    "246075003": "HAS_CAUSATIVE_AGENT",
    "246112005": "HAS_SEVERITY",
    "263502005": "HAS_CLINICAL_COURSE",
    "246456000": "HAS_EPISODICITY",
    "246454002": "HAS_OCCURRENCE",
    "370135005": "HAS_PATHOLOGICAL_PROCESS",
    "408731000": "HAS_TEMPORAL_CONTEXT",
    "408732007": "HAS_SUBJECT_RELATIONSHIP_CONTEXT",
    "408729009": "HAS_FINDING_CONTEXT",
    "363589002": "HAS_ASSOCIATED_PROCEDURE",
    "260686004": "HAS_METHOD",
    "363704007": "HAS_PROCEDURE_SITE",
    "272741003": "HAS_LATERALITY",
    "260507000": "HAS_ACCESS",
    "424226004": "HAS_USING_DEVICE",
    "363701004": "HAS_DIRECT_SUBSTANCE",
    "411116001": "HAS_DOSE_FORM",
    "127489000": "HAS_ACTIVE_INGREDIENT",
    # --- Lab-domain family relationships ---
    # Enables: procedure <-> observable_entity <-> finding navigation
    "246093002": "HAS_COMPONENT",  # procedure -[HAS_COMPONENT]-> observable_entity
    "363713009": "INTERPRETS",  # finding -[INTERPRETS]-> observable_entity
    "246090004": "HAS_ASSOCIATED_FINDING",  # concept -[HAS_ASSOCIATED_FINDING]-> finding
}

REL_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _projection_cypher(rel_type: str) -> str:
    if not REL_TYPE_RE.match(rel_type):
        raise ValueError(f"Invalid projected relationship type: {rel_type}")
    return f"""
MATCH (src:Concept)-[r:HAS_RELATIONSHIP]->(dst:Concept)
WHERE r.type_id = $type_id
MERGE (src)-[m:{rel_type}]->(dst)
SET m.relationship_group = r.group,
    m.source_type_id = r.type_id
"""


async def load_inferred_attribute_relationships(driver: AsyncDriver) -> int:
    """Project selected SNOMED attribute typeIds into typed relationships."""
    logger.info("AttributeProjection: starting")
    total_created = 0

    async with driver.session() as session:
        for type_id, rel_type in TYPE_ID_TO_REL.items():
            cypher = _projection_cypher(rel_type)
            result = await session.run(cypher, type_id=type_id)
            summary = await result.consume()
            created = summary.counters.relationships_created
            total_created += created
            logger.info(
                "AttributeProjection: %s (%s) created %d",
                rel_type,
                type_id,
                created,
            )

    logger.info("AttributeProjection: complete (%d created)", total_created)
    return total_created
