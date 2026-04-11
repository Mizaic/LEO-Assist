"""Reset patient DOCUMENTS for re-processing."""

from __future__ import annotations

import logging

from app.models.neo4j_schema import (
    CLEANUP_PATIENT_SHORTCUTS_FOR_CONCEPTS,
    CLEAR_ENCOUNTER_SENTENCES_PAYLOAD,
    DELETE_ENCOUNTER_CODING_DECISIONS,
    DELETE_ENCOUNTER_DOCUMENTS,
    DELETE_ENCOUNTER_EPISODE_LINKS,
    DELETE_ORPHAN_ENCOUNTER_LLM_USAGE,
    GET_PATIENT,
    GET_ENCOUNTER,
    LIST_ENCOUNTER_DOCUMENT_CONCEPT_IDS,
    RESET_ENCOUNTER_REVIEW_QUEUE,
    RESET_PATIENT_DOCUMENTS,
    RESET_PATIENT_DIRECT_SEMANTIC,
)

logger = logging.getLogger(__name__)


def reset_patient(patient_id: str, session) -> dict[str, int | str]:
    """Remove all DOCUMENTS and Patient->semantic shortcut relationships."""
    patient_rows = list(session.run(GET_PATIENT, patient_id=patient_id))
    if not patient_rows:
        logger.warning("reset_patient: patient_id=%s not found", patient_id)
        return {
            "patient_id": patient_id,
            "links_deleted": 0,
            "error": "patient_not_found",
        }

    record = session.run(RESET_PATIENT_DOCUMENTS, patient_id=patient_id).single()
    links_deleted = int(record["links_deleted"] or 0) if record else 0
    logger.info(
        "reset_patient documents: patient=%s deleted=%d", patient_id, links_deleted
    )

    direct_record = session.run(
        RESET_PATIENT_DIRECT_SEMANTIC, patient_id=patient_id
    ).single()
    direct_deleted = int(direct_record["direct_deleted"] or 0) if direct_record else 0
    logger.info(
        "reset_patient direct_semantic: patient=%s deleted=%d",
        patient_id,
        direct_deleted,
    )

    total = links_deleted + direct_deleted
    logger.info(
        "reset_patient complete: patient=%s total_deleted=%d", patient_id, total
    )
    return {"patient_id": patient_id, "links_deleted": total}


def reset_encounter(
    patient_id: str, encounter_id: str, session
) -> dict[str, int | str]:
    """Remove encounter coding artefacts while preserving Patient->Encounter links."""
    encounter_rows = list(
        session.run(GET_ENCOUNTER, patient_id=patient_id, encounter_id=encounter_id)
    )
    if not encounter_rows:
        logger.warning(
            "reset_encounter: encounter not found patient=%s encounter=%s",
            patient_id,
            encounter_id,
        )
        return {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "links_deleted": 0,
            "episode_links_deleted": 0,
            "shortcuts_deleted": 0,
            "review_queue_deleted": 0,
            "llm_usage_deleted": 0,
            "coding_decisions_deleted": 0,
            "error": "encounter_not_found",
        }

    concept_row = session.run(
        LIST_ENCOUNTER_DOCUMENT_CONCEPT_IDS,
        patient_id=patient_id,
        encounter_id=encounter_id,
    ).single()
    concept_ids = (
        concept_row["concept_ids"] if concept_row and concept_row["concept_ids"] else []
    )
    logger.info(
        "reset_encounter concept_ids: patient=%s encounter=%s found=%d",
        patient_id,
        encounter_id,
        len(concept_ids),
    )

    docs_row = session.run(
        DELETE_ENCOUNTER_DOCUMENTS,
        patient_id=patient_id,
        encounter_id=encounter_id,
    ).single()
    links_deleted = (
        int(docs_row["deleted"]) if docs_row and "deleted" in docs_row else 0
    )
    logger.info(
        "reset_encounter documents: patient=%s encounter=%s deleted=%d",
        patient_id,
        encounter_id,
        links_deleted,
    )

    episode_links_row = session.run(
        DELETE_ENCOUNTER_EPISODE_LINKS,
        patient_id=patient_id,
        encounter_id=encounter_id,
    ).single()
    episode_links_deleted = (
        int(episode_links_row["deleted"])
        if episode_links_row and "deleted" in episode_links_row
        else 0
    )
    logger.info(
        "reset_encounter episode_links: patient=%s encounter=%s deleted=%d",
        patient_id,
        encounter_id,
        episode_links_deleted,
    )

    shortcuts_deleted = 0
    if concept_ids:
        shortcut_rows = session.run(
            CLEANUP_PATIENT_SHORTCUTS_FOR_CONCEPTS,
            patient_id=patient_id,
            concept_ids=concept_ids,
        )
        for row in shortcut_rows:
            shortcuts_deleted += int(row.get("shortcuts_deleted") or 0)
    logger.info(
        "reset_encounter shortcuts: patient=%s encounter=%s deleted=%d concepts_checked=%d",
        patient_id,
        encounter_id,
        shortcuts_deleted,
        len(concept_ids),
    )

    rq_row = session.run(
        RESET_ENCOUNTER_REVIEW_QUEUE,
        patient_id=patient_id,
        encounter_id=encounter_id,
    ).single()
    review_queue_deleted = (
        int(rq_row["deleted"]) if rq_row and "deleted" in rq_row else 0
    )
    logger.info(
        "reset_encounter review_queue: patient=%s encounter=%s deleted=%d",
        patient_id,
        encounter_id,
        review_queue_deleted,
    )

    llm_row = session.run(
        DELETE_ORPHAN_ENCOUNTER_LLM_USAGE,
        encounter_id=encounter_id,
    ).single()
    llm_usage_deleted = int(llm_row["llm_usage_deleted"]) if llm_row else 0
    logger.info(
        "reset_encounter llm_usage: patient=%s encounter=%s deleted=%d",
        patient_id,
        encounter_id,
        llm_usage_deleted,
    )

    decision_row = session.run(
        DELETE_ENCOUNTER_CODING_DECISIONS,
        decision_prefix=f"dec:{encounter_id}:",
    ).single()
    coding_decisions_deleted = (
        int(decision_row["decisions_deleted"]) if decision_row else 0
    )
    logger.info(
        "reset_encounter coding_decisions: patient=%s encounter=%s deleted=%d",
        patient_id,
        encounter_id,
        coding_decisions_deleted,
    )

    session.run(
        CLEAR_ENCOUNTER_SENTENCES_PAYLOAD,
        patient_id=patient_id,
        encounter_id=encounter_id,
    )
    logger.info(
        "reset_encounter sentences_payload: patient=%s encounter=%s cleared",
        patient_id,
        encounter_id,
    )

    logger.info(
        "reset_encounter complete: patient=%s encounter=%s "
        "docs=%d episode_links=%d shortcuts=%d review_queue=%d "
        "llm_usage=%d coding_decisions=%d",
        patient_id,
        encounter_id,
        links_deleted,
        episode_links_deleted,
        shortcuts_deleted,
        review_queue_deleted,
        llm_usage_deleted,
        coding_decisions_deleted,
    )
    return {
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "links_deleted": links_deleted,
        "episode_links_deleted": episode_links_deleted,
        "shortcuts_deleted": shortcuts_deleted,
        "review_queue_deleted": review_queue_deleted,
        "llm_usage_deleted": llm_usage_deleted,
        "coding_decisions_deleted": coding_decisions_deleted,
    }
