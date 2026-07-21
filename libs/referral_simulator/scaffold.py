"""Materialise production-shaped referral graphs in the patient Neo4j."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from libs.cypher.chunk_queries import UPSERT_CHUNK, chunk_sha256, make_chunk_id
from libs.neo4j_client.client import PatientGraphClient
from libs.referral_simulator.message import ReferralSimulatorError

SOURCE_QUICK_TEST = "quick-test"
SOURCE_SCENARIO = "ai_summarisation_scenario"

_UPSERT_REFERRAL_GRAPH = """
MERGE (p:Patient {id: $patient_id})
SET p.source = $source,
    p.synthetic = true,
    p.gender = coalesce($gender, 'unknown'),
    p.birthDate = CASE WHEN $birth_date <> '' THEN $birth_date ELSE p.birthDate END,
    p.name = CASE WHEN $patient_name <> '' THEN $patient_name ELSE p.name END,
    p.nhsNumber = CASE
        WHEN $nhs_number <> '' THEN $nhs_number ELSE p.nhsNumber END,
    p.case_id = CASE WHEN $case_id <> '' THEN $case_id ELSE p.case_id END,
    p.parent_run_id = CASE
        WHEN $parent_run_id <> '' THEN $parent_run_id ELSE p.parent_run_id END
MERGE (rr:ReferralRequest {id: $referral_id})
SET rr.source = $source, rr.status = 'active'
MERGE (dr:DocumentReference {id: $dr_id})
SET dr.source = $source, dr.title = $document_title
MERGE (rr)-[:FOR_PATIENT]->(p)
MERGE (rr)-[:HAS_DOCUMENT]->(dr)
MERGE (p)-[:HAS_DOCUMENT_REFERENCE]->(dr)
MERGE (dr)-[:DERIVED_FROM]->(rr)
"""

# Correlation Encounter for SBAR context integrity / pipeline encounter_id.
# Text source remains Chunks; Encounter.text is left empty on purpose.
_UPSERT_CORRELATION_ENCOUNTER = """
MATCH (p:Patient {id: $patient_id})
MERGE (e:Encounter {id: $encounter_id})
SET e.source = $source,
    e.case_id = CASE WHEN $case_id <> '' THEN $case_id ELSE e.case_id END,
    e.parent_run_id = CASE
        WHEN $parent_run_id <> '' THEN $parent_run_id ELSE e.parent_run_id END,
    e.referral_id = $referral_id
MERGE (p)-[:HAS_ENCOUNTER]->(e)
"""

_CLEANUP_REFERRAL_SCAFFOLD = """
MATCH (p:Patient {id: $patient_id, source: $source})
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter {source: $source})
OPTIONAL MATCH (p)-[:HAS_DOCUMENT_REFERENCE]->(dr:DocumentReference {source: $source})
OPTIONAL MATCH (dr)-[:HAS_CHUNK]->(c:Chunk)
OPTIONAL MATCH (rr:ReferralRequest {source: $source})-[:FOR_PATIENT]->(p)
DETACH DELETE e, c, dr, rr, p
"""


def _is_markdown_heading(paragraph: str) -> bool:
    first = paragraph.lstrip().splitlines()[0] if paragraph.strip() else ""
    return first.startswith("#")


def _is_markdown_table(paragraph: str) -> bool:
    lines = [ln.strip() for ln in paragraph.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    return lines[0].startswith("|") and lines[1].startswith("|")


def _merge_heading_with_following_table(paragraphs: list[str]) -> list[str]:
    """Keep '## Blood Results' with the following GFM table in one chunk."""
    merged: list[str] = []
    index = 0
    while index < len(paragraphs):
        current = paragraphs[index]
        nxt = paragraphs[index + 1] if index + 1 < len(paragraphs) else ""
        if _is_markdown_heading(current) and nxt and _is_markdown_table(nxt):
            merged.append(f"{current}\n\n{nxt}")
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged


def split_into_chunks(text: str, dr_id: str) -> list[dict[str, Any]]:
    """Split text into paragraph-based chunks with canonical IDs."""
    if not str(text or "").strip():
        raise ReferralSimulatorError("referral text is empty")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        raise ReferralSimulatorError("referral text is empty")
    paragraphs = _merge_heading_with_following_table(paragraphs)
    chunks: list[dict[str, Any]] = []
    offset = 0
    for ordinal, para in enumerate(paragraphs, start=1):
        sha = chunk_sha256(para)
        chunks.append(
            {
                "id": make_chunk_id(dr_id, ordinal, sha),
                "text": para,
                "sha256": sha,
                "ordinal": ordinal,
                "char_start": offset,
                "char_end": offset + len(para),
            }
        )
        offset += len(para) + 2
    return chunks


def _birth_date_from_age(age: float | None) -> str:
    if age is None:
        return ""
    try:
        today = date.today()
        birth_year = today.year - int(age)
        return date(birth_year, today.month, today.day).isoformat()
    except (ValueError, OverflowError):
        return ""


def scaffold_referral(
    patient_id: str,
    referral_id: str,
    dr_id: str,
    text: str,
    *,
    encounter_id: str = "",
    source: str = SOURCE_QUICK_TEST,
    patient_age: float | None = None,
    patient_sex: str | None = None,
    patient_name: str = "",
    nhs_number: str = "",
    birth_date: str = "",
    case_id: str = "",
    parent_run_id: str = "",
    document_title: str = "Referral document",
) -> list[str]:
    """Write Patient+RR+DR+Chunks (+ optional correlation Encounter)."""
    if not str(patient_id or "").strip():
        raise ReferralSimulatorError("patient_id is required")
    if not str(referral_id or "").strip():
        raise ReferralSimulatorError("referral_id is required")
    if not str(dr_id or "").strip():
        raise ReferralSimulatorError("dr_id is required")

    chunks = split_into_chunks(text, dr_id)
    resolved_birth = birth_date or _birth_date_from_age(patient_age)
    client = PatientGraphClient()
    try:
        with client.session() as session:
            session.run(
                _UPSERT_REFERRAL_GRAPH,
                patient_id=patient_id,
                referral_id=referral_id,
                dr_id=dr_id,
                source=source,
                gender=patient_sex or "unknown",
                birth_date=resolved_birth,
                patient_name=patient_name or "",
                nhs_number=nhs_number or "",
                case_id=case_id or "",
                parent_run_id=parent_run_id or "",
                document_title=document_title,
            )
            for chunk in chunks:
                session.run(
                    UPSERT_CHUNK,
                    document_reference_id=dr_id,
                    chunk_id=chunk["id"],
                    text=chunk["text"],
                    sha256=chunk["sha256"],
                    char_start=chunk["char_start"],
                    char_end=chunk["char_end"],
                    ordinal=chunk["ordinal"],
                )
            if str(encounter_id or "").strip():
                session.run(
                    _UPSERT_CORRELATION_ENCOUNTER,
                    patient_id=patient_id,
                    encounter_id=encounter_id,
                    referral_id=referral_id,
                    source=source,
                    case_id=case_id or "",
                    parent_run_id=parent_run_id or "",
                )
    finally:
        client.close()
    return [c["id"] for c in chunks]


def cleanup_referral_scaffold(
    patient_id: str,
    *,
    source: str = SOURCE_QUICK_TEST,
) -> None:
    """Detach-delete scaffold nodes for one patient + source."""
    if not str(patient_id or "").strip():
        raise ReferralSimulatorError("patient_id is required for cleanup")
    if not str(source or "").strip():
        raise ReferralSimulatorError("source is required for cleanup")
    client = PatientGraphClient()
    try:
        client.run(
            _CLEANUP_REFERRAL_SCAFFOLD,
            patient_id=patient_id,
            source=source,
        )
    finally:
        client.close()
