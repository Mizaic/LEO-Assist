"""
Phase 2: Load SNOMED CT map refsets into Neo4j.

ExtendedMap → (:Concept)-[:MAPS_TO_ICD10]->(:Icd10Code)
SimpleMap   → (:Concept)-[:MAPS_TO_READ]->(:ReadCode)

Sources (Snapshot):
  - der2_iisssccRefset_ExtendedMapSnapshot_INT_*.txt
  - der2_iisssciRefset_ExtendedMapUKCLSnapshot_*.txt
  - der2_sRefset_SimpleMapSnapshot_INT_*.txt
  - der2_sRefset_SimpleMapUKCLSnapshot_*.txt
"""

from __future__ import annotations

import logging
from pathlib import Path

from neo4j import AsyncDriver

from .base import BatchWriter, stream_rf2

logger = logging.getLogger(__name__)

# refsetIds that indicate ICD-10 target terminology
ICD10_REFSET_IDS = {
    "447562003",  # ICD-10 WHO (INT)
    "999002271000000101",  # ICD-10 5th ed UK
    "1126441000000105",  # ICD-10 5th ed UK (alt)
}

# refsetId for CTV3 simple map
CTV3_REFSET_ID = "900000000000497000"

MERGE_ICD10_MAP = """
UNWIND $rows AS r
MERGE (icd:Icd10Code {code: r.map_target})
MERGE (c:Concept {id: r.concept_id})
MERGE (c)-[m:MAPS_TO_ICD10]->(icd)
SET m.map_group = toInteger(r.map_group),
    m.map_priority = toInteger(r.map_priority),
    m.map_rule = r.map_rule,
    m.map_advice = r.map_advice
"""

MERGE_READ_MAP = """
UNWIND $rows AS r
MERGE (rd:ReadCode {code: r.map_target})
SET rd.version = 'ctv3'
WITH rd, r
MERGE (c:Concept {id: r.concept_id})
MERGE (c)-[:MAPS_TO_READ]->(rd)
"""


async def load_extended_map(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> int:
    """Stream ExtendedMap refset and create ICD-10 mappings."""
    label = f"ExtendedMap({filepath.name})"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        writer = BatchWriter(session, MERGE_ICD10_MAP, batch_size, label)
        for row in stream_rf2(filepath):
            if row["active"] != "1":
                continue
            if not row.get("mapTarget", "").strip():
                continue
            await writer.add(
                {
                    "concept_id": row["referencedComponentId"],
                    "map_target": row["mapTarget"].strip(),
                    "map_group": row.get("mapGroup", "1"),
                    "map_priority": row.get("mapPriority", "1"),
                    "map_rule": row.get("mapRule", ""),
                    "map_advice": row.get("mapAdvice", ""),
                }
            )
        return await writer.finish()


async def load_simple_map(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> int:
    """Stream SimpleMap refset and create Read code mappings."""
    label = f"SimpleMap({filepath.name})"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        writer = BatchWriter(session, MERGE_READ_MAP, batch_size, label)
        for row in stream_rf2(filepath):
            if row["active"] != "1":
                continue
            target = row.get("mapTarget", "").strip()
            if not target:
                continue
            await writer.add(
                {
                    "concept_id": row["referencedComponentId"],
                    "map_target": target,
                }
            )
        return await writer.finish()
