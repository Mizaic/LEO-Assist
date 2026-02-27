"""Pathway Timepoints: identifies and persists the 6 critical timepoints
in a cancer pathway as PathwayTimepoint nodes linked to EpisodeOfCare.

Timepoints:
1. Presentation      -- Patient first presents with symptoms
2. Referral          -- 2WW or urgent referral made
3. First Clinic      -- First outpatient appointment
4. Diagnosis         -- Definitive diagnosis confirmed
5. Treatment Decision -- Treatment plan decided
6. First Treatment   -- Treatment started

Schema:
- (EpisodeOfCare)-[:HAS_TIMEPOINT]->(PathwayTimepoint)
- (PathwayTimepoint)-[:AT_ENCOUNTER]->(Encounter)

Ported from VRB clinical-ai/app/agent/tools/pathway_timepoints.py.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)


PATHWAY_TIMEPOINTS = {
    "presentation": {
        "order": 1,
        "label": "First Presentation",
        "description": "Patient first presents with symptoms",
        "milestone_types": ["first_presentation"],
    },
    "referral": {
        "order": 2,
        "label": "Referral Sent",
        "description": "2WW or urgent referral made",
        "milestone_types": ["referral_sent", "referral"],
    },
    "first_clinic": {
        "order": 3,
        "label": "First Clinic Visit",
        "description": "First outpatient appointment",
        "milestone_types": ["first_clinic_visit", "clinic_visit", "specialist_visit"],
    },
    "diagnosis": {
        "order": 4,
        "label": "Diagnosis Confirmed",
        "description": "Definitive diagnosis made",
        "milestone_types": ["diagnosis_confirmed", "diagnosis"],
    },
    "treatment_decision": {
        "order": 5,
        "label": "Treatment Decision",
        "description": "Treatment plan decided",
        "milestone_types": ["treatment_decision"],
    },
    "first_treatment": {
        "order": 6,
        "label": "First Treatment",
        "description": "Treatment started",
        "milestone_types": ["treatment_started", "treatment"],
    },
}


def _default_client() -> PatientGraphClient:
    return PatientGraphClient()


# ── Timepoint Identification ─────────────────────────────────────────


def identify_timepoints_from_episode(
    episode_id: str,
    client: Optional[PatientGraphClient] = None,
) -> Dict[str, Any]:
    """Identify the 6 critical timepoints from encounters linked to an episode."""
    encounters = _fetch_episode_encounters(episode_id, client)
    return _map_encounters_to_timepoints(encounters, episode_id)


def _fetch_episode_encounters(
    episode_id: str,
    client: Optional[PatientGraphClient] = None,
) -> List[Dict[str, Any]]:
    c = client or _default_client()
    return c.run(
        "MATCH (e:Encounter)-[r:IS_PART_OF]->(ep:EpisodeOfCare {episode_id: $eid}) "
        "RETURN e.id AS encounter_id, toString(e.date) AS date, "
        "       r.milestone_type AS milestone_type "
        "ORDER BY e.date ASC",
        eid=episode_id,
    )


def _map_encounters_to_timepoints(
    encounters: List[Dict[str, Any]],
    episode_id: str,
) -> Dict[str, Any]:
    if not encounters:
        return _empty_result(episode_id)

    timepoints: Dict[str, Dict[str, Any]] = {}

    for tp_key, tp_info in PATHWAY_TIMEPOINTS.items():
        milestone_types = tp_info["milestone_types"]
        for enc in encounters:
            enc_ms = enc.get("milestone_type") or ""
            if enc_ms in milestone_types:
                timepoints[tp_key] = {
                    "encounter_id": enc["encounter_id"],
                    "date": enc.get("date"),
                    "milestone_matched": enc_ms,
                    "confidence": _calc_confidence(enc_ms),
                }
                break

    intervals = _calculate_intervals(timepoints)
    missing = [k for k in PATHWAY_TIMEPOINTS if k not in timepoints]
    total = len(PATHWAY_TIMEPOINTS)

    return {
        "episode_id": episode_id,
        "timepoints": timepoints,
        "intervals": intervals,
        "completeness_score": len(timepoints) / total if total else 0.0,
        "missing_timepoints": missing,
    }


def _empty_result(episode_id: str) -> Dict[str, Any]:
    return {
        "episode_id": episode_id,
        "timepoints": {},
        "intervals": {},
        "completeness_score": 0.0,
        "missing_timepoints": list(PATHWAY_TIMEPOINTS.keys()),
    }


def _calc_confidence(matched_milestone: str) -> float:
    exact = {
        "first_presentation", "referral_sent", "diagnosis_confirmed",
        "treatment_started",
    }
    return 0.95 if matched_milestone in exact else 0.75


# ── Interval Calculation ──────────────────────────────────────────────


def _calculate_intervals(
    timepoints: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    ordered = [
        "presentation", "referral", "first_clinic",
        "diagnosis", "treatment_decision", "first_treatment",
    ]
    intervals: Dict[str, Any] = {}

    for i in range(len(ordered) - 1):
        cur, nxt = ordered[i], ordered[i + 1]
        days = _days_between(timepoints.get(cur), timepoints.get(nxt))
        if days is not None:
            intervals[f"{cur}_to_{nxt}"] = days

    _add_nhs_intervals(timepoints, intervals)
    return intervals


def _days_between(
    tp_a: Optional[Dict[str, Any]],
    tp_b: Optional[Dict[str, Any]],
) -> Optional[int]:
    if not tp_a or not tp_b:
        return None
    try:
        d1 = datetime.fromisoformat(str(tp_a["date"])[:10])
        d2 = datetime.fromisoformat(str(tp_b["date"])[:10])
        return (d2 - d1).days
    except (ValueError, TypeError, KeyError):
        return None


def _add_nhs_intervals(
    timepoints: Dict[str, Dict[str, Any]],
    intervals: Dict[str, Any],
) -> None:
    rtt = _days_between(timepoints.get("referral"), timepoints.get("first_treatment"))
    if rtt is not None:
        intervals["referral_to_treatment"] = rtt
        intervals["is_62day_breach"] = rtt > 62

    dtt = _days_between(timepoints.get("diagnosis"), timepoints.get("first_treatment"))
    if dtt is not None:
        intervals["diagnosis_to_treatment"] = dtt
        intervals["is_31day_breach"] = dtt > 31

    fds = _days_between(timepoints.get("referral"), timepoints.get("diagnosis"))
    if fds is not None:
        intervals["referral_to_diagnosis"] = fds
        intervals["is_28day_breach"] = fds > 28


# ── Persist to Neo4j ──────────────────────────────────────────────────


def persist_episode_timepoints(
    episode_id: str,
    timepoints_result: Dict[str, Any],
    client: Optional[PatientGraphClient] = None,
) -> Dict[str, int]:
    """Persist identified timepoints to Neo4j as PathwayTimepoint nodes."""
    timepoints = timepoints_result.get("timepoints", {})
    counts = {"timepoints_created": 0, "errors": 0}

    for tp_type, tp_data in timepoints.items():
        created = _create_single_timepoint(episode_id, tp_type, tp_data, client)
        if created:
            counts["timepoints_created"] += 1
        else:
            counts["errors"] += 1

    logger.info("Persisted timepoints for episode %s: %s", episode_id, counts)
    return counts


def _create_single_timepoint(
    episode_id: str,
    tp_type: str,
    tp_data: Dict[str, Any],
    client: Optional[PatientGraphClient] = None,
) -> bool:
    encounter_id = tp_data.get("encounter_id")
    date_str = tp_data.get("date")
    confidence = tp_data.get("confidence", 0.8)

    if not encounter_id or not date_str:
        return False

    tp_id = f"TP_{episode_id}_{tp_type}_{uuid4().hex[:8]}"
    tp_info = PATHWAY_TIMEPOINTS.get(tp_type, {})
    c = client or _default_client()

    try:
        c.run(
            "MATCH (ep:EpisodeOfCare {episode_id: $eid}) "
            "MATCH (enc:Encounter {id: $enc_id}) "
            "MERGE (tp:PathwayTimepoint {timepoint_id: $tp_id}) "
            "ON CREATE SET tp.episode_id = $eid, tp.encounter_id = $enc_id, "
            "              tp.timepoint_type = $tp_type, "
            "              tp.date = $date_str, tp.confidence = $conf, "
            "              tp.label = $label, tp.order_index = $order_idx, "
            "              tp.created_at = datetime(), "
            "              tp.created_by = 'pathway_timepoints' "
            "MERGE (ep)-[:HAS_TIMEPOINT]->(tp) "
            "MERGE (tp)-[:AT_ENCOUNTER]->(enc) "
            "RETURN tp.timepoint_id AS timepoint_id",
            eid=episode_id, enc_id=encounter_id, tp_id=tp_id,
            tp_type=tp_type, date_str=str(date_str)[:10],
            conf=confidence, label=tp_info.get("label", tp_type),
            order_idx=tp_info.get("order", 0),
        )
        return True
    except Exception as exc:
        logger.error("Failed to create timepoint %s: %s", tp_id, exc)
        return False


# ── NHS Compliance ────────────────────────────────────────────────────


def calculate_nhs_compliance(
    timepoints_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Calculate NHS pathway target compliance from timepoint intervals."""
    intervals = timepoints_result.get("intervals", {})
    targets: Dict[str, Dict[str, Any]] = {}

    _check_target(targets, intervals, "referral_to_treatment", 62, "62_day_target",
                  "Referral to first treatment within 62 days")
    _check_target(targets, intervals, "diagnosis_to_treatment", 31, "31_day_target",
                  "Diagnosis to first treatment within 31 days")
    _check_target(targets, intervals, "referral_to_diagnosis", 28, "28_day_fds",
                  "Referral to diagnosis within 28 days (FDS)")

    return {
        "nhs_targets": targets,
        "all_compliant": all(t.get("compliant", True) for t in targets.values()),
        "breach_count": sum(1 for t in targets.values() if not t.get("compliant", True)),
    }


def _check_target(
    targets: Dict[str, Dict[str, Any]],
    intervals: Dict[str, Any],
    interval_key: str,
    target_days: int,
    target_name: str,
    description: str,
) -> None:
    if interval_key not in intervals:
        return
    days = intervals[interval_key]
    targets[target_name] = {
        "days": days,
        "target_days": target_days,
        "compliant": days <= target_days,
        "description": description,
    }
