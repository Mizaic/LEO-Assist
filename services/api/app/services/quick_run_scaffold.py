"""Quick-run scaffold -- thin wrapper over libs.referral_simulator.

Creates and cleans up temporary Patient+Encounter (encounter mode) or
Patient+ReferralRequest+DocumentReference+Chunk (referral mode) nodes
in the patient graph. Referral mode delegates to the shared simulator.
"""

from __future__ import annotations

from libs.referral_simulator.scaffold import (
    SOURCE_QUICK_TEST,
    cleanup_referral_scaffold,
    scaffold_referral as _scaffold_referral,
    split_into_chunks,
)

# Re-export for callers that imported split_into_chunks from this module.
__all__ = [
    "cleanup_quick_run",
    "scaffold_encounter",
    "scaffold_referral",
    "split_into_chunks",
]

_SOURCE = SOURCE_QUICK_TEST

_UPSERT_ENCOUNTER_GRAPH = """
MERGE (p:Patient {id: $patient_id})
SET p.source = $source,
    p.gender = coalesce($gender, 'unknown'),
    p.birthDate = CASE WHEN $birth_date <> '' THEN $birth_date ELSE p.birthDate END
MERGE (e:Encounter {id: $encounter_id})
SET e.text = $text, e.date = date(), e.source = $source
MERGE (p)-[:HAS_ENCOUNTER]->(e)
"""


def _birth_date_from_age(age: float | None) -> str:
    from libs.referral_simulator.scaffold import _birth_date_from_age as _impl

    return _impl(age)


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
    encounter_id: str = "",
    patient_age: float | None = None,
    patient_sex: str | None = None,
) -> list[str]:
    """Write a Patient+RR+DR+Chunks and return the chunk_id list."""
    return _scaffold_referral(
        patient_id,
        referral_id,
        dr_id,
        text,
        encounter_id=encounter_id,
        source=SOURCE_QUICK_TEST,
        patient_age=patient_age,
        patient_sex=patient_sex,
        document_title="Quick test document",
    )


def cleanup_quick_run(patient_id: str) -> None:
    """Detach-delete all quick-test nodes for this patient."""
    cleanup_referral_scaffold(patient_id, source=SOURCE_QUICK_TEST)
