"""Peer cohort milestone percentile queries.

Atlas trace: DO-64B006B5 (see libs/variation/__init__.py).

Computes P25/P50/P75 interval distributions per (from_step, to_step)
milestone pair within a Leiden community. Sample size is returned so
downstream scoring can skip under-represented pairs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient


_PERCENTILE_CYPHER = """
MATCH (p:Patient)
WHERE p.variation_community_id = $community_id {scope_where}
MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.referral_date IS NOT NULL AND trim(ep.referral_date) <> ''
  AND date(ep.referral_date) >= date() - duration({{months: $months}})
MATCH (e1:Encounter)-[r1:IS_PART_OF]->(ep)
MATCH (e2:Encounter)-[r2:IS_PART_OF]->(ep)
WHERE r1.milestone_type IS NOT NULL AND trim(r1.milestone_type) <> ''
  AND r2.milestone_type IS NOT NULL AND trim(r2.milestone_type) <> ''
  AND e1.date IS NOT NULL AND e2.date IS NOT NULL
  AND e2.date > e1.date
WITH r1.milestone_type AS from_step,
     r2.milestone_type AS to_step,
     duration.inDays(date(e1.date), date(e2.date)).days AS interval_days
RETURN from_step,
       to_step,
       percentileCont(interval_days, 0.25) AS p25,
       percentileCont(interval_days, 0.50) AS p50,
       percentileCont(interval_days, 0.75) AS p75,
       count(*) AS sample_size
ORDER BY from_step, to_step
"""


@dataclass(frozen=True)
class MilestonePercentile:
    """P25/P50/P75 of the days-between distribution for a milestone pair."""

    from_step: str
    to_step: str
    p25: float
    p50: float
    p75: float
    sample_size: int


def _build_scope_where(scope: Optional[CallerScope]) -> str:
    if scope is None or getattr(scope, "is_admin", False):
        return ""
    org_ids = getattr(scope, "org_ids", None) or []
    if not org_ids:
        return ""
    return (
        " AND EXISTS { "
        "(p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
        "WHERE gp.id IN $scope_org_ids "
        "}"
    )


def get_milestone_percentiles(
    client: PatientGraphClient,
    community_id: int,
    scope: Optional[CallerScope] = None,
    months: int = 24,
) -> List[MilestonePercentile]:
    """Return P25/P50/P75 intervals per milestone pair within a community.

    `months` bounds the referral_date lookback window so stale pathway
    timings do not bias the comparator distribution.
    """
    scope_where = _build_scope_where(scope)
    cypher = _PERCENTILE_CYPHER.format(scope_where=scope_where)
    params = {"community_id": int(community_id), "months": int(months)}
    if scope_where:
        params["scope_org_ids"] = list(getattr(scope, "org_ids", []) or [])
    rows = client.run(cypher, **params)
    return [
        MilestonePercentile(
            from_step=row["from_step"],
            to_step=row["to_step"],
            p25=float(row["p25"]),
            p50=float(row["p50"]),
            p75=float(row["p75"]),
            sample_size=int(row["sample_size"]),
        )
        for row in rows
    ]
