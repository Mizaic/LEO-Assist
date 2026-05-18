"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-4D608335
  DI: DI-760F5FB7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4D608335")

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

# refsetId for the SNOMED CT to OPCS-4 procedural map (UK Clinical refset)
OPCS4_REFSET_ID = "1126491000000109"

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

MERGE_OPCS4_MAP = """
UNWIND $rows AS r
MERGE (op:OpcsCode {code: r.map_target})
WITH op, r
MERGE (c:Concept {id: r.concept_id})
MERGE (c)-[:MAPS_TO_OPCS4]->(op)
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
    refset_filter: str | None = None,
) -> int:
    """Stream SimpleMap refset and create Read code mappings.

    The SNOMED SimpleMap file contains rows for many refsets in a single
    file (CTV3, OPCS-4, ICD-O, etc.). When `refset_filter` is provided
    only rows whose refsetId matches are loaded as ReadCode targets;
    callers loading other classifications (e.g. OPCS-4 via
    `load_opcs4_map`) should restrict this loader to CTV3.
    """
    label = f"SimpleMap({filepath.name})"
    logger.info("%s: starting (refset_filter=%s)", label, refset_filter or "ALL")
    async with driver.session() as session:
        writer = BatchWriter(session, MERGE_READ_MAP, batch_size, label)
        for row in stream_rf2(filepath):
            if row["active"] != "1":
                continue
            if refset_filter and row.get("refsetId") != refset_filter:
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


async def load_opcs4_map(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> int:
    """Stream a SimpleMap refset and create SNOMED -> OPCS-4 mappings.

    Filters on `OPCS4_REFSET_ID` so this function is safe to run against
    the same file used by `load_simple_map` for CTV3. OpcsCode nodes are
    MERGEd on `code` so titles already loaded by `opcs4.load_opcs4`
    survive (and bare nodes left here are titled later when the OPCS-4
    reference data loader runs).
    """
    label = f"OPCS4Map({filepath.name})"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        writer = BatchWriter(session, MERGE_OPCS4_MAP, batch_size, label)
        for row in stream_rf2(filepath):
            if row["active"] != "1":
                continue
            if row.get("refsetId") != OPCS4_REFSET_ID:
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
