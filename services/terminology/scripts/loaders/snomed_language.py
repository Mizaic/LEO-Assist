"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-B63973E7
  DI: DI-B4D56E92
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-B63973E7")

Phase 1c: Load SNOMED CT Language refset into Neo4j.

Sets acceptability (preferred/acceptable) on [:DESCRIBES] relationships
by matching the Language refset's referencedComponentId to Term.id.

Sources:
  - der2_cRefset_LanguageUKCLSnapshot-en_*.txt
  - der2_cRefset_LanguageUKEDSnapshot-en_*.txt
"""

from __future__ import annotations

import logging
from pathlib import Path

from neo4j import AsyncDriver

from .base import BatchWriter, stream_rf2

logger = logging.getLogger(__name__)

PREFERRED_ID = "900000000000548007"
ACCEPTABLE_ID = "900000000000549004"

SET_ACCEPTABILITY = """
UNWIND $rows AS r
MATCH (t:Term {id: r.desc_id})-[d:DESCRIBES]->(:Concept)
SET d.acceptability = r.acceptability
"""


def _acceptability_label(accept_id: str) -> str:
    if accept_id == PREFERRED_ID:
        return "preferred"
    if accept_id == ACCEPTABLE_ID:
        return "acceptable"
    return accept_id


async def load_language_refset(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> int:
    """Stream Language refset and set acceptability on [:DESCRIBES]."""
    label = f"Language({filepath.name})"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        writer = BatchWriter(session, SET_ACCEPTABILITY, batch_size, label)
        for row in stream_rf2(filepath):
            if row["active"] != "1":
                continue
            await writer.add(
                {
                    "desc_id": row["referencedComponentId"],
                    "acceptability": _acceptability_label(row["acceptabilityId"]),
                }
            )
        return await writer.finish()
