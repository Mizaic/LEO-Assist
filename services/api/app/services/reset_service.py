"""Reset patient DOCUMENTS for re-processing."""

from __future__ import annotations

from app.models.neo4j_schema import GET_PATIENT, RESET_PATIENT_DOCUMENTS


def reset_patient(patient_id: str, session) -> dict[str, int | str]:
    """Remove all DOCUMENTS for a patient's encounters. Returns links_deleted."""
    patient_rows = list(session.run(GET_PATIENT, patient_id=patient_id))
    if not patient_rows:
        return {"patient_id": patient_id, "links_deleted": 0, "error": "patient_not_found"}

    result = session.run(RESET_PATIENT_DOCUMENTS, patient_id=patient_id)
    record = result.single()
    links_deleted = record["links_deleted"] if record else 0
    return {"patient_id": patient_id, "links_deleted": links_deleted}
