"""KPI and quality metric calculator for cancer episodes.

Computes NCDA-aligned metrics:
- Time from first presentation to referral
- Time from referral to diagnosis
- Time from diagnosis to treatment start
- Number of GP consultations before referral
- Safety-netting compliance rate
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def calculate_kpis(
    patient_id: str,
    episode_ids: List[str],
    patient_client,
) -> List[Dict[str, Any]]:
    """Calculate KPI metrics for each episode."""
    all_kpis: list[dict[str, Any]] = []

    for episode_id in episode_ids:
        milestones = _get_milestone_dates(episode_id, patient_client)
        kpis = _compute_episode_kpis(episode_id, milestones, patient_id, patient_client)
        all_kpis.extend(kpis)

        # Persist to graph
        for kpi in kpis:
            _persist_kpi(episode_id, kpi, patient_client)

    return all_kpis


def _get_milestone_dates(episode_id: str, client) -> Dict[str, Optional[str]]:
    rows = client.run(
        "MATCH (e:Encounter)-[r:IS_PART_OF]->(ep:EpisodeOfCare {episode_id: $eid}) "
        "RETURN r.milestone_type AS milestone, min(toString(e.date)) AS earliest_date "
        "ORDER BY earliest_date",
        eid=episode_id,
    )
    result: dict[str, Optional[str]] = {}
    for row in rows:
        mt = row.get("milestone", "")
        d = row.get("earliest_date", "")
        if mt and d:
            result[mt] = d[:10]
    return result


def _compute_episode_kpis(
    episode_id: str,
    milestones: Dict[str, Optional[str]],
    patient_id: str,
    client,
) -> List[Dict[str, Any]]:
    kpis: list[dict[str, Any]] = []

    referral = milestones.get("referral")
    diagnosis = milestones.get("diagnosis")
    treatment = milestones.get("treatment")
    first_pres = milestones.get("first_presentation")

    if first_pres and referral:
        days = _days_between(first_pres, referral)
        if days is not None:
            kpis.append({
                "metric": "days_presentation_to_referral",
                "value": days,
                "unit": "days",
            })

    if referral and diagnosis:
        days = _days_between(referral, diagnosis)
        if days is not None:
            kpis.append({
                "metric": "days_referral_to_diagnosis",
                "value": days,
                "unit": "days",
            })

    if diagnosis and treatment:
        days = _days_between(diagnosis, treatment)
        if days is not None:
            kpis.append({
                "metric": "days_diagnosis_to_treatment",
                "value": days,
                "unit": "days",
            })

    if first_pres and referral:
        consults = _count_consultations(patient_id, first_pres, referral, client)
        kpis.append({
            "metric": "consultations_before_referral",
            "value": consults,
            "unit": "count",
        })

    return kpis


def _days_between(date1: str, date2: str) -> Optional[int]:
    try:
        d1 = datetime.strptime(date1[:10], "%Y-%m-%d")
        d2 = datetime.strptime(date2[:10], "%Y-%m-%d")
        return (d2 - d1).days
    except ValueError:
        return None


def _count_consultations(patient_id: str, start: str, end: str, client) -> int:
    rows = client.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
        "WHERE toString(p.id) = $pid AND toString(e.date) >= $s AND toString(e.date) <= $e "
        "RETURN count(e) AS cnt",
        pid=patient_id, s=start, e=end,
    )
    return rows[0].get("cnt", 0) if rows else 0


def _persist_kpi(episode_id: str, kpi: Dict[str, Any], client) -> None:
    client.run(
        "MATCH (ep:EpisodeOfCare {episode_id: $eid}) "
        "SET ep[$key] = $val",
        eid=episode_id,
        key=f"kpi_{kpi['metric']}",
        val=kpi["value"],
    )
