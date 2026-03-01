"""Reset review queue (EncounterCandidates, ReviewTasks) for a patient."""

from __future__ import annotations

from app.models.neo4j_schema import RESET_PATIENT_REVIEW_QUEUE


def reset_review_queue(patient_id: str, session) -> dict[str, int | str]:
    """Remove all EncounterCandidates and ReviewTasks for a patient from the Coding graph."""
    result = session.run(RESET_PATIENT_REVIEW_QUEUE, patient_id=patient_id)
    record = result.single()
    deleted = record["deleted"] if record else 0
    return {
        "patient_id": patient_id,
        "deleted": deleted,
    }
