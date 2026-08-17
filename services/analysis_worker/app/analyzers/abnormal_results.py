"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-6C694CF9
  DI: DI-21E93377
  Look up via: get_design_control(dc_type="design_output", dc_id="DO-6C694CF9")
"""

from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any

from libs.lab_results.classifier import LabConfigError, classify_lab_result
from libs.neo4j_client.client import KnowledgeGraphClient

_ABNORMAL_PATTERNS = (
    re.compile(r"\babnormal\b", re.I),
    re.compile(r"\babove upper normal range\b", re.I),
    re.compile(r"\bbelow\b.*\brange\b", re.I),
    re.compile(r"\bcritically low\b", re.I),
    re.compile(r"\bcritical\b", re.I),
    re.compile(r"\bseverely reduced\b", re.I),
)
_FOLLOW_UP_PATTERNS = (
    re.compile(r"\brepeat\b", re.I),
    re.compile(r"\bmonitor\b", re.I),
    re.compile(r"\bfollow[- ]?up\b", re.I),
)


_GET_PATIENT_DEMOGRAPHICS = """
MATCH (p:Patient {id: $patient_id})
RETURN coalesce(p.sex, p.gender) AS sex,
       coalesce(p.date_of_birth, p.dateOfBirth, p.birthDate) AS date_of_birth
LIMIT 1
"""

_GET_STRUCTURED_RESULTS = """
MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(o:Observable_entity)
WHERE r.value IS NOT NULL
  AND ($start_date = '' OR e.date IS NULL OR toString(e.date) >= $start_date)
  AND ($end_date = '' OR e.date IS NULL OR toString(e.date) <= $end_date)
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS date,
       o.conceptId AS concept_id,
       toFloat(r.value) AS value,
       r.unit AS unit,
       r.referenceRange AS reported_reference_range,
       r.evidence AS evidence
ORDER BY e.date DESC
"""

_GET_TEXT_ENCOUNTERS = """
MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE ($start_date = '' OR e.date IS NULL OR toString(e.date) >= $start_date)
  AND ($end_date = '' OR e.date IS NULL OR toString(e.date) <= $end_date)
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS date,
       coalesce(e.text, e.note, e.content, '') AS text
ORDER BY e.date DESC
"""


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _age_years_on(dob_raw: str | None, event_date_raw: str | None) -> int | None:
    dob = _parse_date(dob_raw)
    event_date = _parse_date(event_date_raw) or date.today()
    if dob is None:
        return None
    years = event_date.year - dob.year
    if (event_date.month, event_date.day) < (dob.month, dob.day):
        years -= 1
    return max(years, 0)


def classify_severity(
    value: float,
    low: float | None,
    high: float | None,
    critical_low: float | None,
    critical_high: float | None,
) -> str:
    """Classify a numeric result against range boundaries."""
    if critical_low is not None and value < critical_low:
        return "critically_abnormal"
    if critical_high is not None and value > critical_high:
        return "critically_abnormal"
    if low is not None and high is not None and low <= value <= high:
        return "normal"
    if low is not None and value < low:
        denom = max(abs(low), 1e-9)
        return "mildly_abnormal" if ((low - value) / denom) <= 0.2 else "abnormal"
    if high is not None and value > high:
        denom = max(abs(high), 1e-9)
        return "mildly_abnormal" if ((value - high) / denom) <= 0.2 else "abnormal"
    return "normal"


def _severity_from_lab_classification(classification: str) -> str:
    if classification in {"critically_low", "critically_high"}:
        return "critical"
    return "warning"


def _append_range_missing(
    findings: list[dict[str, Any]],
    *,
    patient_id: str,
    encounter_id: str,
    row: dict[str, Any],
    concept_id: str,
    value: float,
    reason: str,
) -> None:
    findings.append(
        {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "date": row.get("date"),
            "severity": "warning",
            "classification": "range_missing",
            "concept_id": concept_id,
            "value": value,
            "unit": row.get("unit"),
            "description": reason,
        }
    )


def detect_abnormal_results(
    patient_id: str,
    start_date: str,
    end_date: str,
    patient_client,
    *,
    org_id: str | None = None,
    knowledge_client: Any | None = None,
) -> list[dict[str, Any]]:

    demographics = list(
        patient_client.run(_GET_PATIENT_DEMOGRAPHICS, patient_id=patient_id) or []
    )
    sex = (
        str((demographics[0].get("sex") if demographics else "") or "").strip().lower()
        or None
    )
    dob_raw = demographics[0].get("date_of_birth") if demographics else None
    owns_kg_client = knowledge_client is None
    try:
        kg_client = knowledge_client or KnowledgeGraphClient()
    except RuntimeError:
        kg_client = None

    rows = list(
        patient_client.run(
            _GET_STRUCTURED_RESULTS,
            patient_id=patient_id,
            start_date=start_date,
            end_date=end_date,
        )
        or []
    )

    findings: list[dict[str, Any]] = []
    structured_encounter_ids: set[str] = set()

    for row in rows:
        encounter_id = str(row.get("encounter_id") or "")
        if encounter_id:
            structured_encounter_ids.add(encounter_id)

        concept_id = str(row.get("concept_id") or "")
        value = _safe_float(row.get("value"))
        if not concept_id or value is None:
            continue

        age_years = _age_years_on(
            str(dob_raw) if dob_raw else None, str(row.get("date") or "")
        )
        if kg_client is None:
            _append_range_missing(
                findings,
                patient_id=patient_id,
                encounter_id=encounter_id,
                row=row,
                concept_id=concept_id,
                value=value,
                reason=(
                    "Knowledge Graph unavailable; cannot classify structured result "
                    f"for concept {concept_id}"
                ),
            )
            continue

        try:
            with kg_client.session() as kg_session:
                lab_result = classify_lab_result(
                    concept_id,
                    value,
                    row.get("unit"),
                    patient_sex=sex,
                    patient_age=age_years,
                    session=kg_session,
                    org_id=org_id,
                )
        except LabConfigError as exc:
            _append_range_missing(
                findings,
                patient_id=patient_id,
                encounter_id=encounter_id,
                row=row,
                concept_id=concept_id,
                value=value,
                reason=str(exc),
            )
            continue
        except Exception as exc:
            _append_range_missing(
                findings,
                patient_id=patient_id,
                encounter_id=encounter_id,
                row=row,
                concept_id=concept_id,
                value=value,
                reason=f"Lab classification failed for concept {concept_id}: {exc}",
            )
            continue

        if lab_result.classification == "normal":
            continue

        band = lab_result.reference_range
        findings.append(
            {
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "date": row.get("date"),
                "severity": _severity_from_lab_classification(
                    lab_result.classification
                ),
                "classification": lab_result.classification,
                "concept_id": concept_id,
                "interpretation_concept_id": lab_result.interpretation_concept_id,
                "value": value,
                "unit": row.get("unit"),
                "canonical_value": lab_result.canonical_value,
                "canonical_unit": lab_result.canonical_unit,
                "range": {
                    "low": band.low if band else None,
                    "high": band.high if band else None,
                    "critical_low": band.critical_low if band else None,
                    "critical_high": band.critical_high if band else None,
                    "source": band.source if band else None,
                    "range_id": band.range_id if band else None,
                },
                "description": (
                    f"{lab_result.display_name}: value "
                    f"{lab_result.canonical_value:g} {lab_result.canonical_unit} "
                    f"classified as {lab_result.classification}"
                ),
            }
        )

    text_rows = list(
        patient_client.run(
            _GET_TEXT_ENCOUNTERS,
            patient_id=patient_id,
            start_date=start_date,
            end_date=end_date,
        )
        or []
    )
    for row in text_rows:
        encounter_id = str(row.get("encounter_id") or "")
        if encounter_id and encounter_id in structured_encounter_ids:
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        if not any(pattern.search(text) for pattern in _ABNORMAL_PATTERNS):
            continue
        if any(pattern.search(text) for pattern in _FOLLOW_UP_PATTERNS):
            continue
        findings.append(
            {
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "date": row.get("date"),
                "severity": (
                    "critical"
                    if re.search(r"\bcritical|critically low\b", text, re.I)
                    else "warning"
                ),
                "classification": "text_fallback",
                "description": text,
            }
        )
    if owns_kg_client and kg_client is not None:
        kg_client.close()
    return findings
