"""Per-site orchestration for the unwarranted variation engine.

Atlas trace: DO-64B006B5 (see libs/variation/__init__.py).

Ties together Leiden community persist (phase 1), cohort percentile
queries (phase 2), per-episode scoring + write (phase 3), and root-cause
attribution (phase 4) into a single site-level run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient
from libs.variation import (
    DEFAULT_MIN_SAMPLE_SIZE,
    MilestoneObservation,
    MilestonePercentile,
    attribute_root_cause,
    get_milestone_percentiles,
    score_episode,
    write_attribution_result,
    write_variation_result,
)

logger = logging.getLogger(__name__)


_EPISODES_IN_SCOPE_CYPHER = """
MATCH (p:Patient) {scope_where}
WHERE p.variation_community_id IS NOT NULL
MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.referral_date IS NOT NULL AND trim(toString(ep.referral_date)) <> ''
  AND date(toString(ep.referral_date)) >= date() - duration({{months: $months}})
MATCH (e1:Encounter)-[r1:IS_PART_OF]->(ep)
MATCH (e2:Encounter)-[r2:IS_PART_OF]->(ep)
WHERE r1.milestone_type IS NOT NULL AND trim(r1.milestone_type) <> ''
  AND r2.milestone_type IS NOT NULL AND trim(r2.milestone_type) <> ''
  AND e1.date IS NOT NULL AND e2.date IS NOT NULL
  AND e2.date > e1.date
RETURN p.id AS patient_id,
       ep.id AS episode_id,
       p.variation_community_id AS community_id,
       r1.milestone_type AS from_step,
       r2.milestone_type AS to_step,
       e1.date AS from_date,
       duration.inDays(date(e1.date), date(e2.date)).days AS interval_days
ORDER BY ep.id, e1.date, e2.date
"""


@dataclass
class VariationRunSummary:
    """Summary of a site-level variation run."""

    episodes_considered: int = 0
    episodes_scored: int = 0
    episodes_flagged: int = 0
    episodes_attributed: int = 0


def _build_scope_where(scope: Optional[CallerScope]) -> str:
    if scope is None or getattr(scope, "is_admin", False):
        return ""
    org_ids = getattr(scope, "org_ids", None) or []
    if not org_ids:
        return ""
    return (
        "WHERE EXISTS { "
        "(p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
        "WHERE gp.id IN $scope_org_ids "
        "}"
    )


def _load_episode_observations(
    client: PatientGraphClient,
    scope: Optional[CallerScope],
    months: int,
) -> Dict[str, Dict[str, object]]:
    """Return {episode_id: {patient_id, community_id, observations}}."""
    scope_where = _build_scope_where(scope)
    cypher = _EPISODES_IN_SCOPE_CYPHER.format(scope_where=scope_where)
    params = {"months": int(months)}
    if scope_where:
        params["scope_org_ids"] = list(getattr(scope, "org_ids", []) or [])
    rows = client.run(cypher, **params)
    episodes: Dict[str, Dict[str, object]] = {}
    for row in rows:
        eid = row["episode_id"]
        bucket = episodes.setdefault(
            eid,
            {
                "patient_id": row["patient_id"],
                "community_id": int(row["community_id"]),
                "observations": [],
            },
        )
        bucket["observations"].append(
            MilestoneObservation(
                from_step=row["from_step"],
                to_step=row["to_step"],
                interval_days=float(row["interval_days"]),
                observed_at=str(row["from_date"]) if row["from_date"] else None,
            )
        )
    return episodes


def _percentiles_for_community(
    client: PatientGraphClient,
    scope: Optional[CallerScope],
    community_id: int,
    months: int,
    cache: Dict[int, List[MilestonePercentile]],
) -> List[MilestonePercentile]:
    cached = cache.get(community_id)
    if cached is not None:
        return cached
    pcts = get_milestone_percentiles(client, community_id, scope, months)
    cache[community_id] = pcts
    return pcts


def run_variation_for_site(
    client: PatientGraphClient,
    scope: Optional[CallerScope],
    months: int = 24,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
) -> VariationRunSummary:
    """Score every in-scope episode and write verdicts + attributions.

    Requires Patient.variation_community_id to be populated first (via
    the Leiden persist pass in algorithm_runner_patient._run_groups with
    persist=True).
    """
    episodes = _load_episode_observations(client, scope, months)
    summary = VariationRunSummary(episodes_considered=len(episodes))
    pct_cache: Dict[int, List[MilestonePercentile]] = {}
    for episode_id, bucket in episodes.items():
        community_id = int(bucket["community_id"])
        observations = bucket["observations"]  # type: ignore[assignment]
        percentiles = _percentiles_for_community(
            client, scope, community_id, months, pct_cache
        )
        result = score_episode(
            episode_id=episode_id,
            community_id=community_id,
            observations=observations,
            percentiles=percentiles,
            min_sample_size=min_sample_size,
        )
        if result is None:
            continue
        summary.episodes_scored += 1
        write_variation_result(client, result)
        if not result.variation_flag:
            continue
        summary.episodes_flagged += 1
        attribution = attribute_root_cause(
            client, str(bucket["patient_id"]), result.first_divergence
        )
        if write_attribution_result(client, episode_id, attribution):
            summary.episodes_attributed += 1
    logger.info(
        "Variation run complete: considered=%d scored=%d flagged=%d attributed=%d",
        summary.episodes_considered,
        summary.episodes_scored,
        summary.episodes_flagged,
        summary.episodes_attributed,
    )
    return summary
