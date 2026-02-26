"""Episode consolidation logic.

Detects when multiple cancer episodes for the same patient have referral
dates within a configurable time window and uses LLM to decide whether
they represent a single diagnostic journey. If so, merges secondaries
into a primary episode.

Ported from VRB clinical-ai/app/agent/subagents/episode_consolidator.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from libs.agent_config import get_agent_property
from libs.llm_client.json_helper import invoke_llm_json
from services.analysis_worker.app.prompts.episode_prompts import (
    EPISODE_CONSOLIDATION_SYSTEM,
    EPISODE_CONSOLIDATION_TASK,
)
from services.analysis_worker.app.queries.episode_queries import (
    get_episode_summary,
    merge_episodes,
)

logger = logging.getLogger(__name__)


async def try_consolidate(
    patient_id: str,
    episode_ids: List[str],
    errors: List[str],
    client=None,
) -> int:
    """Check for consolidation candidates and merge if appropriate.

    Returns the number of episodes merged into primaries.
    """
    candidates = _detect_candidates(episode_ids, client=client)
    if not candidates:
        return 0

    try:
        return await _consolidate_episodes(patient_id, candidates, client=client)
    except Exception as exc:
        errors.append(f"Consolidation failed: {exc}")
        logger.error("Episode consolidation error: %s", exc)
    return 0


def _detect_candidates(
    episode_ids: List[str],
    client=None,
) -> List[Dict[str, Any]]:
    """Detect episodes whose referral dates fall within a configurable window."""
    window = int(get_agent_property("episode-builder", "consolidationWindowDays", 30))

    summaries = []
    for eid in episode_ids:
        s = get_episode_summary(eid, client=client)
        if s and s.get("status") != "merged":
            summaries.append(s)

    if len(summaries) < 2:
        return []

    summaries.sort(key=lambda s: s.get("referral_date") or "")

    earliest = summaries[0].get("referral_date", "")
    latest = summaries[-1].get("referral_date", "")
    if not earliest or not latest:
        return []

    try:
        dt_early = datetime.strptime(str(earliest)[:10], "%Y-%m-%d")
        dt_late = datetime.strptime(str(latest)[:10], "%Y-%m-%d")
    except ValueError:
        return []

    if (dt_late - dt_early) <= timedelta(days=window):
        logger.info(
            "Consolidation candidates: %d episodes within %d days",
            len(summaries), window,
        )
        return summaries
    return []


async def _consolidate_episodes(
    patient_id: str,
    summaries: List[Dict[str, Any]],
    client=None,
) -> int:
    """Use LLM to decide whether to merge candidate episodes."""
    episode_text = _format_summaries(summaries)
    window_days = _calc_day_span(
        summaries[0].get("referral_date", ""),
        summaries[-1].get("referral_date", ""),
    )

    task = EPISODE_CONSOLIDATION_TASK.format(
        patient_id=patient_id,
        episode_count=len(summaries),
        window_days=window_days,
        episode_summaries=episode_text,
    )

    decision = await invoke_llm_json(
        system_prompt=EPISODE_CONSOLIDATION_SYSTEM,
        user_message=task,
        max_tokens=1024,
        temperature=0.0,
        prefill_hint='{"should_merge":',
        agent_task="episode_consolidation",
        patient_id=patient_id,
    )

    decision = _normalise_response(decision)
    if not decision.get("should_merge"):
        logger.info("LLM decided NOT to merge episodes for %s", patient_id)
        return 0

    return _apply_merge(decision, summaries, client=client)


def _format_summaries(summaries: List[Dict[str, Any]]) -> str:
    lines = []
    for s in summaries:
        lines.append(
            f"Episode: {s['episode_id']}\n"
            f"  Cancer type: {s.get('cancer_type', 'unknown')}\n"
            f"  Status: {s.get('status', 'unknown')} "
            f"(confidence: {s.get('confidence', 0)})\n"
            f"  Referral date: {s.get('referral_date', 'unknown')}\n"
            f"  Reasoning: {s.get('reasoning', 'N/A')}"
        )
    return "\n\n".join(lines)


def _normalise_response(decision: Any) -> Dict[str, Any]:
    if isinstance(decision, list):
        decision = decision[0] if decision else {}
    if not isinstance(decision, dict):
        logger.warning("Consolidation LLM returned non-dict: %s", type(decision))
        return {}
    return decision


def _apply_merge(
    decision: Dict[str, Any],
    summaries: List[Dict[str, Any]],
    client=None,
) -> int:
    primary_id = decision.get("primary_episode_id", "")
    reasoning = decision.get("reasoning", "LLM consolidation")
    merged_type = decision.get("merged_cancer_type")

    all_ids = [s["episode_id"] for s in summaries]
    if primary_id not in all_ids:
        primary_id = _pick_best_primary(summaries)

    secondary_ids = [eid for eid in all_ids if eid != primary_id]
    if not secondary_ids:
        return 0

    referral_types = [s.get("cancer_type", "unknown") for s in summaries]
    merge_episodes(primary_id, secondary_ids, reasoning, referral_types, client=client)

    if merged_type:
        _update_cancer_type(primary_id, merged_type, client=client)

    logger.info(
        "Merged %d episodes into %s (%s): %s",
        len(secondary_ids), primary_id,
        merged_type or "same type",
        reasoning[:100],
    )
    return len(secondary_ids)


def _update_cancer_type(episode_id: str, cancer_type: str, client=None) -> None:
    from libs.neo4j_client.client import PatientGraphClient
    c = client or PatientGraphClient()
    c.run(
        "MATCH (ep:CancerEpisode {episode_id: $eid}) SET ep.cancer_type = $ct",
        eid=episode_id, ct=cancer_type,
    )


def _pick_best_primary(summaries: List[Dict[str, Any]]) -> str:
    """Pick the best primary episode from candidates (heuristic fallback).

    Scores by: treatment evidence in reasoning > confirmed status > confidence.
    """
    treatment_terms = ("treatment", "palliative", "nephrostomy", "chemo",
                       "hospice", "radiotherapy", "surgery")
    status_rank = {"confirmed": 3, "excluded": 2, "inconclusive": 1}

    def score(s: Dict[str, Any]) -> tuple:
        reasoning = (s.get("reasoning") or "").lower()
        has_treatment = any(t in reasoning for t in treatment_terms)
        return (
            has_treatment,
            status_rank.get(s.get("status", ""), 0),
            s.get("confidence", 0),
        )

    ranked = sorted(summaries, key=score, reverse=True)
    return ranked[0]["episode_id"]


def _calc_day_span(date1: str, date2: str) -> int:
    try:
        d1 = datetime.strptime(str(date1)[:10], "%Y-%m-%d")
        d2 = datetime.strptime(str(date2)[:10], "%Y-%m-%d")
        return abs((d2 - d1).days)
    except (ValueError, TypeError):
        return 0
