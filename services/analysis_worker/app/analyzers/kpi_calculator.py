"""Episode KPI calculator.

Computes the four NCDA interval KPIs and persists them as named properties
on EpisodeOfCare nodes. Designed to be invoked as the terminal post-pass of
build_episodes() and any on-demand /episodes/rebuild flow.

KPIs:
  days_presentation_to_referral  -- Primary Care Interval (PCI)
  consultations_before_referral  -- count of encounters in [presentation, referral]
  days_referral_to_diagnosis     -- Diagnostic Interval leg
  days_diagnosis_to_treatment    -- Decision-to-Treat leg

All interval math is delegated to libs.metrics so runtime and
ground-truth export paths produce identical numbers. This module owns
the Neo4j fetch, count-consultations query, and persistence.

See DI-LEO-AI-125, DO-LEO-AI-125, R-LEO-AI-085, VT-LEO-AI-120.
"""

from __future__ import annotations

from typing import Any

from libs.metrics import (
    compute_interval_kpis,
    days_between,
    pick_earliest_milestone,
)


_Q_MILESTONES = (
    "MATCH (e:Encounter)-[r:IS_PART_OF]->(ep:EpisodeOfCare {episode_id: $eid}) "
    "RETURN r.milestone_type AS milestone, min(toString(e.date)) AS earliest_date"
)

_Q_COUNT_CONSULTATIONS = (
    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
    "WHERE toString(p.id) = $pid "
    "  AND toString(e.date) >= $start_date "
    "  AND toString(e.date) <= $end_date "
    "RETURN count(e) AS cnt"
)

_Q_SET_KPI = (
    "MATCH (ep:EpisodeOfCare {episode_id: $eid}) " "SET ep[$metric] = $value"
)

# Milestone key aliases accepted by _compute_episode_kpis. Kept here so the
# runtime analyzer can resolve the presentation+referral window for the
# consultations count -- a Neo4j-bound metric that does not belong in libs.metrics.
_DIAGNOSIS_MILESTONES = ("diagnosis_confirmed", "diagnosis")
_TREATMENT_MILESTONES = ("treatment_started", "treatment")


def _days_between(start_date: str, end_date: str) -> int | None:
    """Thin alias over libs.metrics.days_between for backward compatibility."""
    return days_between(start_date, end_date)


def _count_consultations(
    patient_id: str,
    start_date: str,
    end_date: str,
    patient_client: Any,
) -> int:
    rows = patient_client.run(
        _Q_COUNT_CONSULTATIONS,
        pid=patient_id,
        start_date=start_date,
        end_date=end_date,
    )
    if not rows:
        return 0
    return int(rows[0].get("cnt") or 0)


def _pick_first(milestones: dict[str, str], keys: tuple[str, ...]) -> str | None:
    """Thin alias over libs.metrics.pick_earliest_milestone for compatibility."""
    return pick_earliest_milestone(milestones, keys)


def _compute_episode_kpis(
    episode_id: str,
    milestones: dict[str, str],
    patient_id: str,
    patient_client: Any,
) -> list[dict[str, Any]]:
    _ = episode_id
    out: list[dict[str, Any]] = []

    intervals = compute_interval_kpis(milestones)
    for name, value in intervals.items():
        out.append({"metric": name, "value": value})

    presentation = milestones.get("first_presentation")
    referral = milestones.get("referral")
    if presentation and referral and "days_presentation_to_referral" in intervals:
        out.append(
            {
                "metric": "consultations_before_referral",
                "value": _count_consultations(
                    patient_id, presentation, referral, patient_client
                ),
            }
        )

    return out


def _fetch_milestones(
    patient_client: Any, episode_id: str
) -> dict[str, str]:
    rows = patient_client.run(_Q_MILESTONES, eid=episode_id) or []
    out: dict[str, str] = {}
    for row in rows:
        milestone = str(row.get("milestone") or "")
        earliest = str(row.get("earliest_date") or "")
        if milestone and earliest:
            out[milestone] = earliest
    return out


def _persist_episode_kpis(
    patient_client: Any,
    episode_id: str,
    kpis: list[dict[str, Any]],
) -> None:
    """Write each KPI as a named property on the episode node.

    Uses MATCH (not MERGE) so a missing episode_id is a no-op rather than
    creating an orphan node.
    """
    for row in kpis:
        patient_client.run(
            _Q_SET_KPI,
            eid=episode_id,
            metric=row["metric"],
            value=row["value"],
        )


def calculate_kpis(
    patient_id: str,
    episode_ids: list[str],
    patient_client: Any,
) -> list[dict[str, Any]]:
    """Compute and persist the four NCDA interval KPIs for each episode.

    Returns the flat list of {episode_id, metric, value} for every KPI
    that was successfully written, so callers can log or test the output.
    Missing milestones produce no output -- KPIs are never inferred from
    partial data.
    """
    if not episode_ids:
        return []

    all_kpis: list[dict[str, Any]] = []
    for episode_id in episode_ids:
        milestones = _fetch_milestones(patient_client, episode_id)
        kpis = _compute_episode_kpis(episode_id, milestones, patient_id, patient_client)
        _persist_episode_kpis(patient_client, episode_id, kpis)
        for row in kpis:
            all_kpis.append({"episode_id": episode_id, **row})
    return all_kpis
