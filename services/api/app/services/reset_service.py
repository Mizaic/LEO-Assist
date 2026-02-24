"""Reset patient DOCUMENTS for re-processing."""

from __future__ import annotations

from app.models.neo4j_schema import (
    GET_PATIENT,
    RESET_PATIENT_DOCUMENTS,
    RESET_PATIENT_DIRECT_SEMANTIC,
)


def reset_patient(patient_id: str, session) -> dict[str, int | str]:
    """Remove all DOCUMENTS and Patient->semantic relationships. Returns links_deleted."""
    patient_rows = list(session.run(GET_PATIENT, patient_id=patient_id))
    if not patient_rows:
        return {"patient_id": patient_id, "links_deleted": 0, "error": "patient_not_found"}

    result = session.run(RESET_PATIENT_DOCUMENTS, patient_id=patient_id)
    record = result.single()
    links_deleted = record["links_deleted"] if record else 0

    direct_result = session.run(RESET_PATIENT_DIRECT_SEMANTIC, patient_id=patient_id)
    direct_record = direct_result.single()
    direct_deleted = direct_record["direct_deleted"] if direct_record else 0

    return {
        "patient_id": patient_id,
        "links_deleted": links_deleted + direct_deleted,
    }
