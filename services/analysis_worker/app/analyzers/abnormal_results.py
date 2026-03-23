from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any

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

_LOOKUP_REFERENCE_RANGE = """
MATCH (rr:ReferenceRange)
WHERE rr.conceptId = $concept_id
  AND ($org_id IS NULL OR rr.org_id = $org_id OR rr.org_id IS NULL)
  AND ($unit IS NULL OR rr.unit IS NULL OR toLower(rr.unit) = toLower($unit))
  AND ($sex IS NULL OR rr.sex IS NULL OR toLower(rr.sex) = 'all' OR toLower(rr.sex) = toLower($sex))
  AND ($age_years IS NULL OR rr.age_min IS NULL OR rr.age_min <= $age_years)
  AND ($age_years IS NULL OR rr.age_max IS NULL OR rr.age_max >= $age_years)
RETURN rr.low AS low,
       rr.high AS high,
       rr.critical_low AS critical_low,
       rr.critical_high AS critical_high,
       rr.unit AS unit,
       rr.sex AS sex,
       rr.age_min AS age_min,
       rr.age_max AS age_max,
       rr.org_id AS org_id,
       rr.source AS source,
       rr.preferred_term AS preferred_term,
       rr.range_id AS range_id
ORDER BY CASE
           WHEN $org_id IS NOT NULL AND rr.org_id = $org_id THEN 0
           WHEN rr.org_id IS NULL THEN 1
           ELSE 2
         END,
         CASE WHEN rr.unit IS NOT NULL THEN 0 ELSE 1 END,
         CASE WHEN rr.sex IS NOT NULL AND toLower(rr.sex) <> 'all' THEN 0 ELSE 1 END,
         coalesce(rr.age_min, -1) DESC
LIMIT 1
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


def lookup_reference_range(
    concept_id: str,
    unit: str | None,
    sex: str | None,
    age_years: int | None,
    org_id: str | None,
    session: Any,
) -> dict[str, Any] | None:
    rows = list(
        session.run(
            _LOOKUP_REFERENCE_RANGE,
            concept_id=str(concept_id),
            unit=unit,
            sex=sex.lower() if isinstance(sex, str) else None,
            age_years=age_years,
            org_id=org_id,
        )
        or []
    )
    if not rows:
        return None
    return dict(rows[0])


def detect_abnormal_results(
    patient_id: str,
    start_date: str,
    end_date: str,
    patient_client,
    *,
    org_id: str | None = None,
    knowledge_client: Any | None = None,
) -> list[dict[str, Any]]:
    demographics = list(patient_client.run(_GET_PATIENT_DEMOGRAPHICS, patient_id=patient_id) or [])
    sex = str((demographics[0].get("sex") if demographics else "") or "").strip().lower() or None
    dob_raw = (demographics[0].get("date_of_birth") if demographics else None)

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

        age_years = _age_years_on(str(dob_raw) if dob_raw else None, str(row.get("date") or ""))
        reference = lookup_reference_range(
            concept_id=concept_id,
            unit=row.get("unit"),
            sex=sex,
            age_years=age_years,
            org_id=org_id,
            session=patient_client,
        )

        if reference is None:
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
                    "description": f"Structured result has no configured range: concept {concept_id}",
                }
            )
            continue

        low = _safe_float(reference.get("low"))
        high = _safe_float(reference.get("high"))
        critical_low = _safe_float(reference.get("critical_low"))
        critical_high = _safe_float(reference.get("critical_high"))
        classification = classify_severity(value, low, high, critical_low, critical_high)
        if classification == "normal":
            continue

        severity = "critical" if classification == "critically_abnormal" else "warning"
        findings.append(
            {
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "date": row.get("date"),
                "severity": severity,
                "classification": classification,
                "concept_id": concept_id,
                "value": value,
                "unit": row.get("unit"),
                "range": {
                    "low": low,
                    "high": high,
                    "critical_low": critical_low,
                    "critical_high": critical_high,
                    "source": reference.get("source"),
                    "org_id": reference.get("org_id"),
                    "range_id": reference.get("range_id"),
                },
                "description": (
                    f"{reference.get('preferred_term') or concept_id}: value {value} {row.get('unit') or ''} "
                    f"classified as {classification}"
                ).strip(),
            }
        )

    # Regex text fallback for encounters with no structured value rows.
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
                "severity": "critical" if re.search(r"\bcritical|critically low\b", text, re.I) else "warning",
                "classification": "text_fallback",
                "description": text,
            }
        )
    return findings
