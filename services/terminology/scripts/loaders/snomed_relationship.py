"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-B63973E7
  DI: DI-B4D56E92
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-B63973E7")

Phase 1d: Load SNOMED CT relationships into Neo4j.

Creates [:IS_A] for hierarchy and [:HAS_RELATIONSHIP] for defining
attributes (finding_site, causative_agent, etc.).

Sources:
  - sct2_Relationship_Snapshot_INT_*.txt  (International)
  - sct2_Relationship_UKCLSnapshot_*.txt  (UK Clinical)
"""

from __future__ import annotations

import logging
from pathlib import Path

from neo4j import AsyncDriver

from .base import BatchWriter, stream_rf2

logger = logging.getLogger(__name__)

IS_A_TYPE_ID = "116680003"

MERGE_IS_A = """
UNWIND $rows AS r
MATCH (src:Concept {id: r.source_id})
MATCH (dst:Concept {id: r.dest_id})
MERGE (src)-[:IS_A]->(dst)
"""

MERGE_ATTRIBUTE = """
UNWIND $rows AS r
MATCH (src:Concept {id: r.source_id})
MATCH (dst:Concept {id: r.dest_id})
MERGE (src)-[:HAS_RELATIONSHIP {type_id: r.type_id, group: r.rel_group}]->(dst)
"""


async def load_relationships(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> int:
    """Stream sct2_Relationship and create IS_A + attribute relationships."""
    label = f"Relationship({filepath.name})"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        isa_writer = BatchWriter(session, MERGE_IS_A, batch_size, f"{label}/IS_A")
        attr_writer = BatchWriter(session, MERGE_ATTRIBUTE, batch_size, f"{label}/ATTR")
        for row in stream_rf2(filepath):
            if row["active"] != "1":
                continue
            rec = {
                "source_id": row["sourceId"],
                "dest_id": row["destinationId"],
                "type_id": row["typeId"],
                "rel_group": row["relationshipGroup"],
            }
            if row["typeId"] == IS_A_TYPE_ID:
                await isa_writer.add(rec)
            else:
                await attr_writer.add(rec)
        isa_count = await isa_writer.finish()
        attr_count = await attr_writer.finish()
        return isa_count + attr_count
