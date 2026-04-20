"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-B63973E7
  DI: DI-B4D56E92
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-B63973E7")

Phase 1a: Load SNOMED CT concepts into Neo4j.

Sources:
  - sct2_Concept_Snapshot_INT_*.txt  (International)
  - sct2_Concept_UKCLSnapshot_*.txt  (UK Clinical)
"""

from __future__ import annotations

import logging
from pathlib import Path

from neo4j import AsyncDriver

from .base import BatchWriter, stream_rf2

logger = logging.getLogger(__name__)

MERGE_CONCEPT = """
UNWIND $rows AS r
MERGE (c:Concept {id: r.id})
SET c.active = (r.active = '1'),
    c.module_id = r.module_id,
    c.definition_status_id = r.def_status,
    c.effective_time = r.effective_time
"""


async def load_concepts(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> int:
    """Stream sct2_Concept file and MERGE into (:Concept) nodes."""
    label = f"Concept({filepath.name})"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        writer = BatchWriter(session, MERGE_CONCEPT, batch_size, label)
        for row in stream_rf2(filepath):
            await writer.add(
                {
                    "id": row["id"],
                    "active": row["active"],
                    "module_id": row["moduleId"],
                    "def_status": row["definitionStatusId"],
                    "effective_time": row["effectiveTime"],
                }
            )
        return await writer.finish()
