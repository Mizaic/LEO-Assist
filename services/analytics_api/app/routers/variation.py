"""Unwarranted variation detection endpoints.

Atlas trace:
  DO: DO-64B006B5
  DI: DI-EF8EA3BD
  UN: UN-86B5D433
  R:  R-31217EFA
  VT: VT-3B37176C
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-64B006B5")

Routes
------
POST /variation/run-site             -- score every in-scope episode
GET  /variation/episodes/{id}        -- variation detail for one episode
GET  /variation/summary              -- site-level flag rollup
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient
from libs.variation import (
    DEFAULT_MIN_SAMPLE_SIZE,
    get_milestone_percentiles,
)
from services.analytics_api.app.services.variation_service import (
    VariationRunSummary,
    run_variation_for_site,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class RunSiteRequest(BaseModel):
    """Inputs for POST /variation/run-site."""

    months: int = Field(
        default=24, ge=1, le=120,
        description="Cohort lookback window in months.",
    )
    min_sample_size: int = Field(
        default=DEFAULT_MIN_SAMPLE_SIZE, ge=1, le=10_000,
        description="Minimum cohort size per milestone pair before flag is written.",
    )


class RunSiteResponse(BaseModel):
    episodes_considered: int
    episodes_scored: int
    episodes_flagged: int
    episodes_attributed: int


class EpisodeVariationResponse(BaseModel):
    episode_id: str
    variation_flag: Optional[bool] = None
    variation_score: Optional[float] = None
    variation_first_divergence: Optional[str] = None
    variation_outlier_steps: List[str] = Field(default_factory=list)
    variation_community_id: Optional[int] = None
    variation_compared_pairs: Optional[int] = None
    variation_observed_pairs: Optional[int] = None
    variation_attributed_node_type: Optional[str] = None
    variation_attributed_node_id: Optional[str] = None
    variation_attributed_node_name: Optional[str] = None
    variation_updated: Optional[str] = None
    cohort_percentiles: List[Dict[str, Any]] = Field(default_factory=list)
    cohort_size: int = 0


class VariationStepSummary(BaseModel):
    step: str
    flagged_episodes: int


class VariationAttributionSummary(BaseModel):
    node_type: str
    node_id: str
    node_name: str
    flagged_episodes: int


class SummaryResponse(BaseModel):
    total_episodes: int
    flagged_episodes: int
    by_first_divergence: List[VariationStepSummary] = Field(default_factory=list)
    by_attributed_node: List[VariationAttributionSummary] = Field(default_factory=list)


def _to_response(summary: VariationRunSummary) -> RunSiteResponse:
    return RunSiteResponse(
        episodes_considered=summary.episodes_considered,
        episodes_scored=summary.episodes_scored,
        episodes_flagged=summary.episodes_flagged,
        episodes_attributed=summary.episodes_attributed,
    )


@router.post("/variation/run-site", response_model=RunSiteResponse)
def run_site(
    body: RunSiteRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> RunSiteResponse:
    """Score every in-scope episode and write flags + attributions.

    Runs synchronously for MVP; callers with large cohorts should budget
    for multi-minute response times. A future iteration can move this
    to BackgroundTasks or a Celery-style queue.
    """
    client = PatientGraphClient()
    try:
        summary = run_variation_for_site(
            client,
            scope,
            months=body.months,
            min_sample_size=body.min_sample_size,
        )
    finally:
        client.close()
    return _to_response(summary)


_EPISODE_DETAIL_CYPHER = """
MATCH (ep:EpisodeOfCare {id: $episode_id})
OPTIONAL MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep)
RETURN ep.id AS episode_id,
       ep.variation_flag AS variation_flag,
       ep.variation_score AS variation_score,
       ep.variation_first_divergence AS variation_first_divergence,
       ep.variation_outlier_steps AS variation_outlier_steps,
       ep.variation_community_id AS variation_community_id,
       ep.variation_compared_pairs AS variation_compared_pairs,
       ep.variation_observed_pairs AS variation_observed_pairs,
       ep.variation_attributed_node_type AS variation_attributed_node_type,
       ep.variation_attributed_node_id AS variation_attributed_node_id,
       ep.variation_attributed_node_name AS variation_attributed_node_name,
       toString(ep.variation_updated) AS variation_updated,
       p.variation_community_id AS patient_community_id
"""


_COHORT_SIZE_CYPHER = """
MATCH (p:Patient)
WHERE p.variation_community_id = $community_id
RETURN count(p) AS cohort_size
"""


def _cohort_size(client: PatientGraphClient, community_id: int) -> int:
    rows = client.run(_COHORT_SIZE_CYPHER, community_id=int(community_id))
    return int(rows[0]["cohort_size"]) if rows else 0


def _load_episode_detail(
    client: PatientGraphClient,
    episode_id: str,
) -> Dict[str, Any]:
    rows = client.run(_EPISODE_DETAIL_CYPHER, episode_id=episode_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Episode not found")
    return rows[0]


@router.get(
    "/variation/episodes/{episode_id}",
    response_model=EpisodeVariationResponse,
)
def episode_detail(
    episode_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> EpisodeVariationResponse:
    """Return variation flags and the relevant cohort percentile detail."""
    client = PatientGraphClient()
    try:
        row = _load_episode_detail(client, episode_id)
        community_id = row.get("patient_community_id") or row.get(
            "variation_community_id"
        )
        percentiles: List[Dict[str, Any]] = []
        cohort_size = 0
        if community_id is not None:
            cohort_size = _cohort_size(client, int(community_id))
            pcts = get_milestone_percentiles(client, int(community_id), scope)
            percentiles = [
                {
                    "from_step": p.from_step,
                    "to_step": p.to_step,
                    "p25": p.p25,
                    "p50": p.p50,
                    "p75": p.p75,
                    "sample_size": p.sample_size,
                }
                for p in pcts
            ]
    finally:
        client.close()
    return EpisodeVariationResponse(
        episode_id=row["episode_id"],
        variation_flag=row.get("variation_flag"),
        variation_score=row.get("variation_score"),
        variation_first_divergence=row.get("variation_first_divergence"),
        variation_outlier_steps=list(row.get("variation_outlier_steps") or []),
        variation_community_id=row.get("variation_community_id")
        or row.get("patient_community_id"),
        variation_compared_pairs=row.get("variation_compared_pairs"),
        variation_observed_pairs=row.get("variation_observed_pairs"),
        variation_attributed_node_type=row.get("variation_attributed_node_type"),
        variation_attributed_node_id=row.get("variation_attributed_node_id"),
        variation_attributed_node_name=row.get("variation_attributed_node_name"),
        variation_updated=row.get("variation_updated"),
        cohort_percentiles=percentiles,
        cohort_size=cohort_size,
    )


_SCOPED_EPISODES = """
MATCH (p:Patient) {scope_where}
MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.variation_score IS NOT NULL
WITH ep, coalesce(ep.variation_flag, false) AS flag
RETURN count(ep) AS total_episodes,
       sum(CASE WHEN flag THEN 1 ELSE 0 END) AS flagged_episodes
"""

_STEPS_ROLLUP = """
MATCH (p:Patient) {scope_where}
MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.variation_flag = true
  AND ep.variation_first_divergence IS NOT NULL
RETURN ep.variation_first_divergence AS step,
       count(ep) AS flagged_episodes
ORDER BY flagged_episodes DESC
LIMIT 20
"""

_NODES_ROLLUP = """
MATCH (p:Patient) {scope_where}
MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.variation_flag = true
  AND ep.variation_attributed_node_id IS NOT NULL
RETURN ep.variation_attributed_node_type AS node_type,
       ep.variation_attributed_node_id   AS node_id,
       ep.variation_attributed_node_name AS node_name,
       count(ep) AS flagged_episodes
ORDER BY flagged_episodes DESC
LIMIT 20
"""


def _summary_scope_where(scope: Optional[CallerScope]) -> tuple[str, Dict[str, Any]]:
    if scope is None or getattr(scope, "is_admin", False):
        return "", {}
    org_ids = list(getattr(scope, "org_ids", []) or [])
    if not org_ids:
        return "", {}
    where = (
        "WHERE EXISTS { "
        "(p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
        "WHERE gp.id IN $scope_org_ids "
        "}"
    )
    return where, {"scope_org_ids": org_ids}


@router.get("/variation/summary", response_model=SummaryResponse)
def site_summary(
    scope: CallerScope = Depends(get_caller_scope),
) -> SummaryResponse:
    """Site-level rollup of variation flags and attributed nodes."""
    scope_where, params = _summary_scope_where(scope)
    client = PatientGraphClient()
    try:
        overall_rows = client.run(
            _SCOPED_EPISODES.format(scope_where=scope_where), **params
        )
        step_rows = client.run(
            _STEPS_ROLLUP.format(scope_where=scope_where), **params
        )
        node_rows = client.run(
            _NODES_ROLLUP.format(scope_where=scope_where), **params
        )
    finally:
        client.close()
    overall = overall_rows[0] if overall_rows else {
        "total_episodes": 0, "flagged_episodes": 0,
    }
    return SummaryResponse(
        total_episodes=int(overall.get("total_episodes") or 0),
        flagged_episodes=int(overall.get("flagged_episodes") or 0),
        by_first_divergence=[
            VariationStepSummary(
                step=row["step"],
                flagged_episodes=int(row["flagged_episodes"]),
            )
            for row in step_rows
        ],
        by_attributed_node=[
            VariationAttributionSummary(
                node_type=row["node_type"],
                node_id=row["node_id"],
                node_name=row.get("node_name") or "",
                flagged_episodes=int(row["flagged_episodes"]),
            )
            for row in node_rows
        ],
    )
