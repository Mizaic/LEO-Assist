"""Primary-care EPR-shaped patient scaffolding for Validation Lab.

Atlas: DI-3002D641 / DO-9F47D376 / DI-D6E5F94E
"""

from __future__ import annotations

import hashlib
from typing import Any

from libs.referral_simulator.scaffold import _birth_date_from_age
from libs.validation_lab.gp_consult import synthesise_gp_encounter
from libs.validation_lab.models import EncounterSpec, ValidationCaseSpec

SOURCE_VALIDATION_LAB = "validation-lab"

_UPSERT_EPR_PATIENT = """
MERGE (p:Patient {id: $patient_id})
SET p.source = $source,
    p.synthetic = true,
    p.gender = coalesce($gender, 'unknown'),
    p.birthDate = CASE WHEN $birth_date <> '' THEN $birth_date ELSE p.birthDate END,
    p.name = CASE WHEN $patient_name <> '' THEN $patient_name ELSE p.name END,
    p.nhsNumber = CASE WHEN $nhs_number <> '' THEN $nhs_number ELSE p.nhsNumber END,
    p.case_id = CASE WHEN $case_id <> '' THEN $case_id ELSE p.case_id END
MERGE (org:Organization {id: $practice_id})
SET org.name = $practice_name,
    org.source = $source,
    org:GPPractice
MERGE (p)-[:REGISTERED_IN]->(org)
MERGE (p)-[:HAS_GENERAL_PRACTITIONER]->(org)
MERGE (ep:EpisodeOfCare {id: $episode_id})
SET ep.episode_id = $episode_id,
    ep.status = 'active',
    ep.source = $source,
    ep.case_id = $case_id,
    ep.care_setting = 'primary_care',
    ep.referral_date = CASE
        WHEN $referral_date <> '' THEN date($referral_date) ELSE date() END
MERGE (p)-[:HAS_EPISODE_OF_CARE]->(ep)
RETURN p.id AS patient_id, org.id AS practice_id, ep.episode_id AS episode_id
"""

_UPSERT_GP_ENCOUNTER = """
MATCH (p:Patient {id: $patient_id})
MERGE (e:Encounter {id: $encounter_id})
SET e.text = $text,
    e.label = $label,
    e.date = CASE WHEN $date <> '' THEN date($date) ELSE date() END,
    e.source = $source,
    e.case_id = $case_id,
    e.encounter_kind = 'gp_consultation',
    e.consultation_type = 'gp_consultation',
    e.care_setting = 'primary_care'
MERGE (p)-[:HAS_ENCOUNTER]->(e)
RETURN e.id AS encounter_id
"""


def generate_lab_nhs_number(case_id: str) -> str:
    """Deterministic synthetic NHS number for Lab cases (not a real checksum)."""
    digest = hashlib.sha256(str(case_id).encode("utf-8")).hexdigest()
    digits = "".join(ch for ch in digest if ch.isdigit())
    body = (digits + "9999999999")[:10]
    return body


def is_spoa_scenario(scenario_type: str) -> bool:
    return str(scenario_type or "").strip() in {"spo_ag", "ras_referral"}


def auto_gp_encounter_from_text(text: str) -> EncounterSpec:
    """Backward-compatible wrapper -- synthesises SOAP, never letter text.

    Prefer ``synthesise_gp_encounter`` with a full ValidationCaseSpec.
    """
    spec = ValidationCaseSpec(
        case_id="legacy-auto",
        title="Legacy",
        referral_text=text,
    )
    encounter, _referral_date = synthesise_gp_encounter(spec, referral_text=text)
    return encounter


def scaffold_epr_patient(
    client: Any,
    spec: ValidationCaseSpec,
    *,
    patient_id: str,
    referral_date: str = "",
) -> dict[str, str]:
    """Write Care-shaped Patient + practice + primary-care episode."""
    practice_id = f"lab-{spec.case_id}:practice"
    episode_id = f"lab-{spec.case_id}:episode-primary"
    nhs = str(spec.nhs_number or "").strip() or generate_lab_nhs_number(spec.case_id)
    practice_name = (
        str(spec.gp_practice_name or "").strip() or "Validation Lab GP Practice"
    )
    birth_date = _birth_date_from_age(spec.patient_age)
    rows = client.run(
        _UPSERT_EPR_PATIENT,
        patient_id=patient_id,
        practice_id=practice_id,
        episode_id=episode_id,
        source=SOURCE_VALIDATION_LAB,
        gender=spec.patient_sex or "unknown",
        birth_date=birth_date,
        patient_name=spec.patient_name or spec.title or "",
        nhs_number=nhs,
        case_id=spec.case_id,
        practice_name=practice_name,
        referral_date=str(referral_date or "").strip(),
    )
    row = (rows or [{}])[0]
    return {
        "patient_id": str(row.get("patient_id") or patient_id),
        "practice_id": str(row.get("practice_id") or practice_id),
        "episode_id": str(row.get("episode_id") or episode_id),
        "nhs_number": nhs,
        "practice_name": practice_name,
    }


def write_gp_consultation(
    client: Any,
    *,
    patient_id: str,
    case_id: str,
    encounter: EncounterSpec,
) -> str:
    """Write typed GP consultation encounter (not pipeline text source)."""
    text = str(encounter.text or "").strip()
    if not text:
        raise ValueError("gp_encounter.text is required for SPoA scenarios")
    encounter_id = f"lab-{case_id}:gp-consultation"
    client.run(
        _UPSERT_GP_ENCOUNTER,
        patient_id=patient_id,
        encounter_id=encounter_id,
        text=text,
        label=encounter.label or "GP consultation",
        date=encounter.date or "",
        source=SOURCE_VALIDATION_LAB,
        case_id=case_id,
    )
    return encounter_id
