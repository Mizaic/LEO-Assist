"""Quick-run scaffold -- ephemeral patient graph nodes for pipeline testing.

Creates and cleans up temporary Patient+Encounter (encounter mode) or
Patient+ReferralRequest+DocumentReference+Chunk (referral mode) nodes
in the patient graph. All nodes carry source='quick-test' for safe cleanup.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from libs.cypher.chunk_queries import UPSERT_CHUNK, chunk_sha256, make_chunk_id

_SOURCE = "quick-test"

_UPSERT_ENCOUNTER_GRAPH = """
MERGE (p:Patient {id: $patient_id})
SET p.source = $source,
    p.gender = coalesce($gender, 'unknown'),
    p.birthDate = CASE WHEN $birth_date <> '' THEN $birth_date ELSE p.birthDate END
MERGE (e:Encounter {id: $encounter_id})
SET e.text = $text, e.date = date(), e.source = $source
MERGE (p)-[:HAS_ENCOUNTER]->(e)
"""

_UPSERT_REFERRAL_GRAPH = """
MERGE (p:Patient {id: $patient_id})
SET p.source = $source,
    p.gender = coalesce($gender, 'unknown'),
    p.birthDate = CASE WHEN $birth_date <> '' THEN $birth_date ELSE p.birthDate END
MERGE (rr:ReferralRequest {id: $referral_id})
SET rr.source = $source, rr.status = 'active'
MERGE (dr:DocumentReference {id: $dr_id})
SET dr.source = $source, dr.title = 'Quick test document'
MERGE (rr)-[:FOR_PATIENT]->(p)
MERGE (rr)-[:HAS_DOCUMENT]->(dr)
MERGE (p)-[:HAS_DOCUMENT_REFERENCE]->(dr)
MERGE (dr)-[:DERIVED_FROM]->(rr)
"""

_CLEANUP_QUICK_RUN = """
MATCH (p:Patient {id: $patient_id, source: $source})
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter {source: $source})
OPTIONAL MATCH (p)-[:HAS_DOCUMENT_REFERENCE]->(dr:DocumentReference {source: $source})
OPTIONAL MATCH (dr)-[:HAS_CHUNK]->(c:Chunk)
OPTIONAL MATCH (rr:ReferralRequest {source: $source})-[:FOR_PATIENT]->(p)
DETACH DELETE e, c, dr, rr, p
"""


def split_into_chunks(text: str, dr_id: str) -> list[dict[str, Any]]:
    """Split text into paragraph-based chunks with canonical IDs."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]
    chunks: list[dict[str, Any]] = []
    offset = 0
    for ordinal, para in enumerate(paragraphs, start=1):
        sha = chunk_sha256(para)
        chunks.append({
            "id": make_chunk_id(dr_id, ordinal, sha),
            "text": para,
            "sha256": sha,
            "ordinal": ordinal,
            "char_start": offset,
            "char_end": offset + len(para),
        })
        offset += len(para) + 2
    return chunks


def _birth_date_from_age(age: float | None) -> str:
    """Return an ISO-8601 date string for an approximate birthdate, or ''."""
    if age is None:
        return ""
    try:
        today = date.today()
        birth_year = today.year - int(age)
        return date(birth_year, today.month, today.day).isoformat()
    except (ValueError, OverflowError):
        return ""


def scaffold_encounter(
    patient_id: str,
    encounter_id: str,
    text: str,
    *,
    patient_age: float | None = None,
    patient_sex: str | None = None,
) -> None:
    """Write a Patient + Encounter to the patient graph."""
    from app.db.neo4j_client import PatientGraphClient

    client = PatientGraphClient()
    try:
        client.run(
            _UPSERT_ENCOUNTER_GRAPH,
            patient_id=patient_id,
            encounter_id=encounter_id,
            text=text,
            source=_SOURCE,
            gender=patient_sex or "unknown",
            birth_date=_birth_date_from_age(patient_age),
        )
    finally:
        client.close()


def scaffold_referral(
    patient_id: str,
    referral_id: str,
    dr_id: str,
    text: str,
    *,
    patient_age: float | None = None,
    patient_sex: str | None = None,
) -> list[str]:
    """Write a Patient+RR+DR+Chunks and return the chunk_id list."""
    from app.db.neo4j_client import PatientGraphClient

    chunks = split_into_chunks(text, dr_id)
    client = PatientGraphClient()
    try:
        with client.session() as session:
            session.run(
                _UPSERT_REFERRAL_GRAPH,
                patient_id=patient_id,
                referral_id=referral_id,
                dr_id=dr_id,
                source=_SOURCE,
                gender=patient_sex or "unknown",
                birth_date=_birth_date_from_age(patient_age),
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
    finally:
        client.close()
    return [c["id"] for c in chunks]


def cleanup_quick_run(patient_id: str) -> None:
    """Detach-delete all quick-test nodes for this patient."""
    from app.db.neo4j_client import PatientGraphClient

    client = PatientGraphClient()
    try:
        client.run(_CLEANUP_QUICK_RUN, patient_id=patient_id, source=_SOURCE)
    finally:
        client.close()
