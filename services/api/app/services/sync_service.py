"""Sync approved gold from patient graph EncounterCandidates to DOCUMENTS."""

from __future__ import annotations

from typing import Any

from app.models.neo4j_schema import DELETE_ENCOUNTER_DOCUMENTS
from app.services.neo4j_store import list_approved_candidates_for_patient
from app.services.v3.patient_graph_writer import PatientGraphWriter, SemanticLinkPayload


def _term_to_payload(term: dict[str, Any], encounter_id: str) -> SemanticLinkPayload | None:
    """Build SemanticLinkPayload from gold term. Returns None if no SNOMED concept."""
    concept_id = term.get("coding", {}).get("snomed_concept_id")
    if not concept_id:
        return None
    coding = term.get("coding", {})
    context = term.get("context", {})
    if isinstance(context, dict):
        ctx = context
    else:
        ctx = {}
    modifiers = term.get("modifiers", {}) or {}
    semantic_tag = term.get("semantic_tag", "SnomedConcept") or "SnomedConcept"
    return SemanticLinkPayload(
        encounter_id=encounter_id,
        semantic_tag=semantic_tag,
        concept_id=concept_id,
        term=coding.get("snomed_term"),
        read_code=coding.get("read_code"),
        evidence=term.get("text", ""),
        confidence=float(coding.get("score", 0.9)),
        domain="clinical",
        context=ctx,
        modifiers=modifiers,
        source="gold_sync",
    )


def sync_gold_to_patient(
    patient_id: str,
    *,
    patient_session,
) -> dict[str, Any]:
    """
    Sync approved gold EncounterCandidates into DOCUMENTS on the patient graph.
    Both candidates and DOCUMENTS now live in the same graph.
    """
    candidates = list_approved_candidates_for_patient(patient_id, patient_session)
    if not candidates:
        return {
            "patient_id": patient_id,
            "encounters_synced": 0,
            "links_created": 0,
            "error": "no_approved_gold",
        }

    writer = PatientGraphWriter()
    links_created = 0

    for candidate in candidates:
        encounter_id = str(candidate.get("encounter_id", ""))
        if not encounter_id:
            continue

        patient_session.run(
            DELETE_ENCOUNTER_DOCUMENTS,
            patient_id=patient_id,
            encounter_id=encounter_id,
        )

        for sentence in candidate.get("sentences", []):
            for term in sentence.get("terms", []):
                payload = _term_to_payload(term, encounter_id)
                if payload:
                    writer.upsert_documents_link(payload, session=patient_session)
                    links_created += 1

    return {
        "patient_id": patient_id,
        "encounters_synced": len(candidates),
        "links_created": links_created,
    }
