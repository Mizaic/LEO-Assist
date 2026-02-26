"""Episode builder: creates CancerEpisode nodes and links encounters.

Full VRB parity: creates episodes from anchors, links milestones
(pre-referral, post-referral coded + uncoded), classifies via LLM,
persists NCDA fields and pathway timepoints, and triggers consolidation.

Ported from VRB clinical-ai/app/agent/subagents/episode_builder.py.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from libs.agent_config import get_agent_prompt, get_agent_property
from libs.llm_client.json_helper import invoke_llm_json
from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult
from services.analysis_worker.app.analyzers.episode_consolidator import try_consolidate
from services.analysis_worker.app.analyzers.pathway_timepoints import (
    identify_timepoints_from_episode,
    persist_episode_timepoints,
)
from services.analysis_worker.app.prompts.episode_prompts import (
    EPISODE_BUILDER_SYSTEM,
    EPISODE_BUILDER_TASK,
)
from services.analysis_worker.app.queries.episode_queries import (
    complete_episode,
    create_episode,
    get_earliest_episode_milestone_dates,
    get_encounter_full_text,
    get_encounters_by_timeframe,
    get_encounters_with_codes,
    get_episode_place_of_presentation,
    link_encounter_to_episode,
    set_episode_ncda_fields,
)

logger = logging.getLogger(__name__)


@dataclass
class EpisodeBuildResult:
    patient_id: str
    episodes_created: int = 0
    episodes_completed: int = 0
    episodes_merged: int = 0
    encounters_linked: int = 0
    timepoints_created: int = 0
    episode_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0


async def build_episodes(
    patient_id: str,
    anchors: AnchorResult,
    patient_client=None,
    max_episodes: Optional[int] = None,
) -> EpisodeBuildResult:
    """Build cancer episodes from detected anchors.

    For each referral anchor:
    1. Create a CancerEpisode
    2. Link the referral encounter
    3. Search for and link milestone encounters (pre/post-referral)
    4. Classify episode status using LLM
    5. Persist NCDA fields and pathway timepoints
    """
    start = time.time()
    result = EpisodeBuildResult(patient_id=patient_id)

    if max_episodes is None:
        max_episodes = int(get_agent_property("episode-builder", "maxEpisodes", 10))

    if not anchors.referral_anchors:
        if anchors.diagnosis_anchors or anchors.treatment_anchors:
            return await _build_non_referral_episodes(
                patient_id, anchors, result, max_episodes, start, patient_client
            )
        logger.info("No anchors found for %s, skipping episode build", patient_id)
        result.duration_ms = (time.time() - start) * 1000
        return result

    seen_types: set = set()
    unique_referrals: List[Dict[str, Any]] = []
    sorted_refs = sorted(
        anchors.referral_anchors,
        key=lambda r: (r.get("encounter_date", "") or "")[:10],
    )
    for ref in sorted_refs:
        cancer_key = _extract_cancer_key(ref)
        if cancer_key not in seen_types:
            seen_types.add(cancer_key)
            unique_referrals.append(ref)

    for referral in unique_referrals[:max_episodes]:
        try:
            episode_result = await _build_single_episode(
                patient_id, referral, anchors,
                anchor_type="referral", client=patient_client,
            )
            if episode_result:
                result.episodes_created += 1
                if episode_result.get("status") in ("confirmed", "excluded", "inconclusive"):
                    result.episodes_completed += 1
                result.encounters_linked += episode_result.get("encounters_linked", 0)
                result.timepoints_created += episode_result.get("timepoints_created", 0)
                result.episode_ids.append(episode_result.get("episode_id", ""))
        except Exception as exc:
            ref_id = referral.get("encounter_id", "unknown")
            result.errors.append(f"Episode build failed for referral {ref_id}: {exc}")
            logger.error("Episode build error: %s", exc)

    if result.episodes_created >= 2:
        result.episodes_merged = await try_consolidate(
            patient_id, result.episode_ids, result.errors, client=patient_client,
        )

    result.duration_ms = (time.time() - start) * 1000
    logger.info(
        "Episode builder for %s: %d created, %d completed, %d merged (%.0fms)",
        patient_id, result.episodes_created, result.episodes_completed,
        result.episodes_merged, result.duration_ms,
    )
    return result


def _extract_cancer_key(ref: Dict[str, Any]) -> str:
    name = (ref.get("concept_name") or "").lower()
    for prefix in (
        "fast track referral for suspected ", "suspected ",
        "diagnosis of ", "confirmed ", "biopsy confirmed ",
    ):
        if name.startswith(prefix):
            name = name[len(prefix):]
    name = name.replace("lower gastrointestinal", "lower gi")
    name = name.replace("upper gi (gastrointestinal)", "upper gi")
    if "(" in name:
        name = name.split("(")[0].strip()
    return name.strip().replace("cancer", "").replace("carcinoma", "").strip() or "unknown"


async def _build_non_referral_episodes(
    patient_id: str,
    anchors: AnchorResult,
    result: EpisodeBuildResult,
    max_episodes: int,
    start: float,
    client=None,
) -> EpisodeBuildResult:
    """Build episodes when no referral anchor exists (A&E / secondary care path)."""
    primary = anchors.diagnosis_anchors or anchors.treatment_anchors
    anchor_type = "diagnosis" if anchors.diagnosis_anchors else "treatment"

    logger.info(
        "No referral for %s -- building from %d %s anchor(s)",
        patient_id, len(primary), anchor_type,
    )

    seen_types: set = set()
    unique_anchors: List[Dict[str, Any]] = []
    for anchor in sorted(primary, key=lambda r: (r.get("encounter_date", "") or "")[:10]):
        key = _extract_cancer_key(anchor)
        if key not in seen_types:
            seen_types.add(key)
            unique_anchors.append(anchor)

    for anchor in unique_anchors[:max_episodes]:
        try:
            ep = await _build_single_episode(
                patient_id, anchor, anchors,
                anchor_type=anchor_type, client=client,
            )
            if ep:
                result.episodes_created += 1
                if ep.get("status") in ("confirmed", "excluded", "inconclusive"):
                    result.episodes_completed += 1
                result.encounters_linked += ep.get("encounters_linked", 0)
                result.timepoints_created += ep.get("timepoints_created", 0)
                result.episode_ids.append(ep.get("episode_id", ""))
        except Exception as exc:
            anc_id = anchor.get("encounter_id", "unknown")
            result.errors.append(f"Non-referral episode failed for {anc_id}: {exc}")
            logger.error("Non-referral episode build error: %s", exc)

    if result.episodes_created >= 2:
        result.episodes_merged = await try_consolidate(
            patient_id, result.episode_ids, result.errors, client=client,
        )

    result.duration_ms = (time.time() - start) * 1000
    logger.info(
        "Non-referral episodes for %s: %d created, %d completed (%.0fms)",
        patient_id, result.episodes_created, result.episodes_completed,
        result.duration_ms,
    )
    return result


async def _build_single_episode(
    patient_id: str,
    referral: Dict[str, Any],
    anchors: AnchorResult,
    anchor_type: str = "referral",
    client=None,
) -> Dict[str, Any]:
    ref_date = (referral.get("encounter_date", "") or "")[:10]
    ref_id = referral.get("encounter_id", "")
    cancer_type = referral.get("concept_name", "Unknown")

    if "(" in cancer_type:
        cancer_type = cancer_type.split("(")[0].strip()
    cancer_type = (
        cancer_type.replace("Fast track referral for suspected ", "")
        .replace("cancer", "")
        .strip()
    )
    if not cancer_type:
        cancer_type = "Unknown"

    ep = create_episode(patient_id, cancer_type, ref_id, ref_date, client=client)
    episode_id = ep.get("episode_id", "")
    if not episode_id:
        return {"error": "Failed to create episode"}

    linked = 1
    linked_ids: set = {ref_id}

    linked += _link_anchors(
        anchors.diagnosis_anchors, ref_date, episode_id, "diagnosis", linked_ids,
        client=client,
    )

    # Treatment: no date gate (may predate GP coding)
    linked += _link_anchors(
        anchors.treatment_anchors, ref_date, episode_id, "treatment", linked_ids,
        require_after=False, client=client,
    )

    linked += _link_pre_referral(patient_id, ref_date, episode_id, linked_ids, client=client)
    linked += _link_post_referral(patient_id, ref_date, episode_id, linked_ids, client=client)

    classification = await _classify_episode(
        patient_id, episode_id, cancer_type, ref_date, anchors, anchor_type,
    )
    if isinstance(classification, list):
        classification = classification[0] if classification and isinstance(classification[0], dict) else {}
    if not isinstance(classification, dict):
        classification = {}

    status = classification.get("status", "inconclusive")
    confidence = classification.get("confidence", 50)
    reasoning = classification.get("reasoning", "LLM classification")

    linked_dates = get_earliest_episode_milestone_dates(episode_id, client=client)
    milestones: Dict[str, str] = {}
    if linked_dates.get("treatment"):
        milestones["treatment_start"] = linked_dates["treatment"]
    if linked_dates.get("diagnosis"):
        milestones["diagnosis"] = linked_dates["diagnosis"]

    if classification.get("diagnosis_date"):
        milestones["diagnosis"] = classification["diagnosis_date"]
    if classification.get("treatment_date"):
        milestones["treatment_start"] = classification["treatment_date"]

    complete_episode(episode_id, status, confidence, reasoning,
                     milestones or None, client=client)

    _persist_ncda_fields(episode_id, anchor_type, client=client)
    tp_counts = _persist_timepoints(episode_id, client=client)

    return {
        "episode_id": episode_id,
        "status": status,
        "confidence": confidence,
        "encounters_linked": linked,
        "timepoints_created": tp_counts,
    }


# ── Safety-netting detection ────────────────────────────────────────────

_SAFETY_NETTING_PATTERNS = (
    "safety net", "safety-net", "if symptoms persist",
    "return if", "re-attend if", "seek help if", "advised to re",
)


def _detect_safety_netting(episode_id: str, client=None) -> bool:
    from libs.neo4j_client.client import PatientGraphClient
    c = client or PatientGraphClient()
    rows = c.run(
        "MATCH (e:Encounter)-[r:IS_PART_OF]->(ep:CancerEpisode {episode_id: $eid}) "
        "WHERE r.milestone_type IN ['first_presentation', 'referral'] "
        "RETURN coalesce(e.text, '') AS text LIMIT 10",
        eid=episode_id,
    )
    for row in rows:
        text = (row.get("text") or "").lower()
        if any(p in text for p in _SAFETY_NETTING_PATTERNS):
            return True
    return False


def _persist_ncda_fields(episode_id: str, anchor_type: str, client=None) -> None:
    referral_route = "two_week_wait" if anchor_type == "referral" else "non_referral"
    place = get_episode_place_of_presentation(episode_id, client=client)
    safety = _detect_safety_netting(episode_id, client=client)

    set_episode_ncda_fields(
        episode_id,
        referral_route=referral_route,
        place_of_presentation=place,
        safety_netting_recorded=safety if safety else None,
        client=client,
    )
    logger.info(
        "NCDA fields for %s: route=%s place=%s safety_net=%s",
        episode_id, referral_route, place, safety,
    )


# ── Anchor + encounter linking ───────────────────────────────────────────


def _link_anchors(
    anchors: List[Dict[str, Any]],
    ref_date: str,
    episode_id: str,
    milestone: str,
    linked_ids: set,
    require_after: bool = True,
    client=None,
) -> int:
    for anchor in anchors:
        enc_id = anchor.get("encounter_id", "")
        anchor_date = (anchor.get("encounter_date", "") or "")[:10]
        date_ok = (not require_after) or (anchor_date >= ref_date)
        if date_ok and enc_id not in linked_ids:
            link_encounter_to_episode(enc_id, episode_id, milestone,
                                      f"{milestone} anchor", client=client)
            linked_ids.add(enc_id)
            return 1
    return 0


def _link_pre_referral(
    patient_id: str, ref_date: str, episode_id: str, linked_ids: set, client=None,
) -> int:
    pre_days = int(get_agent_property("episode-builder", "preReferralDays", 30))
    pre_limit = int(get_agent_property("episode-builder", "preReferralLimit", 5))
    try:
        ref_dt = datetime.strptime(ref_date, "%Y-%m-%d")
        pre_start = (ref_dt - timedelta(days=pre_days)).strftime("%Y-%m-%d")
        pre_enc = get_encounters_by_timeframe(patient_id, pre_start, ref_date,
                                              client=client, limit=pre_limit)
        if pre_enc:
            first = pre_enc[0]
            enc_id = str(first["encounter_id"])
            if enc_id not in linked_ids:
                link_encounter_to_episode(
                    enc_id, episode_id, "first_presentation",
                    "Earliest encounter before referral", client=client,
                )
                linked_ids.add(enc_id)
                return 1
    except ValueError:
        pass
    return 0


_CLINIC_KEYWORDS = frozenset([
    "fast track", "suspected", "clinic", "seen in", "seen by",
    "consultation", "specialist", "outpatient",
])

_INVESTIGATION_KEYWORDS = frozenset([
    "colonoscopy", "ct", "computed tomography", "mri", "pet",
    "ultrasonography", "ultrasound", "biopsy", "endoscopy",
    "sigmoidoscopy", "cystoscopy", "bone scan", "x-ray",
])


def _classify_encounter_milestone(coded_concepts: List[Dict]) -> str:
    for c in coded_concepts:
        name = (c.get("name") or "").lower()
        context = (c.get("context") or "patient").lower()
        if context in ("negated", "plan"):
            continue
        if any(kw in name for kw in _INVESTIGATION_KEYWORDS):
            return "investigation"
        if any(kw in name for kw in _CLINIC_KEYWORDS):
            return "specialist_visit"
    return "related"


def _link_post_referral(
    patient_id: str, ref_date: str, episode_id: str, linked_ids: set, client=None,
) -> int:
    post_days = int(get_agent_property("episode-builder", "postReferralDays", 180))
    try:
        ref_dt = datetime.strptime(ref_date, "%Y-%m-%d")
        post_end = (ref_dt + timedelta(days=post_days)).strftime("%Y-%m-%d")
    except ValueError:
        return 0

    post_day_after = (ref_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    linked = _link_coded_post_referral(
        patient_id, post_day_after, post_end, episode_id, linked_ids, client=client,
    )
    linked += _link_uncoded_post_referral(
        patient_id, post_day_after, post_end, episode_id, linked_ids, client=client,
    )

    if linked:
        logger.info("Linked %d post-referral encounters to episode %s", linked, episode_id)
    return linked


def _link_coded_post_referral(
    patient_id: str, start: str, end: str,
    episode_id: str, linked_ids: set, client=None,
) -> int:
    post_encounters = get_encounters_with_codes(patient_id, start, end, client=client)
    linked = 0
    for enc in post_encounters:
        enc_id = enc.get("encounter_id", "")
        if enc_id in linked_ids:
            continue
        codes = enc.get("coded_concepts") or []
        positive_codes = [
            c for c in codes
            if (c.get("context") or "patient") not in ("negated", "plan")
        ]
        if not positive_codes:
            continue
        milestone = _classify_encounter_milestone(positive_codes)
        link_encounter_to_episode(
            enc_id, episode_id, milestone,
            f"Post-referral {milestone} (auto-linked)", client=client,
        )
        linked_ids.add(enc_id)
        linked += 1
    return linked


def _link_uncoded_post_referral(
    patient_id: str, start: str, end: str,
    episode_id: str, linked_ids: set, client=None,
) -> int:
    all_encounters = get_encounters_by_timeframe(patient_id, start, end, client=client)
    linked = 0
    for enc in all_encounters:
        enc_id = enc.get("encounter_id", "")
        if enc_id in linked_ids:
            continue
        text = enc.get("encounter_text") or ""
        if not text:
            continue
        milestone = _classify_text_milestone(text)
        if not milestone:
            continue
        link_encounter_to_episode(
            enc_id, episode_id, milestone,
            f"Post-referral {milestone} (text-linked)", client=client,
        )
        linked_ids.add(enc_id)
        linked += 1
    return linked


def _classify_text_milestone(text: str) -> Optional[str]:
    from services.analysis_worker.app.analyzers import anchor_detector as _anchor_mod
    diag_re = getattr(_anchor_mod, "_DIAGNOSIS_STRUCTURE_RE", None)
    if diag_re and diag_re.search(text):
        return "diagnosis"
    return None


def _persist_timepoints(episode_id: str, client=None) -> int:
    try:
        tp_result = identify_timepoints_from_episode(episode_id, client=client)
        counts = persist_episode_timepoints(episode_id, tp_result, client=client)
        return counts.get("timepoints_created", 0)
    except Exception as exc:
        logger.warning("Timepoint persistence failed for %s: %s", episode_id, exc)
        return 0


# ── LLM classification ───────────────────────────────────────────────────


def _format_anchor_detail(anchor: Dict[str, Any]) -> str:
    date = (anchor.get("encounter_date", "") or "")[:10]
    name = anchor.get("concept_name", "unknown")
    text = (anchor.get("encounter_text", "") or "")[:200]
    source = anchor.get("source", "coded")
    parts = [f"  - [{date}] {name} (source: {source})"]
    if text:
        parts.append(f"    Text: {text}")
    return "\n".join(parts)


def _build_rich_coded_summary(
    patient_id: str, anchors: AnchorResult, referral_date: str,
) -> str:
    parts: List[str] = []

    if anchors.referral_anchors:
        parts.append(f"REFERRALS ({len(anchors.referral_anchors)} found):")
        for a in anchors.referral_anchors[:5]:
            parts.append(_format_anchor_detail(a))

    if anchors.diagnosis_anchors:
        parts.append(f"\nDIAGNOSIS ANCHORS ({len(anchors.diagnosis_anchors)} found):")
        for a in anchors.diagnosis_anchors[:5]:
            parts.append(_format_anchor_detail(a))
        first_diag = anchors.diagnosis_anchors[0]
        enc_id = first_diag.get("encounter_id", "")
        if enc_id and not first_diag.get("encounter_text"):
            result = get_encounter_full_text(enc_id)
            text = str(result.get("encounter_text", "")) if isinstance(result, dict) else ""
            if text:
                parts.append(f"    Full text: {text[:500]}")

    if anchors.treatment_anchors:
        parts.append(f"\nTREATMENT ANCHORS ({len(anchors.treatment_anchors)} found):")
        for a in anchors.treatment_anchors[:5]:
            parts.append(_format_anchor_detail(a))

    if not parts:
        return "No coded data available"
    return "\n".join(parts)


async def _classify_episode(
    patient_id: str,
    episode_id: str,
    cancer_type: str,
    anchor_date: str,
    anchors: AnchorResult,
    anchor_type: str = "referral",
) -> Dict[str, Any]:
    coded_summary = _build_rich_coded_summary(patient_id, anchors, anchor_date)

    system_prompt = get_agent_prompt(
        "episode-builder", "agent-system-prompt", EPISODE_BUILDER_SYSTEM
    )
    task_template = get_agent_prompt(
        "episode-builder", "agent-task-template", EPISODE_BUILDER_TASK
    )

    task = task_template.format(
        patient_id=patient_id,
        coded_summary=coded_summary,
        episode_id=episode_id,
        cancer_type=cancer_type,
        referral_date=anchor_date,
        anchor_type=anchor_type,
        anchor_date=anchor_date,
    )

    result = await invoke_llm_json(
        system_prompt=system_prompt,
        user_message=task,
        max_tokens=1024,
        temperature=0.0,
        prefill_hint='{"status":"',
        agent_task="episode_builder",
        patient_id=patient_id,
        max_retries=3,
    )

    if result.get("error"):
        result = {
            "status": "inconclusive",
            "confidence": 0,
            "reasoning": "LLM did not return valid JSON",
            "diagnosis_date": None,
            "treatment_date": None,
        }
    return result
