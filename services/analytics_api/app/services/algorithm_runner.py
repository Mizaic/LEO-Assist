"""GDS algorithm runner for Pathway Explorer research missions.

Atlas trace:
  DO: DO-38C2D850
  DI: DI-58988BF2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-38C2D850")

Public interface: call run_mission() with a mission ID and scoping params.

Internally the module delegates to three focused sub-modules:
  algorithm_runner_helpers.py    -- shared helpers, data types, enrichers
  algorithm_runner_patient.py    -- groups, similar, gaps, circles
  algorithm_runner_condition.py  -- critical, busiest, bridges, missing, teams,
                                    bottleneck

Result counts by detail level:
  summary    -- top 10 aggregated results
  detailed   -- top 50 individual results
  everything -- all results (capped at 500 for UI safety)
"""

from __future__ import annotations

import logging
from typing import Optional

from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient

from services.analytics_api.app.services.algorithm_runner_helpers import (
    AlgorithmResult,
    CoverageInfo,
    _DETAIL_LIMITS,
    _build_scope_label,
    _coverage_note,  # noqa: F401
    _ensure_projection,  # noqa: F401
    _gds_client_from_env,  # noqa: F401
    _get_coverage,  # noqa: F401
    _period_to_months,  # noqa: F401
)
from services.analytics_api.app.services.algorithm_runner_condition import (
    _run_bottleneck,
    _run_bridges,
    _run_busiest,
    _run_critical,
    _run_missing,
    _run_teams,
    NEXT_STEPS as _NEXT_STEPS_CONDITION,
)
from services.analytics_api.app.services.algorithm_runner_patient import (
    _run_circles,
    _run_gaps,
    _run_groups,
    _run_similar,
    NEXT_STEPS as _NEXT_STEPS_PATIENT,
)

logger = logging.getLogger(__name__)

# Re-export for consumers who import from this module
__all__ = ["AlgorithmResult", "CoverageInfo", "run_mission"]

_RUNNERS = {
    "groups": _run_groups,
    "similar": _run_similar,
    "gaps": _run_gaps,
    "circles": _run_circles,
    "critical": _run_critical,
    "busiest": _run_busiest,
    "bridges": _run_bridges,
    "missing": _run_missing,
    "teams": _run_teams,
    "bottleneck": _run_bottleneck,
}

_NEXT_STEPS = {**_NEXT_STEPS_PATIENT, **_NEXT_STEPS_CONDITION}


def run_mission(
    mission_id: str,
    client: PatientGraphClient,
    scope: CallerScope,
    area: str = "all",
    period: str = "12m",
    detail: str = "summary",
    patient_id: Optional[str] = None,
    confidence_min: float = 0.5,
    context_filter: str = "current",
) -> AlgorithmResult:
    """Run a named mission and return structured results.

    Args:
        mission_id:       Mission card ID (e.g. "groups", "bottleneck").
        client:           PatientGraphClient for the org.
        scope:            CallerScope for org-filtering.
        area:             Audit area / cancer site (e.g. "lung", "all").
        period:           Time window (e.g. "6m", "12m").
        detail:           Detail level: "summary" | "detailed" | "everything".
        patient_id:       Required for "similar" mission.
        confidence_min:   Minimum edge confidence for co-occurrence projection.
        context_filter:   "current" (active conditions only) or "all".
    """
    runner = _RUNNERS.get(mission_id)
    if runner is None:
        return AlgorithmResult(
            mission_id=mission_id,
            headline="This investigation is not yet available.",
            items=[],
            total_count=0,
            coverage=CoverageInfo(),
            method_plain="",
            method_technical="",
            next_steps=[],
            detail_level=detail,
            data_available=False,
            unavailable_reason=f"Mission {mission_id!r} is not implemented.",
        )

    scope_label = _build_scope_label(area, period)
    limit = _DETAIL_LIMITS.get(detail, 10)

    try:
        return runner(
            client=client,
            scope=scope,
            area=area,
            period=period,
            detail=detail,
            limit=limit,
            scope_label=scope_label,
            patient_id=patient_id,
            confidence_min=confidence_min,
            context_filter=context_filter,
        )
    except Exception as exc:
        logger.error("Mission %s failed: %s", mission_id, exc, exc_info=True)
        return AlgorithmResult(
            mission_id=mission_id,
            headline="Something went wrong running this investigation.",
            items=[],
            total_count=0,
            coverage=CoverageInfo(),
            method_plain="",
            method_technical="",
            next_steps=[],
            detail_level=detail,
            error=str(exc),
        )
