from __future__ import annotations

from datetime import datetime
from typing import Any

_SAFETY_NET_TERMS = (
    "safety net",
    "symptoms persist",
    "worsen",
    "return sooner",
    "call 999",
    "call 111",
    "not improving",
    "red flag",
    "continue to monitor",
)


def _check_safety_netting(data: dict[str, Any]) -> bool:
    for encounter in data.get("encounters") or []:
        if str(encounter.get("milestone_type") or "") != "first_presentation":
            continue
        text = str(encounter.get("text") or "").lower()
        if any(term in text for term in _SAFETY_NET_TERMS):
            return True
    return False


def _check_investigation_gap(data: dict[str, Any]) -> str | None:
    encounters = list(data.get("encounters") or [])
    milestone_types = {str(e.get("milestone_type") or "") for e in encounters}
    if "referral" in milestone_types and "investigation" not in milestone_types:
        return "Referral recorded without follow-up investigation"
    return None


def _check_referral_wait(data: dict[str, Any]) -> int | None:
    referral_date: datetime | None = None
    follow_up_date: datetime | None = None
    for encounter in data.get("encounters") or []:
        milestone_type = str(encounter.get("milestone_type") or "")
        raw_date = encounter.get("date")
        if not raw_date:
            continue
        try:
            parsed = datetime.fromisoformat(str(raw_date))
        except ValueError:
            continue
        if milestone_type == "referral" and referral_date is None:
            referral_date = parsed
        if (
            milestone_type in {"investigation", "specialist_visit", "diagnosis"}
            and follow_up_date is None
        ):
            follow_up_date = parsed
    if referral_date is None or follow_up_date is None:
        return None
    return (follow_up_date.date() - referral_date.date()).days


def detect_safety_net_signals(
    patient_id: str,
    episode_ids: list[str],
    patient_client,
    _knowledge_client,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for episode_id in episode_ids:
        encounters = list(
            patient_client.run(
                "MATCH (ep:EpisodeOfCare)<-[:IS_PART_OF]-(e:Encounter) RETURN e",
                patient_id=patient_id,
                episode_id=episode_id,
            )
            or []
        )
        if not encounters:
            continue
        episode_data = {"episode_id": episode_id, "encounters": encounters}
        if not _check_safety_netting(episode_data):
            signals.append(
                {
                    "episode_id": episode_id,
                    "patient_id": patient_id,
                    "type": "missing_safety_netting",
                    "severity": "warning",
                    "description": "No safety-netting advice recorded at first presentation",
                }
            )
        gap = _check_investigation_gap(episode_data)
        if gap:
            signals.append(
                {
                    "episode_id": episode_id,
                    "patient_id": patient_id,
                    "type": "investigation_gap",
                    "severity": "warning",
                    "description": gap,
                }
            )
        wait_days = _check_referral_wait(episode_data)
        if wait_days is not None and wait_days > 31:
            signals.append(
                {
                    "episode_id": episode_id,
                    "patient_id": patient_id,
                    "type": "excessive_referral_wait",
                    "severity": "high",
                    "description": f"Referral wait exceeded threshold ({wait_days} days)",
                    "wait_days": wait_days,
                }
            )
    return signals
