"""Materialise Validation Lab cases into production-shaped Neo4j graphs.

Atlas: DI-724CD8A5
"""

from __future__ import annotations

from typing import Any

from libs.referral_simulator.scaffold import (
    cleanup_referral_scaffold,
    scaffold_referral,
)
from libs.validation_lab.models import EncounterSpec, PmhItem, ValidationCaseSpec

SOURCE_VALIDATION_LAB = "validation-lab"

_PMH_NODE_LABELS: dict[str, tuple[str, str]] = {
    "condition": ("Condition", "HAS_CONDITION"),
    "medication": ("MedicationStatement", "HAS_MEDICATION_STATEMENT"),
    "allergy": ("AllergyIntolerance", "HAS_ALLERGY"),
}

_PMH_NARRATIVE_LABEL: dict[str, str] = {
    "condition": "Past medical history",
    "medication": "Current medications",
    "allergy": "Allergies",
}

_UPSERT_BACKGROUND_ENCOUNTER = """
MATCH (p:Patient {id: $patient_id})
MERGE (e:Encounter {id: $encounter_id})
SET e.text = $text,
    e.label = $label,
    e.date = CASE WHEN $date <> '' THEN date($date) ELSE date() END,
    e.source = $source,
    e.case_id = $case_id
MERGE (p)-[:HAS_ENCOUNTER]->(e)
"""

_CLEANUP_PMH_ITEMS = """
MATCH (p:Patient {id: $patient_id, source: $source})
OPTIONAL MATCH (p)-[:HAS_CONDITION|HAS_MEDICATION_STATEMENT|HAS_ALLERGY]->(pmh)
DETACH DELETE pmh
"""


def _ids_for_case(case_id: str) -> dict[str, str]:
    base = f"lab-{case_id}"
    return {
        "patient_id": f"{base}:patient",
        "encounter_id": f"{base}:encounter",
        "referral_id": f"{base}:referral",
        "dr_id": f"{base}:document",
    }


def _birth_date_from_age(age: float | None) -> str:
    from libs.referral_simulator.scaffold import _birth_date_from_age as _impl

    return _impl(age)


def render_pmh_narrative(pmh: list[PmhItem]) -> str:
    """Render structured PMH picks into a referral-style narrative block.

    PMH is never handed to the pipeline as structured data -- production
    referrals only ever carry free text. Folding these picks into the
    referral narrative keeps every submission exercising real extraction.
    """
    if not pmh:
        return ""
    grouped: dict[str, list[str]] = {}
    for item in pmh:
        label = str(item.term or item.concept_id).strip()
        if not label:
            continue
        grouped.setdefault(item.category, []).append(label)
    lines: list[str] = []
    for category in ("condition", "medication", "allergy"):
        terms = grouped.get(category)
        if not terms:
            continue
        lines.append(f"{_PMH_NARRATIVE_LABEL[category]}: {', '.join(terms)}.")
    return "\n".join(lines)


def _pmh_query(node_label: str, rel_type: str) -> str:
    # node_label/rel_type only ever come from the fixed _PMH_NODE_LABELS
    # allow-list below -- never from unvalidated user input.
    return (
        "MATCH (p:Patient {id: $patient_id}) "
        f"MERGE (item:{node_label} {{id: $item_id}}) "
        "SET item.snomed_concept_id = $concept_id, "
        "item.term = $term, "
        "item.source = $source, "
        "item.case_id = $case_id "
        f"MERGE (p)-[:{rel_type}]->(item)"
    )


def _write_pmh_nodes(
    client: Any, patient_id: str, pmh: list[PmhItem], case_id: str
) -> None:
    for index, item in enumerate(pmh):
        labels = _PMH_NODE_LABELS.get(item.category)
        if not labels:
            continue
        node_label, rel_type = labels
        client.run(
            _pmh_query(node_label, rel_type),
            patient_id=patient_id,
            item_id=f"{patient_id}:pmh:{index}",
            concept_id=item.concept_id,
            term=item.term,
            source=SOURCE_VALIDATION_LAB,
            case_id=case_id,
        )


def _write_encounters(
    client: Any,
    patient_id: str,
    case_id: str,
    encounters: list[EncounterSpec],
) -> list[str]:
    ids: list[str] = []
    for index, encounter in enumerate(encounters):
        encounter_id = f"lab-{case_id}:background-encounter:{index}"
        client.run(
            _UPSERT_BACKGROUND_ENCOUNTER,
            patient_id=patient_id,
            encounter_id=encounter_id,
            text=encounter.text,
            label=encounter.label,
            date=encounter.date,
            source=SOURCE_VALIDATION_LAB,
            case_id=case_id,
        )
        ids.append(encounter_id)
    return ids


def materialise_case(
    client: Any,
    spec: ValidationCaseSpec,
) -> dict[str, Any]:
    """Write patient-graph nodes for the case. Returns graph id map."""
    ids = _ids_for_case(spec.case_id)
    referral_text = (spec.referral_text or "").strip()
    if not referral_text:
        raise ValueError("referral_text is required")

    pmh_narrative = render_pmh_narrative(spec.pmh)
    full_text = (
        f"{pmh_narrative}\n\n{referral_text}" if pmh_narrative else referral_text
    )

    chunk_ids = scaffold_referral(
        ids["patient_id"],
        ids["referral_id"],
        ids["dr_id"],
        full_text,
        encounter_id=ids["encounter_id"],
        source=SOURCE_VALIDATION_LAB,
        patient_age=spec.patient_age,
        patient_sex=spec.patient_sex,
        document_title=spec.title or "Validation Lab referral",
        case_id=spec.case_id,
        patient_name=spec.patient_name or spec.title or "",
    )
    _write_pmh_nodes(client, ids["patient_id"], spec.pmh, spec.case_id)
    encounter_ids = _write_encounters(
        client, ids["patient_id"], spec.case_id, spec.encounters
    )
    return {
        "patient_id": ids["patient_id"],
        "encounter_id": ids["encounter_id"],
        "referral_id": ids["referral_id"],
        "document_reference_id": ids["dr_id"],
        "chunk_ids": list(chunk_ids),
        "background_encounter_ids": encounter_ids,
    }


def cleanup_case_graph(patient_id: str) -> None:
    """Remove Lab-sourced patient graph (+ PMH nodes) for a case patient id."""
    client = None
    try:
        from libs.neo4j_client.client import PatientGraphClient

        client = PatientGraphClient()
        client.run(
            _CLEANUP_PMH_ITEMS, patient_id=patient_id, source=SOURCE_VALIDATION_LAB
        )
    finally:
        if client is not None:
            client.close()
    cleanup_referral_scaffold(patient_id, source=SOURCE_VALIDATION_LAB)
