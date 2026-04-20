"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-B63973E7
  DI: DI-B4D56E92
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-B63973E7")

Phase 1b: Load SNOMED CT descriptions into Neo4j.

Sources:
  - sct2_Description_Snapshot-en_INT_*.txt  (International)
  - sct2_Description_UKCLSnapshot-en_*.txt  (UK Clinical)

Creates (:Term) nodes and [:DESCRIBES] relationships to (:Concept).
Sets FSN and semantic_tag on (:Concept) when the description is an FSN.
"""

from __future__ import annotations

import logging
from pathlib import Path

from neo4j import AsyncDriver

from .base import BatchWriter, normalize_term, stream_rf2
from libs.terminology.semantic_tag import normalise_semantic_tag

logger = logging.getLogger(__name__)

FSN_TYPE_ID = "900000000000003001"

MERGE_DESCRIPTION = """
UNWIND $rows AS r
MERGE (t:Term {id: r.desc_id})
SET t.surface_form = r.term,
    t.normalized_form = r.normalized,
    t.term_type = r.type_id,
    t.language_code = r.lang,
    t.active = true
WITH t, r
MERGE (c:Concept {id: r.concept_id})
MERGE (t)-[:DESCRIBES]->(c)
WITH c, r
WHERE r.type_id = $fsn_type_id
SET c.fsn = r.term,
    c.semantic_tag = r.semantic_tag
"""


def _extract_semantic_tag(fsn: str) -> str:
    if fsn.endswith(")"):
        start = fsn.rfind("(")
        if start > 0:
            return normalise_semantic_tag(fsn[start + 1 : -1])
    return "unknown"


async def load_descriptions(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> int:
    """Stream sct2_Description and create (:Term)-[:DESCRIBES]->(:Concept)."""
    label = f"Description({filepath.name})"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        writer = BatchWriter(
            session,
            MERGE_DESCRIPTION,
            batch_size,
            label,
            extra_params={"fsn_type_id": FSN_TYPE_ID},
        )
        for row in stream_rf2(filepath):
            if row["active"] != "1":
                continue
            term_text = row["term"]
            await writer.add(
                {
                    "desc_id": row["id"],
                    "concept_id": row["conceptId"],
                    "term": term_text,
                    "normalized": normalize_term(term_text),
                    "type_id": row["typeId"],
                    "lang": row["languageCode"],
                    "semantic_tag": _extract_semantic_tag(term_text),
                }
            )
        return await writer.finish()
