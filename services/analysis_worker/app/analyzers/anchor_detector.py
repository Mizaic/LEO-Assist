from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from libs.domains.ncda_concept_sets import (
    CANCER_TYPE_IDS,
    FAST_TRACK_REFERRAL_IDS,
    SEEN_BY_SPECIALIST_IDS,
    TREATMENT_IDS,
)


@dataclass
class AnchorResult:
    patient_id: str
    referral_anchors: list[dict[str, Any]] = field(default_factory=list)
    diagnosis_anchors: list[dict[str, Any]] = field(default_factory=list)
    treatment_anchors: list[dict[str, Any]] = field(default_factory=list)
    specialist_visit_anchors: list[dict[str, Any]] = field(default_factory=list)
    detection_method: str = "none"
    expanded_start: str | None = None
    expanded_end: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def has_referral(self) -> bool:
        return bool(self.referral_anchors)

    @property
    def earliest_date(self) -> str | None:
        if not self.referral_anchors:
            return None
        return str(self.referral_anchors[0].get("encounter_date") or "")


def _dedupe_by_encounter(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        encounter_id = str(row.get("encounter_id") or "")
        if not encounter_id or encounter_id in seen:
            continue
        seen.add(encounter_id)
        out.append(dict(row))
    return out


_AnchorBuckets = tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]


def _classify_anchor_rows(rows: list[dict[str, Any]]) -> _AnchorBuckets:
    referrals: list[dict[str, Any]] = []
    diagnoses: list[dict[str, Any]] = []
    treatments: list[dict[str, Any]] = []
    specialists: list[dict[str, Any]] = []
    for row in rows:
        concept_id = row.get("concept_id")
        try:
            concept_id = int(concept_id)
        except (TypeError, ValueError):
            continue
        if concept_id in FAST_TRACK_REFERRAL_IDS:
            referrals.append(dict(row))
        if concept_id in CANCER_TYPE_IDS:
            diagnoses.append(dict(row))
        if concept_id in TREATMENT_IDS:
            treatments.append(dict(row))
        if concept_id in SEEN_BY_SPECIALIST_IDS:
            specialists.append(dict(row))
    return (
        _dedupe_by_encounter(referrals),
        _dedupe_by_encounter(diagnoses),
        _dedupe_by_encounter(treatments),
        _dedupe_by_encounter(specialists),
    )


_ANCHOR_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(p.id) = $patient_id
  AND toString(e.date) >= $start_date
  AND toString(e.date) <= $end_date
RETURN
    toString(e.id)              AS encounter_id,
    toString(e.date)            AS encounter_date,
    c.conceptId                 AS concept_id,
    c.name                      AS concept_name,
    c.semanticTag               AS semantic_tag,
    r.source                    AS source,
    coalesce(r.confidence, 0.0) AS confidence,
    r.evidence                  AS evidence
ORDER BY encounter_date
"""


def detect_anchors(
    patient_id: str,
    start_date: str,
    end_date: str,
    patient_client,
    expand_months: int = 3,
) -> AnchorResult:
    rows = patient_client.run(
        _ANCHOR_QUERY,
        patient_id=patient_id,
        start_date=start_date,
        end_date=end_date,
    )
    referrals, diagnoses, treatments, specialists = _classify_anchor_rows(
        list(rows or [])
    )
    has_anchors = any((referrals, diagnoses, treatments, specialists))
    result = AnchorResult(
        patient_id=patient_id,
        referral_anchors=referrals,
        diagnosis_anchors=diagnoses,
        treatment_anchors=treatments,
        specialist_visit_anchors=specialists,
        detection_method="concept" if has_anchors else "none",
    )
    if referrals:
        try:
            raw_date = str(referrals[0].get("encounter_date"))
            referral_date = datetime.fromisoformat(raw_date)
            delta = timedelta(days=30 * expand_months)
            result.expanded_start = (referral_date - delta).date().isoformat()
            result.expanded_end = (referral_date + delta).date().isoformat()
        except (TypeError, ValueError):
            result.errors.append("invalid_referral_date")
    return result
