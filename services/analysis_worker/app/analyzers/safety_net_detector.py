"""Clinical Safety Signal (safety-net) and Unwarranted Variation detector.

Identifies NG12 pathway signals, safety-netting gaps, and safety-net alerts
by scanning episodes and coded encounter data against guideline pathways.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_SAFETY_NETTING_PATTERNS = (
    "safety net", "safety-net", "if symptoms persist",
    "return if", "re-attend if", "seek help if", "advised to re",
)

_INVESTIGATION_CONCEPTS = frozenset([
    "colonoscopy", "ct scan", "mri", "ultrasound", "biopsy",
    "endoscopy", "sigmoidoscopy", "blood test",
])


def detect_safety_net_signals(
    patient_id: str,
    episode_ids: List[str],
    patient_client,
    knowledge_client,
) -> List[Dict[str, Any]]:
    """Detect CSS and unwarranted variation signals across episodes."""
    signals: list[dict[str, Any]] = []

    for episode_id in episode_ids:
        episode_data = _load_episode_data(episode_id, patient_client)
        if not episode_data:
            continue

        safety_net = _check_safety_netting(episode_data)
        if not safety_net:
            signals.append({
                "type": "missing_safety_netting",
                "episode_id": episode_id,
                "severity": "warning",
                "description": "No safety-netting language found in pre-referral encounters",
            })

        investigation_gap = _check_investigation_gap(episode_data)
        if investigation_gap:
            signals.append({
                "type": "investigation_gap",
                "episode_id": episode_id,
                "severity": "alert",
                "description": investigation_gap,
            })

        wait_time = _check_referral_wait(episode_data)
        if wait_time and wait_time > 14:
            signals.append({
                "type": "excessive_referral_wait",
                "episode_id": episode_id,
                "severity": "alert",
                "description": f"Referral to first specialist contact: {wait_time} days (target: 14)",
                "value": wait_time,
            })

    return signals


def _load_episode_data(episode_id: str, client) -> Dict[str, Any]:
    rows = client.run(
        "MATCH (e:Encounter)-[r:IS_PART_OF]->(ep:EpisodeOfCare {episode_id: $eid}) "
        "RETURN e.id AS encounter_id, e.text AS text, e.date AS date, "
        "       r.milestone_type AS milestone_type "
        "ORDER BY e.date",
        eid=episode_id,
    )
    return {"episode_id": episode_id, "encounters": rows} if rows else {}


def _check_safety_netting(episode_data: Dict[str, Any]) -> bool:
    for enc in episode_data.get("encounters", []):
        if enc.get("milestone_type") in ("first_presentation", "referral"):
            text = (str(enc.get("text", "")) or "").lower()
            if any(p in text for p in _SAFETY_NETTING_PATTERNS):
                return True
    return False


def _check_investigation_gap(episode_data: Dict[str, Any]) -> str | None:
    has_referral = False
    has_investigation = False
    for enc in episode_data.get("encounters", []):
        mt = enc.get("milestone_type", "")
        if mt == "referral":
            has_referral = True
        if mt == "investigation":
            has_investigation = True
    if has_referral and not has_investigation:
        return "No investigation encounter found after referral"
    return None


def _check_referral_wait(episode_data: Dict[str, Any]) -> int | None:
    referral_date = None
    specialist_date = None
    for enc in episode_data.get("encounters", []):
        mt = enc.get("milestone_type", "")
        d = str(enc.get("date", ""))[:10]
        if mt == "referral" and d:
            referral_date = d
        if mt in ("specialist_visit", "investigation") and d:
            if specialist_date is None or d < specialist_date:
                specialist_date = d
    if referral_date and specialist_date:
        try:
            from datetime import datetime
            rd = datetime.strptime(referral_date, "%Y-%m-%d")
            sd = datetime.strptime(specialist_date, "%Y-%m-%d")
            return (sd - rd).days
        except ValueError:
            pass
    return None
