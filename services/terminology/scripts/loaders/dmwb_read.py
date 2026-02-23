"""
Phase 4: Enrich Read codes, CTV3, and ICD-10 from DMWB Access databases.

Sources:
  - DMWB NHS READ.mdb → CTV3 terms (395K), Read v2 terms (175K)
  - DMWB NHS Data Migration Maps.mdb → CTV3→SNOMED (445K), RCT→SNOMED (102K),
    ICD terms (19K), ICD→SNOMED (38K)
"""

from __future__ import annotations

import logging
from pathlib import Path

import pyodbc
from neo4j import AsyncDriver

from .base import BatchWriter, normalize_term

logger = logging.getLogger(__name__)

CONN_TPL = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ="

ENRICH_READ_CTV3 = """
UNWIND $rows AS r
MERGE (rd:ReadCode {code: r.code})
SET rd.term = r.term,
    rd.version = CASE WHEN rd.version IS NULL THEN 'ctv3' ELSE rd.version END
"""

ENRICH_READ_V2 = """
UNWIND $rows AS r
MERGE (rd:ReadCode {code: r.code})
SET rd.term = r.term,
    rd.version = 'v2'
"""

MAP_CTV3_TO_SNOMED = """
UNWIND $rows AS r
MATCH (rd:ReadCode {code: r.read_code})
MATCH (c:Concept {id: r.snomed_id})
MERGE (c)-[:MAPS_TO_READ]->(rd)
"""

MAP_RCT_TO_SNOMED = """
UNWIND $rows AS r
MATCH (rd:ReadCode {code: r.read_code})
MATCH (c:Concept {id: r.snomed_id})
MERGE (c)-[:MAPS_TO_READ]->(rd)
"""

ENRICH_ICD10 = """
UNWIND $rows AS r
MERGE (icd:Icd10Code {code: r.code})
SET icd.term = r.term
"""

MAP_ICD_TO_SNOMED = """
UNWIND $rows AS r
MATCH (icd:Icd10Code {code: r.icd_code})
MATCH (c:Concept {id: r.snomed_id})
MERGE (c)-[:MAPS_TO_ICD10]->(icd)
"""


def _decode(v):
    if isinstance(v, bytes):
        try:
            return v.decode("utf-16-le")
        except Exception:
            return v.hex()
    return v


def _stream_table(mdb_path: str, table: str, columns: list[str]):
    """Yield dicts from an Access table, decoding binary fields."""
    conn = pyodbc.connect(CONN_TPL + mdb_path)
    cursor = conn.cursor()
    col_list = ", ".join(f"[{c}]" for c in columns)
    cursor.execute(f"SELECT {col_list} FROM [{table}]")
    for row in cursor:
        yield {c: _decode(v) for c, v in zip(columns, row)}
    conn.close()


async def load_ctv3_terms(
    driver: AsyncDriver,
    mdb_path: str,
    batch_size: int = 5_000,
) -> int:
    """Load CTV3 code→term from DMWB NHS READ.mdb CTV3 table."""
    label = "CTV3 terms"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        writer = BatchWriter(session, ENRICH_READ_CTV3, batch_size, label)
        for row in _stream_table(mdb_path, "CTV3", ["CUI", "T30", "STAT"]):
            if row["STAT"] != "C":
                continue
            term = (row["T30"] or "").strip()
            code = (row["CUI"] or "").strip()
            if not code or not term:
                continue
            await writer.add({"code": code, "term": term})
        return await writer.finish()


async def load_rct_terms(
    driver: AsyncDriver,
    mdb_path: str,
    batch_size: int = 5_000,
) -> int:
    """Load Read v2 code→term from DMWB NHS READ.mdb RCT table."""
    label = "RCT (Read v2) terms"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        writer = BatchWriter(session, ENRICH_READ_V2, batch_size, label)
        seen = set()
        for row in _stream_table(mdb_path, "RCT", ["CUI", "TUI", "T30"]):
            code = (row["CUI"] or "").strip()
            term = (row["T30"] or "").strip()
            if not code or not term:
                continue
            if row["TUI"] == "00" and code not in seen:
                seen.add(code)
                await writer.add({"code": code, "term": term})
        return await writer.finish()


async def load_ctv3_snomed_map(
    driver: AsyncDriver,
    mdb_path: str,
    batch_size: int = 5_000,
) -> int:
    """Load CTV3→SNOMED maps from DMWB Maps.mdb CTV3SCTMAP table."""
    label = "CTV3→SNOMED map"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        writer = BatchWriter(session, MAP_CTV3_TO_SNOMED, batch_size, label)
        for row in _stream_table(
            mdb_path, "CTV3SCTMAP", ["SCUI", "TCUI", "MAPTYP", "ASSURED"]
        ):
            if row["MAPTYP"] not in ("E", "D"):
                continue
            read_code = (row["SCUI"] or "").strip()
            snomed_id = (row["TCUI"] or "").strip()
            if read_code and snomed_id:
                await writer.add({
                    "read_code": read_code,
                    "snomed_id": snomed_id,
                })
        return await writer.finish()


async def load_rct_snomed_map(
    driver: AsyncDriver,
    mdb_path: str,
    batch_size: int = 5_000,
) -> int:
    """Load Read v2→SNOMED maps from DMWB Maps.mdb RCTSCTMAP table."""
    label = "RCT→SNOMED map"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        writer = BatchWriter(session, MAP_RCT_TO_SNOMED, batch_size, label)
        for row in _stream_table(
            mdb_path, "RCTSCTMAP", ["SCUI", "TCUI", "MAPTYP", "ASSURED"]
        ):
            if row["MAPTYP"] not in ("E", "D"):
                continue
            read_code = (row["SCUI"] or "").strip()
            snomed_id = (row["TCUI"] or "").strip()
            if read_code and snomed_id:
                await writer.add({
                    "read_code": read_code,
                    "snomed_id": snomed_id,
                })
        return await writer.finish()


async def load_icd_terms(
    driver: AsyncDriver,
    mdb_path: str,
    batch_size: int = 5_000,
) -> int:
    """Enrich Icd10Code nodes with terms from DMWB Maps.mdb ICD table."""
    label = "ICD terms"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        writer = BatchWriter(session, ENRICH_ICD10, batch_size, label)
        for row in _stream_table(mdb_path, "ICD", ["CUI", "TERM"]):
            code = (row["CUI"] or "").strip()
            term = (row["TERM"] or "").strip()
            if code and term:
                await writer.add({"code": code, "term": term})
        return await writer.finish()


async def load_icd_snomed_map(
    driver: AsyncDriver,
    mdb_path: str,
    batch_size: int = 5_000,
) -> int:
    """Load ICD→SNOMED maps from DMWB Maps.mdb ICDSCTMAP table."""
    label = "ICD→SNOMED map"
    logger.info("%s: starting", label)
    async with driver.session() as session:
        writer = BatchWriter(session, MAP_ICD_TO_SNOMED, batch_size, label)
        for row in _stream_table(
            mdb_path, "ICDSCTMAP", ["SCUI", "TCUI", "MAPTYP", "ASSURED"]
        ):
            if row["MAPTYP"] not in ("E", "D"):
                continue
            icd_code = (row["SCUI"] or "").strip()
            snomed_id = (row["TCUI"] or "").strip()
            if icd_code and snomed_id:
                await writer.add({
                    "icd_code": icd_code,
                    "snomed_id": snomed_id,
                })
        return await writer.finish()
