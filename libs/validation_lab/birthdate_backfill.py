"""Backfill Validation Lab Patient.birthDate from case prose.

Atlas trace:
  DO: DO-6FF1E931
  DI: DI-169C1EB9
  Risks: R-64AC4E14
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-6FF1E931")

Existing lab patients may have birthDate unset while ValidationCase referral
text mentions age (for example "62-year-old"). Pipeline compliance needs
birthDate on the Patient node, not just a runtime fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from libs.validation_lab.patient_age import validation_lab_age_from_case_row
from libs.validation_lab.scaffold import _birth_date_from_age

_LIST_MISSING_BIRTHDATE_PATIENTS = """
MATCH (p:Patient)
WHERE p.id STARTS WITH 'lab-' AND p.id ENDS WITH ':patient'
  AND (p.birthDate IS NULL OR toString(p.birthDate) = '')
OPTIONAL MATCH (c:ValidationCase {patient_id: p.id})
RETURN p.id AS patient_id,
       coalesce(c.id, '') AS case_id,
       coalesce(c.referral_text, '') AS referral_text,
       coalesce(c.reason_for_submission, '') AS reason_for_submission,
       coalesce(c.gp_encounter_json, '') AS gp_encounter_json
ORDER BY p.id
"""

_COUNT_MISSING_BIRTHDATE_PATIENTS = """
MATCH (p:Patient)
WHERE p.id STARTS WITH 'lab-' AND p.id ENDS WITH ':patient'
  AND (p.birthDate IS NULL OR toString(p.birthDate) = '')
RETURN count(p) AS missing_count
"""

_SET_PATIENT_BIRTH_DATE = """
MATCH (p:Patient {id: $patient_id})
WHERE p.birthDate IS NULL OR toString(p.birthDate) = ''
SET p.birthDate = $birth_date
RETURN p.id AS patient_id, toString(p.birthDate) AS birth_date
"""


def case_id_from_patient_id(patient_id: str) -> str:
    """Extract ValidationCase id from lab-{case_id}:patient."""
    base = str(patient_id or "").strip()
    prefix = "lab-"
    suffix = ":patient"
    if base.startswith(prefix) and base.endswith(suffix):
        inner = base.removeprefix(prefix).removesuffix(suffix)
        return inner
    return ""


def resolve_birth_date_for_row(row: dict[str, Any]) -> str:
    """Return ISO birth date for a missing-birthDate lab patient row."""
    case_id = str(row.get("case_id") or "").strip()
    if not case_id:
        case_id = case_id_from_patient_id(str(row.get("patient_id") or ""))
    age_row = {
        "case_id": case_id,
        "referral_text": row.get("referral_text") or "",
        "reason_for_submission": row.get("reason_for_submission") or "",
        "gp_encounter_json": row.get("gp_encounter_json") or "",
    }
    age = validation_lab_age_from_case_row(age_row)
    return _birth_date_from_age(age)


def plan_backfill_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build idempotent birthDate updates from Neo4j rows."""
    planned: list[dict[str, str]] = []
    for row in rows:
        patient_id = str(row.get("patient_id") or "").strip()
        if not patient_id:
            continue
        birth_date = resolve_birth_date_for_row(row)
        if not birth_date:
            continue
        planned.append(
            {
                "patient_id": patient_id,
                "case_id": str(
                    row.get("case_id") or case_id_from_patient_id(patient_id)
                ),
                "birth_date": birth_date,
            }
        )
    return planned


def count_missing_birthdate_patients(client: Any) -> int:
    """Return count of lab-* patients without birthDate."""
    rows = client.run(_COUNT_MISSING_BIRTHDATE_PATIENTS)
    if not rows:
        return 0
    return int(rows[0].get("missing_count") or 0)


def list_missing_birthdate_patients(client: Any) -> list[dict[str, Any]]:
    """Fetch lab patients missing birthDate plus linked ValidationCase text."""
    return list(client.run(_LIST_MISSING_BIRTHDATE_PATIENTS))


@dataclass
class BirthdateBackfillReport:
    """Summary of a validation-lab birthDate backfill run."""

    missing_before: int = 0
    missing_after: int = 0
    planned: int = 0
    updated: int = 0
    skipped: int = 0
    dry_run: bool = True
    updates: list[dict[str, str]] = field(default_factory=list)


def backfill_validation_lab_birthdates(
    client: Any,
    *,
    dry_run: bool = True,
) -> BirthdateBackfillReport:
    """Set Patient.birthDate for lab patients where it is currently absent."""
    report = BirthdateBackfillReport(dry_run=dry_run)
    report.missing_before = count_missing_birthdate_patients(client)
    rows = list_missing_birthdate_patients(client)
    planned = plan_backfill_rows(rows)
    report.planned = len(planned)
    report.skipped = max(0, len(rows) - len(planned))

    if dry_run:
        report.updates = planned
        report.missing_after = report.missing_before
        return report

    updated: list[dict[str, str]] = []
    for item in planned:
        result = client.run(
            _SET_PATIENT_BIRTH_DATE,
            patient_id=item["patient_id"],
            birth_date=item["birth_date"],
        )
        if result:
            updated.append(dict(result[0]))
    report.updated = len(updated)
    report.updates = updated
    report.missing_after = count_missing_birthdate_patients(client)
    return report
