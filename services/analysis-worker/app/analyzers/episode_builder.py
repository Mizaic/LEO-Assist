"""Episode builder: creates CancerEpisode nodes and links encounters.

Ported from VRB clinical-ai/app/agent/subagents/episode_builder.py.
Creates episodes from anchors, links milestones, consolidates duplicates.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult

logger = logging.getLogger(__name__)


@dataclass
class EpisodeBuildResult:
    patient_id: str
    episodes_created: int = 0
    episodes_completed: int = 0
    episodes_merged: int = 0
    encounters_linked: int = 0
    episode_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


async def build_episodes(
    patient_id: str,
    anchors: AnchorResult,
    patient_client,
    max_episodes: int = 10,
) -> EpisodeBuildResult:
    result = EpisodeBuildResult(patient_id=patient_id)

    if not anchors.referral_anchors and not anchors.diagnosis_anchors:
        logger.info("No anchors for %s, skipping episode build", patient_id)
        return result

    primary = anchors.referral_anchors or anchors.diagnosis_anchors
    seen_types: set[str] = set()
    unique: list[dict[str, Any]] = []
    for ref in sorted(primary, key=lambda r: (r.get("encounter_date", "") or "")[:10]):
        key = _extract_cancer_key(ref)
        if key not in seen_types:
            seen_types.add(key)
            unique.append(ref)

    for anchor in unique[:max_episodes]:
        try:
            ep = _build_single_episode(patient_id, anchor, anchors, patient_client)
            if ep:
                result.episodes_created += 1
                result.encounters_linked += ep.get("encounters_linked", 0)
                result.episode_ids.append(ep["episode_id"])
                if ep.get("status") in ("confirmed", "excluded"):
                    result.episodes_completed += 1
        except Exception as exc:
            result.errors.append(str(exc))
            logger.error("Episode build error: %s", exc)

    if result.episodes_created >= 2:
        result.episodes_merged = _try_consolidate(result.episode_ids, patient_client)

    return result


def _extract_cancer_key(ref: Dict[str, Any]) -> str:
    name = (ref.get("concept_name") or "").lower()
    for prefix in ("fast track referral for suspected ", "suspected ", "diagnosis of "):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name.replace("cancer", "").replace("carcinoma", "").strip() or "unknown"


def _build_single_episode(
    patient_id: str,
    anchor: Dict[str, Any],
    anchors: AnchorResult,
    patient_client,
) -> Optional[Dict[str, Any]]:
    anchor_date = (anchor.get("encounter_date", "") or "")[:10]
    anchor_id = anchor.get("encounter_id", "")
    cancer_type = _simplify_cancer_type(anchor.get("concept_name", "Unknown"))
    episode_id = str(uuid.uuid4())

    patient_client.run(
        "MERGE (ep:CancerEpisode {episode_id: $eid}) "
        "SET ep.patient_id = $pid, ep.cancer_type = $ct, ep.status = 'pending', "
        "    ep.referral_date = $rd, ep.created_at = datetime()",
        eid=episode_id, pid=patient_id, ct=cancer_type, rd=anchor_date,
    )

    linked = 1
    linked_ids = {anchor_id}

    # Link anchor encounter
    _link_encounter(anchor_id, episode_id, "referral", patient_client)

    # Link diagnosis anchors
    for diag in anchors.diagnosis_anchors:
        eid = diag.get("encounter_id", "")
        if eid not in linked_ids:
            _link_encounter(eid, episode_id, "diagnosis", patient_client)
            linked_ids.add(eid)
            linked += 1

    # Link pre-referral (first presentation)
    try:
        ref_dt = datetime.strptime(anchor_date, "%Y-%m-%d")
        pre_start = (ref_dt - timedelta(days=30)).strftime("%Y-%m-%d")
        pre_encounters = patient_client.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid AND toString(e.date) >= $s AND toString(e.date) < $e "
            "RETURN e.id AS encounter_id ORDER BY e.date LIMIT 1",
            pid=patient_id, s=pre_start, e=anchor_date,
        )
        if pre_encounters:
            eid = str(pre_encounters[0]["encounter_id"])
            if eid not in linked_ids:
                _link_encounter(eid, episode_id, "first_presentation", patient_client)
                linked_ids.add(eid)
                linked += 1
    except ValueError:
        pass

    return {
        "episode_id": episode_id,
        "status": "pending",
        "encounters_linked": linked,
    }


def _simplify_cancer_type(name: str) -> str:
    name = name.replace("Fast track referral for suspected ", "").replace("cancer", "").strip()
    return name or "Unknown"


def _link_encounter(encounter_id, episode_id, milestone_type, client):
    client.run(
        "MATCH (e:Encounter {id: $eid}) "
        "MATCH (ep:CancerEpisode {episode_id: $epid}) "
        "MERGE (e)-[r:IS_PART_OF]->(ep) "
        "SET r.milestone_type = $mt, r.linked_at = datetime()",
        eid=encounter_id, epid=episode_id, mt=milestone_type,
    )


def _try_consolidate(episode_ids: List[str], patient_client) -> int:
    """Merge episodes that share encounters or have overlapping date ranges.

    Ported from VRB episode_consolidator.py.
    """
    if len(episode_ids) < 2:
        return 0

    merged = 0
    for i in range(len(episode_ids) - 1):
        for j in range(i + 1, len(episode_ids)):
            overlap = patient_client.run(
                "MATCH (e:Encounter)-[:IS_PART_OF]->(ep1:CancerEpisode {episode_id: $ep1}) "
                "MATCH (e)-[:IS_PART_OF]->(ep2:CancerEpisode {episode_id: $ep2}) "
                "RETURN count(e) AS shared",
                ep1=episode_ids[i], ep2=episode_ids[j],
            )
            if overlap and overlap[0].get("shared", 0) > 0:
                patient_client.run(
                    "MATCH (e:Encounter)-[r:IS_PART_OF]->(ep2:CancerEpisode {episode_id: $ep2}) "
                    "MATCH (ep1:CancerEpisode {episode_id: $ep1}) "
                    "MERGE (e)-[:IS_PART_OF]->(ep1) "
                    "DELETE r "
                    "WITH ep2 WHERE NOT EXISTS((ep2)<-[:IS_PART_OF]-()) "
                    "SET ep2.status = 'merged'",
                    ep1=episode_ids[i], ep2=episode_ids[j],
                )
                merged += 1

    return merged
