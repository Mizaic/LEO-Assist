"""Operational reports: sitrep and cohort builder.

Atlas trace:
  DO: DO-0998FAF5
  Also implements: DO-86800C9B
  DI: DI-FC80B65A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0998FAF5")
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from libs.dq._filters import DQFilters
from libs.dq._models import CohortResult, SitrepResult

logger = logging.getLogger(__name__)

_SITREP_EPISODES_Q = """
MATCH (ep:EpisodeOfCare)
RETURN ep.status AS status, count(*) AS cnt
"""

_SITREP_HITL_Q = """
MATCH (ep:EpisodeOfCare {hitl_flag: true})
RETURN count(*) AS cnt
"""

_SITREP_SF_TASKS_Q = """
MATCH (t:SurfaceFormTask)
WHERE t.status IN ['pending', 'in_review']
RETURN count(*) AS cnt
"""

_SITREP_GOLD_Q = """
MATCH (g:GoldLabel)
RETURN count(*) AS cnt
"""

_SITREP_TRAINING_Q = """
MATCH (tc:TrainingCandidate)
RETURN count(*) AS cnt
"""

_COHORT_Q = """
MATCH (p:Patient)-[:HAS_EPISODE]->(ep:EpisodeOfCare)
WHERE ($status IS NULL OR ep.status = $status)
  AND ($site IS NULL OR ep.cancer_type = $site)
  AND ($since IS NULL OR ep.referral_date >= $since)
  AND ($until IS NULL OR ep.referral_date <= $until)
RETURN DISTINCT p.id AS patient_id
LIMIT $limit
"""


def get_sitrep(patient_client: Any) -> SitrepResult:
    """Return unified operational situation report."""
    from libs.neo4j_client.client import run_with_retry

    ep_rows = run_with_retry(patient_client, _SITREP_EPISODES_Q)
    status_counts = {r["status"]: int(r["cnt"]) for r in ep_rows if r.get("status")}
    stale_count = sum(v for k, v in status_counts.items() if "stale" in (k or ""))

    hitl_rows = run_with_retry(patient_client, _SITREP_HITL_Q)
    hitl_count = int((hitl_rows[0] or {}).get("cnt") or 0) if hitl_rows else 0

    sf_rows = _safe_run(patient_client, _SITREP_SF_TASKS_Q)
    sf_backlog = int((sf_rows[0] or {}).get("cnt") or 0) if sf_rows else 0

    gold_rows = _safe_run(patient_client, _SITREP_GOLD_Q)
    gold_count = int((gold_rows[0] or {}).get("cnt") or 0) if gold_rows else 0

    tc_rows = _safe_run(patient_client, _SITREP_TRAINING_Q)
    tc_count = int((tc_rows[0] or {}).get("cnt") or 0) if tc_rows else 0

    return SitrepResult(
        episode_status_counts=status_counts,
        stale_count=stale_count,
        hitl_queue_depth=hitl_count,
        sf_task_backlog=sf_backlog,
        gold_label_count=gold_count,
        training_candidate_count=tc_count,
    )


def get_cohort(
    patient_client: Any, filters: Optional[DQFilters] = None
) -> CohortResult:
    """Return patient IDs matching episode filters."""
    from libs.neo4j_client.client import run_with_retry

    f = filters or DQFilters()
    rows = run_with_retry(
        patient_client,
        _COHORT_Q,
        status=f.status,
        site=f.site,
        since=f.since,
        until=f.until,
        limit=f.limit,
    )
    ids = [r["patient_id"] for r in rows if r.get("patient_id")]
    return CohortResult(
        patient_ids=ids,
        total_count=len(ids),
        filters_applied=f.to_cypher_params(),
    )


def _safe_run(client: Any, query: str) -> list[dict]:
    try:
        from libs.neo4j_client.client import run_with_retry

        return run_with_retry(client, query)
    except Exception as exc:
        logger.debug("sitrep query skipped: %s", exc)
        return []
