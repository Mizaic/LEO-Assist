"""
Phase 3: Load UMLS crosswalk into Neo4j.

Streams MRCONSO.RRF filtered to English + relevant SABs.
Creates (:UmlsConcept) nodes and [:SAME_AS] links to existing (:Concept).
Links CUIs to existing (:Icd10Code) and (:ReadCode) nodes.
Then loads MRSTY.RRF to add semantic types to each UmlsConcept.

Source files (pipe-delimited, no header):
  - umls/full/2025AB/META/MRCONSO.RRF
  - umls/full/2025AB/META/MRSTY.RRF

Available SABs in the full download:
  SNOMEDCT_US, ICD10CM, RCD, RXNORM, LNC, DSM-5, MTH, SRC
"""

from __future__ import annotations

import logging
from pathlib import Path

from neo4j import AsyncDriver

from .base import BatchWriter, normalize_term, stream_rrf

logger = logging.getLogger(__name__)

MRCONSO_COLUMNS = [
    "CUI", "LAT", "TS", "LUI", "STT", "SUI", "ISPREF",
    "AUI", "SAUI", "SCUI", "SDUI", "SAB", "TTY", "CODE",
    "STR", "SRL", "SUPPRESS", "CVF",
]

MRSTY_COLUMNS = ["CUI", "TUI", "STN", "STY", "ATUI", "CVF"]

SNOMED_SABS = {"SNOMEDCT_US"}
ICD10_SABS = {"ICD10CM"}
READ_SABS = {"RCD"}
ALL_RELEVANT_SABS = SNOMED_SABS | ICD10_SABS | READ_SABS

MERGE_UMLS_SNOMED = """
UNWIND $rows AS r
MERGE (u:UmlsConcept {cui: r.cui})
ON CREATE SET u.preferred_name = r.term
WITH u, r
MATCH (c:Concept {id: r.scui})
MERGE (u)-[:SAME_AS]->(c)
"""

MERGE_UMLS_PREFERRED = """
UNWIND $rows AS r
MERGE (u:UmlsConcept {cui: r.cui})
SET u.preferred_name = r.term
"""

MERGE_UMLS_ICD10 = """
UNWIND $rows AS r
MERGE (u:UmlsConcept {cui: r.cui})
ON CREATE SET u.preferred_name = r.term
WITH u, r
MERGE (icd:Icd10Code {code: r.code})
MERGE (u)-[:MAPS_TO_ICD10]->(icd)
"""

MERGE_UMLS_READ = """
UNWIND $rows AS r
MERGE (u:UmlsConcept {cui: r.cui})
ON CREATE SET u.preferred_name = r.term
WITH u, r
MERGE (rd:ReadCode {code: r.code})
ON CREATE SET rd.version = 'v2', rd.term = r.term
MERGE (u)-[:MAPS_TO_READ]->(rd)
"""

SET_SEMANTIC_TYPES = """
UNWIND $rows AS r
MATCH (u:UmlsConcept {cui: r.cui})
SET u.semantic_types = coalesce(u.semantic_types, []) + r.sty
"""


async def load_mrconso(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> int:
    """Stream MRCONSO.RRF and create UmlsConcept nodes + crosswalk links."""
    label = "MRCONSO"
    logger.info("%s: starting (streaming %s)", label, filepath.name)

    async with driver.session() as session:
        snomed_writer = BatchWriter(
            session, MERGE_UMLS_SNOMED, batch_size, f"{label}/SNOMED"
        )
        pref_writer = BatchWriter(
            session, MERGE_UMLS_PREFERRED, batch_size, f"{label}/PREF"
        )
        icd10_writer = BatchWriter(
            session, MERGE_UMLS_ICD10, batch_size, f"{label}/ICD10"
        )
        read_writer = BatchWriter(
            session, MERGE_UMLS_READ, batch_size, f"{label}/READ"
        )

        seen_cui_pref: set[str] = set()
        total_scanned = 0

        for row in stream_rrf(filepath, MRCONSO_COLUMNS):
            total_scanned += 1
            if total_scanned % 500_000 == 0:
                logger.info("%s: scanned %d rows", label, total_scanned)

            if row["LAT"] != "ENG":
                continue
            if row["SUPPRESS"] in ("O", "E"):
                continue

            sab = row["SAB"]
            if sab not in ALL_RELEVANT_SABS:
                continue

            cui = row["CUI"]
            term = row["STR"]

            if sab in SNOMED_SABS:
                scui = row["SCUI"]
                if scui:
                    await snomed_writer.add({
                        "cui": cui,
                        "term": term,
                        "scui": scui,
                    })
                if cui not in seen_cui_pref and row["ISPREF"] == "Y":
                    seen_cui_pref.add(cui)
                    await pref_writer.add({"cui": cui, "term": term})

            elif sab in ICD10_SABS:
                code = row["CODE"]
                if code:
                    await icd10_writer.add({
                        "cui": cui,
                        "term": term,
                        "code": code,
                    })

            elif sab in READ_SABS:
                code = row["CODE"]
                if code:
                    await read_writer.add({
                        "cui": cui,
                        "term": term,
                        "code": code,
                    })

        logger.info("%s: scanned %d total rows", label, total_scanned)
        snomed_count = await snomed_writer.finish()
        pref_count = await pref_writer.finish()
        icd10_count = await icd10_writer.finish()
        read_count = await read_writer.finish()
        return snomed_count + pref_count + icd10_count + read_count


async def load_mrsty(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> int:
    """Stream MRSTY.RRF and add semantic types to UmlsConcept nodes."""
    label = "MRSTY"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        writer = BatchWriter(
            session, SET_SEMANTIC_TYPES, batch_size, label
        )
        for row in stream_rrf(filepath, MRSTY_COLUMNS):
            await writer.add({
                "cui": row["CUI"],
                "sty": row["STY"],
            })
        return await writer.finish()
