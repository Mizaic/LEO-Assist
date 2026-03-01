"""Anchor detection: finds referral, diagnosis, and treatment milestones.

Single canonical path
---------------------
Tier 1 — :DOCUMENTS + SNOMED concept IDs (source of truth)
    The coding worker writes DOCUMENTS relationships after extracting and
    resolving SNOMED concepts. Each coded concept is matched against
    milestone concept sets (``libs.domains.ncda_concept_sets``).

Legacy fallback paths (hybrid resolver / regex) were removed in hard-cutover
mode to avoid multiple detection behaviors.

Domain → milestone mapping
  fast_track_referrals  → "referral"
  cancer_types          → "diagnosis"
  treatment             → "treatment_start"
  seen_by_specialist    → "specialist_visit"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from libs.domains.ncda_concept_sets import (
    CANCER_TYPE_IDS,
    FAST_TRACK_REFERRAL_IDS,
    MILESTONE_CONCEPT_SETS,
    SEEN_BY_SPECIALIST_IDS,
    TREATMENT_IDS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class AnchorResult:
    patient_id: str
    referral_anchors: list[dict[str, Any]] = field(default_factory=list)
    diagnosis_anchors: list[dict[str, Any]] = field(default_factory=list)
    treatment_anchors: list[dict[str, Any]] = field(default_factory=list)
    specialist_visit_anchors: list[dict[str, Any]] = field(default_factory=list)
    earliest_date: str | None = None
    latest_date: str | None = None
    expanded_start: str | None = None
    expanded_end: str | None = None
    expanded_encounters: list[dict[str, Any]] = field(default_factory=list)
    detection_method: str = "concept"  # "concept" | "none"

    @property
    def has_referral(self) -> bool:
        return bool(self.referral_anchors)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def detect_anchors(
    patient_id: str,
    start_date: str,
    end_date: str,
    patient_client,
    expand_months: int = 3,
) -> AnchorResult:
    """Detect milestone anchors from coded DOCUMENTS relationships only.

    Parameters
    ----------
    patient_client:
        Connected ``PatientGraphClient``.
    """
    result = AnchorResult(patient_id=patient_id)

    # Concept matching via :DOCUMENTS
    coded = _fetch_coded_encounters(patient_id, start_date, end_date, patient_client)
    has_documents = bool(coded)

    if has_documents:
        _apply_concept_anchors(coded, result)
        result.detection_method = "concept"
        logger.info(
            "detect_anchors: patient=%s concept-path (%d coded rows) "
            "→ referrals=%d diagnoses=%d treatments=%d specialist=%d",
            patient_id,
            len(coded),
            len(result.referral_anchors),
            len(result.diagnosis_anchors),
            len(result.treatment_anchors),
            len(result.specialist_visit_anchors),
        )

    if not has_documents:
        result.detection_method = "none"

    _expand_window(patient_id, expand_months, result, patient_client)
    return result


# ---------------------------------------------------------------------------
# Concept-based detection (primary path)
# ---------------------------------------------------------------------------

def _fetch_coded_encounters(
    patient_id: str,
    start_date: str,
    end_date: str,
    client,
) -> list[dict[str, Any]]:
    """Return encounters that have at least one :DOCUMENTS relationship."""
    # Collect all milestone concept IDs in a single query pass
    all_ids = list(
        FAST_TRACK_REFERRAL_IDS
        | CANCER_TYPE_IDS
        | TREATMENT_IDS
        | SEEN_BY_SPECIALIST_IDS
    )
    rows = client.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c) "
        "WHERE toString(p.id) = $pid "
        "  AND toString(e.date) >= $start "
        "  AND toString(e.date) <= $end "
        "  AND toInteger(c.conceptId) IN $ids "
        "RETURN toString(e.id) AS encounter_id, "
        "       toString(e.date) AS encounter_date, "
        "       toInteger(c.conceptId) AS concept_id, "
        "       c.name AS concept_name, "
        "       c.semanticTag AS semantic_tag, "
        "       r.domain AS domain, "
        "       r.confidence AS confidence, "
        "       r.source AS source, "
        "       r.evidence AS evidence "
        "ORDER BY e.date",
        pid=patient_id,
        start=start_date,
        end=end_date,
        ids=all_ids,
    )
    return [dict(r) for r in rows]


def _apply_concept_anchors(
    coded_rows: list[dict[str, Any]],
    result: AnchorResult,
) -> None:
    """Populate anchor lists from coded encounter rows."""
    # Group by encounter so each encounter appears once per anchor type
    seen: dict[str, set[str]] = {
        "referral": set(),
        "diagnosis": set(),
        "treatment_start": set(),
        "specialist_visit": set(),
    }

    for row in coded_rows:
        enc_id = str(row["encounter_id"])
        enc_date = str(row["encounter_date"])
        concept_id = int(row["concept_id"])
        concept_name = row.get("concept_name") or ""
        confidence = row.get("confidence") or 0.0
        source = row.get("source") or "provisional"
        evidence = row.get("evidence") or ""

        anchor_entry = {
            "encounter_id": enc_id,
            "encounter_date": enc_date,
            "concept_id": concept_id,
            "concept_name": concept_name,
            "confidence": confidence,
            "source": source,
            "detection_method": "concept",
            "evidence": evidence,
        }

        if concept_id in FAST_TRACK_REFERRAL_IDS and enc_id not in seen["referral"]:
            result.referral_anchors.append(anchor_entry)
            seen["referral"].add(enc_id)

        if concept_id in CANCER_TYPE_IDS and enc_id not in seen["diagnosis"]:
            result.diagnosis_anchors.append(anchor_entry)
            seen["diagnosis"].add(enc_id)

        if concept_id in TREATMENT_IDS and enc_id not in seen["treatment_start"]:
            result.treatment_anchors.append(anchor_entry)
            seen["treatment_start"].add(enc_id)

        if concept_id in SEEN_BY_SPECIALIST_IDS and enc_id not in seen["specialist_visit"]:
            result.specialist_visit_anchors.append(anchor_entry)
            seen["specialist_visit"].add(enc_id)


# ---------------------------------------------------------------------------
# Window expansion (shared)
# ---------------------------------------------------------------------------

def _expand_window(
    patient_id: str,
    expand_months: int,
    result: AnchorResult,
    client,
) -> None:
    all_dates: list[str] = []
    for anchors in [
        result.referral_anchors,
        result.diagnosis_anchors,
        result.treatment_anchors,
        result.specialist_visit_anchors,
    ]:
        for a in anchors:
            d = a.get("encounter_date", "")
            if d:
                all_dates.append(d[:10])

    if not all_dates:
        return

    all_dates.sort()
    result.earliest_date = all_dates[0]
    result.latest_date = all_dates[-1]

    try:
        earliest = datetime.strptime(result.earliest_date, "%Y-%m-%d")
        latest = datetime.strptime(result.latest_date, "%Y-%m-%d")
        result.expanded_start = (earliest - timedelta(days=expand_months * 30)).strftime("%Y-%m-%d")
        result.expanded_end = (latest + timedelta(days=expand_months * 30)).strftime("%Y-%m-%d")

        if result.expanded_start and result.expanded_end:
            result.expanded_encounters = client.run(
                "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
                "WHERE toString(p.id) = $pid "
                "  AND toString(e.date) >= $start "
                "  AND toString(e.date) <= $end "
                "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text "
                "ORDER BY e.date",
                pid=patient_id,
                start=result.expanded_start,
                end=result.expanded_end,
            )
    except ValueError:
        pass
