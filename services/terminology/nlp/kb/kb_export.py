"""
Export the Neo4j terminology graph to Entity JSONL for TF-IDF index building.

Queries the graph for all Concepts with their descriptions, UMLS mappings,
ICD-10 codes, Read codes, and semantic types, then writes one JSON line per
concept to the output file.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

EXPORT_QUERY = """
MATCH (c:Concept)
WHERE c.active = true OR c.active IS NULL
OPTIONAL MATCH (c)<-[:DESCRIBES]-(t:Term)
OPTIONAL MATCH (c)-[:SAME_AS]-(u:UmlsConcept)
OPTIONAL MATCH (u)-[:MAPS_TO_ICD10]->(i:Icd10Code)
OPTIONAL MATCH (u)-[:MAPS_TO_READ]->(r:ReadCode)
WITH c,
     collect(DISTINCT t.term) AS terms,
     collect(DISTINCT u.cui) AS cuis,
     collect(DISTINCT u.preferred_name) AS umls_names,
     collect(DISTINCT i.code) AS icd10_codes,
     collect(DISTINCT r.code) AS read_codes,
     collect(DISTINCT u.semantic_types) AS sem_type_lists
RETURN c.id AS concept_id,
       c.fsn AS fsn,
       c.semantic_tag AS semantic_tag,
       terms,
       cuis,
       umls_names,
       icd10_codes,
       read_codes,
       sem_type_lists
"""


async def export_kb(
    driver: AsyncDriver,
    output_path: str | Path,
    database: str = "neo4j",
) -> int:
    """Stream concepts from Neo4j and write Entity JSONL."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    async with driver.session(database=database) as session:
        result = await session.run(EXPORT_QUERY)
        with open(output_path, "w", encoding="utf-8") as f:
            async for record in result:
                concept_id = record["concept_id"]
                fsn = record["fsn"] or ""
                terms = [t for t in record["terms"] if t]

                canonical = _pick_canonical(fsn, terms)
                aliases = list(dict.fromkeys(terms))
                if canonical in aliases:
                    aliases.remove(canonical)

                cuis = [c for c in record["cuis"] if c]
                umls_names = [n for n in record["umls_names"] if n]
                for name in umls_names:
                    if name not in aliases and name != canonical:
                        aliases.append(name)

                sem_types: list[str] = []
                for type_list in record["sem_type_lists"]:
                    if isinstance(type_list, list):
                        sem_types.extend(type_list)
                    elif isinstance(type_list, str):
                        sem_types.append(type_list)
                sem_types = list(dict.fromkeys(sem_types))

                entity = {
                    "concept_id": concept_id,
                    "canonical_name": canonical,
                    "aliases": aliases,
                    "types": sem_types,
                    "definition": None,
                    "cui": cuis[0] if cuis else None,
                    "icd10_codes": list(dict.fromkeys(record["icd10_codes"])),
                    "read_codes": list(dict.fromkeys(record["read_codes"])),
                }
                f.write(json.dumps(entity, ensure_ascii=False) + "\n")
                count += 1
                if count % 50_000 == 0:
                    logger.info("Exported %d concepts", count)

    logger.info("Export complete: %d concepts written to %s", count, output_path)
    return count


def _pick_canonical(fsn: str, terms: list[str]) -> str:
    """Pick the best canonical name: prefer the preferred term, fall back to FSN."""
    if terms:
        return terms[0]
    if fsn:
        return fsn
    return ""
