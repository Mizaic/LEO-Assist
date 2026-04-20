"""Patient graph inspection service.

Atlas trace:
  DO: DO-0998FAF5
  Also implements: DO-86800C9B
  DI: DI-FC80B65A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0998FAF5")
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from libs.dq._models import (
    CodedConcept,
    EncounterSummary,
    EpisodeSummary,
    PatientSummary,
)

logger = logging.getLogger(__name__)

_PATIENT_EPISODES_Q = """
MATCH (p:Patient {id: $patient_id})-[:HAS_EPISODE]->(ep:EpisodeOfCare)
RETURN ep.id AS episode_id,
       ep.cancer_type AS site,
       ep.status AS status,
       ep.referral_date AS referral_date,
       ep.specialist_visit_date AS specialist_date,
       ep.auto_closed AS auto_closed,
       ep.hitl_flag AS hitl_flag,
       ep.hitl_reason AS hitl_reason
ORDER BY ep.referral_date
LIMIT $limit
"""

_PATIENT_ENCOUNTERS_Q = """
MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE ($since IS NULL OR enc.date >= $since)
  AND ($until IS NULL OR enc.date <= $until)
OPTIONAL MATCH (enc)-[d:DOCUMENTS]->(c)
WHERE c.conceptId IS NOT NULL
WITH enc, collect({
    concept_id: toString(c.conceptId),
    name: c.name,
    assertion: d.assertion,
    source: d.source,
    confidence: d.confidence,
    semantic_tag: c.semanticTag
}) AS concepts
RETURN enc.id AS encounter_id,
       enc.date AS date,
       enc.classification_type AS classification,
       concepts,
       enc.text AS text
ORDER BY enc.date DESC
LIMIT $limit
"""

_SCHEMA_AUDIT_Q = """
MATCH (enc:Encounter)
WITH enc LIMIT $sample_size
RETURN
    enc.id IS NOT NULL AS has_id,
    enc.date IS NOT NULL AS has_date,
    enc.text IS NOT NULL AS has_text,
    valueType(enc.date) AS date_type,
    enc.classification_type IS NOT NULL AS has_classification
LIMIT $sample_size
"""


def get_patient_summary(
    patient_id: str,
    client: Any,
    since: Optional[str] = None,
    until: Optional[str] = None,
    with_text: bool = False,
    limit: int = 100,
) -> PatientSummary:
    """Return a full patient summary including encounters and episodes."""
    from libs.neo4j_client.client import run_with_retry

    ep_rows = run_with_retry(
        client, _PATIENT_EPISODES_Q, patient_id=patient_id, limit=limit
    )
    episodes = [
        EpisodeSummary(
            episode_id=r["episode_id"] or "",
            site=r["site"] or "unknown",
            status=r["status"] or "unknown",
            referral_date=r.get("referral_date"),
            specialist_date=r.get("specialist_date"),
            auto_closed=bool(r.get("auto_closed")),
            hitl_flag=bool(r.get("hitl_flag")),
            hitl_reason=r.get("hitl_reason"),
        )
        for r in ep_rows
    ]

    enc_rows = run_with_retry(
        client,
        _PATIENT_ENCOUNTERS_Q,
        patient_id=patient_id,
        since=since,
        until=until,
        limit=limit,
    )
    encounters = [_row_to_encounter(r, with_text) for r in enc_rows]

    return PatientSummary(
        patient_id=patient_id,
        encounter_count=len(enc_rows),
        episode_count=len(ep_rows),
        episodes=episodes,
        encounters=encounters,
    )


def get_schema_audit(client: Any, sample_size: int = 200) -> dict:
    """Return encounter schema consistency stats from a sample."""
    from libs.neo4j_client.client import run_with_retry

    rows = run_with_retry(client, _SCHEMA_AUDIT_Q, sample_size=sample_size)
    if not rows:
        return {"sample_size": 0}

    date_types = [r.get("date_type") for r in rows]
    return {
        "sample_size": len(rows),
        "missing_id_pct": _pct_false(rows, "has_id"),
        "missing_date_pct": _pct_false(rows, "has_date"),
        "missing_text_pct": _pct_false(rows, "has_text"),
        "missing_classification_pct": _pct_false(rows, "has_classification"),
        "date_types": _count_unique(date_types),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_encounter(row: dict, with_text: bool) -> EncounterSummary:
    concepts = [
        CodedConcept(
            concept_id=c.get("concept_id") or "",
            name=c.get("name") or "",
            assertion=c.get("assertion"),
            source=c.get("source"),
            confidence=c.get("confidence"),
            semantic_tag=c.get("semantic_tag"),
        )
        for c in (row.get("concepts") or [])
        if c.get("concept_id")
    ]
    text = row.get("text") or ""
    return EncounterSummary(
        encounter_id=row["encounter_id"] or "",
        date=row["date"] or "",
        classification=row.get("classification"),
        coded_concepts=concepts,
        text_preview=(text[:200] if with_text else text[:150]) or None,
    )


def _pct_false(rows: list[dict], key: str) -> float:
    falsey = sum(1 for r in rows if not r.get(key))
    return round(falsey / len(rows) * 100, 1) if rows else 0.0


def _count_unique(values: list) -> dict:
    counts: dict = {}
    for v in values:
        k = str(v) if v is not None else "null"
        counts[k] = counts.get(k, 0) + 1
    return counts
