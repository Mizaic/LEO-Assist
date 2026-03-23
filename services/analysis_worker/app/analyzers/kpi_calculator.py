from __future__ import annotations

from datetime import date
from typing import Any


def _days_between(start_date: str, end_date: str) -> int | None:
    try:
        start = date.fromisoformat(str(start_date))
        end = date.fromisoformat(str(end_date))
    except (TypeError, ValueError):
        return None
    return (end - start).days


def _count_consultations(
    patient_id: str,
    start_date: str,
    end_date: str,
    patient_client: Any,
) -> int:
    rows = patient_client.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
        "WHERE toString(p.id) = $pid "
        "  AND toString(e.date) >= $start_date "
        "  AND toString(e.date) <= $end_date "
        "RETURN count(e) AS cnt",
        pid=patient_id,
        start_date=start_date,
        end_date=end_date,
    )
    if not rows:
        return 0
    return int(rows[0].get("cnt") or 0)


def _compute_episode_kpis(
    episode_id: str,
    milestones: dict[str, str],
    patient_id: str,
    patient_client: Any,
) -> list[dict[str, Any]]:
    _ = episode_id
    out: list[dict[str, Any]] = []

    presentation = milestones.get("first_presentation")
    referral = milestones.get("referral")
    diagnosis = milestones.get("diagnosis")
    treatment = milestones.get("treatment")

    if presentation and referral:
        delta = _days_between(presentation, referral)
        if delta is not None:
            out.append({"metric": "days_presentation_to_referral", "value": delta})
            out.append(
                {
                    "metric": "consultations_before_referral",
                    "value": _count_consultations(
                        patient_id, presentation, referral, patient_client
                    ),
                }
            )

    if referral and diagnosis:
        delta = _days_between(referral, diagnosis)
        if delta is not None:
            out.append({"metric": "days_referral_to_diagnosis", "value": delta})

    if diagnosis and treatment:
        delta = _days_between(diagnosis, treatment)
        if delta is not None:
            out.append({"metric": "days_diagnosis_to_treatment", "value": delta})

    return out


def calculate_kpis(
    patient_id: str,
    episode_ids: list[str],
    patient_client: Any,
) -> list[dict[str, Any]]:
    if not episode_ids:
        return []

    all_kpis: list[dict[str, Any]] = []
    for episode_id in episode_ids:
        rows = patient_client.run(
            "MATCH (e:Encounter)-[r:IS_PART_OF]->(ep:EpisodeOfCare {episode_id: $eid}) "
            "RETURN r.milestone_type AS milestone, min(toString(e.date)) AS earliest_date",
            eid=episode_id,
        )
        milestones = {
            str(r.get("milestone") or ""): str(r.get("earliest_date") or "")
            for r in (rows or [])
            if r.get("milestone") and r.get("earliest_date")
        }
        kpis = _compute_episode_kpis(episode_id, milestones, patient_id, patient_client)
        for row in kpis:
            patient_client.run(
                "MERGE (ep:EpisodeOfCare {episode_id: $eid}) "
                "SET ep[$metric] = $value",
                eid=episode_id,
                metric=row["metric"],
                value=row["value"],
            )
        all_kpis.extend(kpis)
    return all_kpis
