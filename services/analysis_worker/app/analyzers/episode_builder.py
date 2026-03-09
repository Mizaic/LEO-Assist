from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult


@dataclass
class EpisodeBuildResult:
    patient_id: str
    episodes_created: int = 0
    episodes_completed: int = 0
    episodes_merged: int = 0
    encounters_linked: int = 0
    episode_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _extract_condition_key(anchor: dict[str, Any]) -> str:
    concept_name = str(anchor.get("concept_name") or "").lower().strip()
    if not concept_name:
        return "unknown"
    prefixes = (
        "fast track referral for suspected ",
        "suspected ",
        "diagnosis of ",
        "confirmed ",
    )
    for prefix in prefixes:
        if concept_name.startswith(prefix):
            concept_name = concept_name[len(prefix):]
    concept_name = concept_name.replace("carcinoma", "").replace("cancer", "").strip()
    generic_terms = {"adenocarcinoma", "carcinoma", "malignancy", "cancer", "neoplasm", "tumour", "tumor"}
    if concept_name in generic_terms:
        return "unknown"
    return concept_name.split()[0] if concept_name else "unknown"


async def build_episodes(
    patient_id: str,
    anchors: AnchorResult,
    patient_client,
) -> EpisodeBuildResult:
    result = EpisodeBuildResult(patient_id=patient_id)
    if not anchors.referral_anchors and not anchors.diagnosis_anchors:
        return result

    grouped: dict[str, list[dict[str, Any]]] = {}
    referral_keys: list[str] = []
    for anchor in list(anchors.referral_anchors):
        key = _extract_condition_key(anchor)
        grouped.setdefault(key, []).append(anchor)
        if key not in referral_keys:
            referral_keys.append(key)
    for anchor in list(anchors.diagnosis_anchors):
        key = _extract_condition_key(anchor)
        concept_name = str(anchor.get("concept_name") or "").lower()
        if referral_keys and (key == "unknown" or all(ref_key not in concept_name for ref_key in referral_keys)):
            key = referral_keys[0]
        grouped.setdefault(key, []).append(anchor)

    for condition_key, rows in grouped.items():
        rows.sort(key=lambda row: str(row.get("encounter_date") or ""))
        episode_id = hashlib.sha256(f"{patient_id}|{condition_key}".encode()).hexdigest()[:16]
        result.episode_ids.append(episode_id)
        result.episodes_created += 1
        result.encounters_linked += len({str(r.get("encounter_id") or "") for r in rows if r.get("encounter_id")})
        try:
            patient_client.run(
                "MERGE (ep:EpisodeOfCare {episode_id: $episode_id}) RETURN ep",
                patient_id=patient_id,
                episode_id=episode_id,
                condition_type=condition_key,
            )
            for row in rows:
                encounter_date = str(row.get("encounter_date") or "")
                if encounter_date:
                    datetime.fromisoformat(encounter_date)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(str(exc))

    return result
