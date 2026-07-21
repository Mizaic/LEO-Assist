"""Materialise Validation Lab cases into production-shaped Neo4j graphs.

Atlas trace:
  DO: DO-3A70C3DD
  DI: DI-724CD8A5
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3A70C3DD")

Atlas: DI-724CD8A5
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from libs.referral_simulator.scaffold import (
    cleanup_referral_scaffold,
    scaffold_referral,
)
from libs.validation_lab.ag_scaffold import scaffold_ag_case
from libs.validation_lab.epr_scaffold import (
    is_spoa_scenario,
    scaffold_epr_patient,
    write_gp_consultation,
)
from libs.validation_lab.gp_consult import (
    referral_delay_days,
    synthesise_gp_encounter,
)
from libs.validation_lab.models import (
    EncounterSpec,
    ObservationTrigger,
    PmhItem,
    ValidationCaseSpec,
)
from libs.validation_lab.pmh_verbalisation import compose_submission_text
from libs.validation_lab.referral_identity import fill_referral_identity

SOURCE_VALIDATION_LAB = "validation-lab"

_SET_PATIENT_EQUITY = """
MATCH (p:Patient {id: $patient_id})
SET p.ethnicityConceptId = CASE
        WHEN $ethnicity_concept_id <> '' THEN $ethnicity_concept_id
        ELSE p.ethnicityConceptId END,
    p.ethnicityTerm = CASE
        WHEN $ethnicity_term <> '' THEN $ethnicity_term
        ELSE p.ethnicityTerm END,
    p.performanceStatusGrade = CASE
        WHEN $performance_status_grade IS NOT NULL
        THEN $performance_status_grade
        ELSE p.performanceStatusGrade END,
    p.comorbidityBand = CASE
        WHEN $comorbidity_band <> '' THEN $comorbidity_band
        ELSE p.comorbidityBand END,
    p.core20Decile = CASE
        WHEN $core20_decile IS NOT NULL THEN $core20_decile
        ELSE p.core20Decile END,
    p.plusGroup = CASE
        WHEN $plus_group <> '' THEN $plus_group
        ELSE p.plusGroup END
"""

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


def render_observations_narrative(
    observations: list[ObservationTrigger] | None,
) -> str:
    """Render numeric observations as plain-English referral sentences.

    Production observations reach GuidelineEvaluator via NER over text
    (observations_from_entities), not direct :Observation writes. Lab
    cases follow the same path.
    """
    if not observations:
        return ""
    lines: list[str] = []
    for item in observations:
        label = str(item.term or item.observable_id).strip()
        if not label:
            continue
        unit = str(item.unit or "").strip()
        value = item.value
        if unit:
            lines.append(f"Blood test: {label} {value} {unit}.")
        else:
            lines.append(f"Blood test: {label} {value}.")
    return "\n".join(lines)


def _has_equity_fields(spec: ValidationCaseSpec) -> bool:
    return any(
        (
            spec.ethnicity_concept_id,
            spec.ethnicity_term,
            spec.performance_status_grade is not None,
            spec.comorbidity_band,
            spec.core20_decile is not None,
            spec.plus_group,
        )
    )


def _apply_equity_fields(
    client: Any, patient_id: str, spec: ValidationCaseSpec
) -> None:
    """SET optional synthetic equity properties when present on the spec."""
    if not _has_equity_fields(spec):
        return
    client.run(
        _SET_PATIENT_EQUITY,
        patient_id=patient_id,
        ethnicity_concept_id=str(spec.ethnicity_concept_id or ""),
        ethnicity_term=str(spec.ethnicity_term or ""),
        performance_status_grade=spec.performance_status_grade,
        comorbidity_band=str(spec.comorbidity_band or ""),
        core20_decile=spec.core20_decile,
        plus_group=str(spec.plus_group or ""),
    )


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


def _knowledge_client_for_verbalisation() -> Any:
    from libs.neo4j_client.client import KnowledgeGraphClient

    return KnowledgeGraphClient()


def _resolve_referral_submission_text(
    spec: ValidationCaseSpec,
    *,
    knowledge_client: Any | None = None,
) -> str:
    """Compose referral narrative for generic vs RAS SPoA scenarios."""
    if spec.scenario_type == "ras_referral":
        seed = str(spec.verbalisation_seed or spec.case_id)
        reason = str(spec.reason_for_submission or "").strip()
        if not reason and not (spec.referral_text or "").strip():
            raise ValueError("reason_for_submission is required for ras_referral")
        kg = knowledge_client
        close_kg = False
        if kg is None and spec.pmh:
            kg = _knowledge_client_for_verbalisation()
            close_kg = True
        try:
            return compose_submission_text(
                reason=reason or (spec.referral_text or "").strip(),
                pmh=spec.pmh,
                seed=seed,
                client=kg,
            )
        finally:
            if close_kg and kg is not None:
                kg.close()

    referral_text = (spec.referral_text or "").strip()
    if not referral_text:
        raise ValueError("referral_text is required")
    filled = fill_referral_identity(
        referral_text,
        patient_name=spec.patient_name or spec.title or "",
        birth_date=_birth_date_from_age(spec.patient_age),
        gp_name=str(spec.gp_practice_name or "").strip()
        or "Validation Lab GP Practice",
    )
    blocks = [
        render_pmh_narrative(spec.pmh),
        render_observations_narrative(spec.observations),
        filled,
    ]
    return "\n\n".join(block for block in blocks if block)


def _resolve_gp_encounter(
    spec: ValidationCaseSpec,
    *,
    submission_text: str,
) -> tuple[EncounterSpec, str]:
    """Return (GP encounter, referral_date ISO).

    Explicit GP notes are kept. Missing notes are synthesised as SOAP
    (never a referral-letter excerpt). Referral date is on/after the GP
    consult depending on lab wait.
    """
    seed = submission_text or (spec.referral_text or "")
    if spec.gp_encounter is not None and str(spec.gp_encounter.text or "").strip():
        encounter = spec.gp_encounter
        if str(encounter.date or "").strip():
            gp_day = date.fromisoformat(str(encounter.date)[:10])
            delay = referral_delay_days(
                case_id=spec.case_id,
                referral_text=seed,
                observations=spec.observations,
            )
            return encounter, (gp_day + timedelta(days=delay)).isoformat()
        synthesised, referral_date = synthesise_gp_encounter(spec, referral_text=seed)
        # Keep author text; apply synthesised dating only.
        return (
            EncounterSpec(
                label=encounter.label or synthesised.label,
                text=encounter.text,
                date=synthesised.date,
            ),
            referral_date,
        )
    if is_spoa_scenario(spec.scenario_type) and spec.case_type == "ag":
        raise ValueError("gp_encounter is required for SPoA scenarios")
    return synthesise_gp_encounter(spec, referral_text=seed)


def _apply_care_ready_patient_shape(
    client: Any,
    spec: ValidationCaseSpec,
    graph: dict[str, Any],
) -> None:
    """EPR overlay for all referrals; SPoA A&G still requires gp_encounter."""
    if spec.case_type == "ag" and not is_spoa_scenario(spec.scenario_type):
        return
    if spec.case_type != "referral" and not is_spoa_scenario(spec.scenario_type):
        return
    encounter, referral_date = _resolve_gp_encounter(
        spec,
        submission_text=str(graph.get("submission_text") or ""),
    )
    epr = scaffold_epr_patient(
        client,
        spec,
        patient_id=graph["patient_id"],
        referral_date=referral_date,
    )
    gp_id = write_gp_consultation(
        client,
        patient_id=graph["patient_id"],
        case_id=spec.case_id,
        encounter=encounter,
    )
    graph["nhs_number"] = epr["nhs_number"]
    graph["practice_id"] = epr["practice_id"]
    graph["episode_id"] = epr["episode_id"]
    graph["gp_encounter_id"] = gp_id
    graph["referral_date"] = referral_date
    graph["gp_encounter_date"] = encounter.date


def materialise_case(
    client: Any,
    spec: ValidationCaseSpec,
    *,
    knowledge_client: Any | None = None,
) -> dict[str, Any]:
    """Write patient-graph nodes for the case. Returns graph id map."""
    if spec.scenario_type == "spo_ag" and spec.case_type != "ag":
        raise ValueError("spo_ag requires case_type=ag")
    if spec.scenario_type == "ras_referral" and spec.case_type != "referral":
        raise ValueError("ras_referral requires case_type=referral")

    if spec.case_type == "ag":
        graph = scaffold_ag_case(client, spec, knowledge_client=knowledge_client)
        _write_pmh_nodes(client, graph["patient_id"], spec.pmh, spec.case_id)
        encounter_ids = _write_encounters(
            client, graph["patient_id"], spec.case_id, spec.encounters
        )
        graph["background_encounter_ids"] = encounter_ids
        _apply_equity_fields(client, graph["patient_id"], spec)
        _apply_care_ready_patient_shape(client, spec, graph)
        return graph

    ids = _ids_for_case(spec.case_id)
    full_text = _resolve_referral_submission_text(
        spec, knowledge_client=knowledge_client
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
        nhs_number=spec.nhs_number or "",
    )
    _write_pmh_nodes(client, ids["patient_id"], spec.pmh, spec.case_id)
    encounter_ids = _write_encounters(
        client, ids["patient_id"], spec.case_id, spec.encounters
    )
    _apply_equity_fields(client, ids["patient_id"], spec)
    graph = {
        "patient_id": ids["patient_id"],
        "encounter_id": ids["encounter_id"],
        "referral_id": ids["referral_id"],
        "document_reference_id": ids["dr_id"],
        "chunk_ids": list(chunk_ids),
        "background_encounter_ids": encounter_ids,
        "submission_text": full_text,
    }
    _apply_care_ready_patient_shape(client, spec, graph)
    return graph


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
